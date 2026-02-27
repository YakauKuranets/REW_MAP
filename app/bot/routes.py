"""
Маршруты для телеграм‑бота.

Бот может создавать новые точки без роли администратора. Для
авторизации используется API‑ключ, передаваемый в заголовке
`X-API-KEY` или в query‑параметре `api_key`. При создании
заявки осуществляется поиск дубликатов и при необходимости
определяются координаты через офлайн/онлайн геокодирование.
"""

import json
import os
import uuid
import time
import tempfile
from threading import Thread
from typing import Any, Dict, List, Optional

import requests
from openai import OpenAI
from compat_flask import Response, jsonify, request, current_app, render_template, g

from sqlalchemy.exc import OperationalError

from ..helpers import parse_coord, in_range
from ..models import Address, PendingMarker, PendingHistory
from ..extensions import db
from ..db_compat import ensure_sqlite_schema_minimal
from ..helpers import haversine_m  # для возможного использования

from . import bp
from ..sockets import broadcast_event_sync
from ..security.api_keys import require_bot_api_key
from ..security.rate_limit import check_rate_limit
from ..services.ai_vision_service import analyze_incident_photo
from ..services.voice_service import enqueue_voice_incident
from .middlewares.telegram_webapp_security import enforce_telegram_init_data, validate_telegram_init_data



def _resolve_photo_path(photo_value: Optional[str]) -> Optional[str]:
    if not photo_value:
        return None
    pv = photo_value.strip()
    if not pv:
        return None
    if pv.startswith('http://') or pv.startswith('https://'):
        return None
    if os.path.isabs(pv) and os.path.isfile(pv):
        return pv
    up = current_app.config.get('UPLOAD_FOLDER')
    if up:
        candidate = os.path.join(up, pv)
        if os.path.isfile(candidate):
            return candidate
    return None


def _run_ai_vision_job(app, pending_id: int, image_path: str) -> None:
    with app.app_context():
        result = analyze_incident_photo(image_path) or {}
        pending = PendingMarker.query.get(pending_id)
        if not pending:
            return
        tags = result.get('tags') if isinstance(result.get('tags'), list) else []
        pending.ai_tags = tags
        if isinstance(result.get('priority'), int):
            pending.priority = result.get('priority')
        if (result.get('category') or '').strip():
            pending.category = (result.get('category') or '').strip()
        db.session.commit()
        broadcast_event_sync('incident_updated', {
            'id': pending.id,
            'priority': pending.priority,
            'tags': pending.ai_tags or [],
            'category': pending.category,
        })


def _schedule_ai_vision_for_pending(pending_id: int, photo_value: Optional[str]) -> None:
    image_path = _resolve_photo_path(photo_value)
    if not image_path:
        return
    app_obj = current_app._get_current_object()
    Thread(target=_run_ai_vision_job, args=(app_obj, pending_id, image_path), daemon=True).start()

# ---------------------------------------------------------------------------
# Вспомогательная функция поиска дубликатов в базе данных
# ---------------------------------------------------------------------------

@bp.before_request
def bot_twa_security_middleware() -> Response | None:
    """Validate Telegram Mini App initData for protected TWA endpoints."""
    protected_endpoints = {"bot.bot_webapp_submit"}
    if request.endpoint in protected_endpoints:
        return enforce_telegram_init_data()
    return None




@bp.post('/voice_camera_submit')
def bot_voice_camera_submit() -> Response:
    """Telegram Mini App: принять голос + координаты, сделать STT через Whisper."""
    audio_file = request.files.get('audio')
    if not audio_file:
        return jsonify({'error': 'audio file is required'}), 400

    lat_raw = request.form.get('lat')
    lon_raw = request.form.get('lon')
    lat = parse_coord(lat_raw)
    lon = parse_coord(lon_raw)

    init_data = (
        request.form.get('initData')
        or request.headers.get('X-Telegram-Init-Data')
        or request.args.get('initData')
        or ''
    ).strip()
    bot_token = (current_app.config.get('TELEGRAM_BOT_TOKEN') or '').strip()
    if not validate_telegram_init_data(init_data, bot_token):
        return jsonify({'error': 'forbidden'}), 403

    # photo может прийти как base64-строка либо как файл (обрабатывается на следующих шагах пайплайна)
    photo_b64 = (request.form.get('photo') or '').strip()
    photo_file = request.files.get('photo')

    temp_path: Optional[str] = None
    try:
        ext = os.path.splitext(audio_file.filename or '')[1] or '.webm'
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            audio_file.save(tmp.name)
            temp_path = tmp.name

        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        with open(temp_path, 'rb') as af:
            transcript = client.audio.transcriptions.create(
                model='whisper-1',
                file=af,
                language='ru',
            )

        transcript_text = (getattr(transcript, 'text', '') or '').strip()
        if not transcript_text:
            return jsonify({'error': 'stt_empty'}), 422

        return jsonify({
            'ok': True,
            'transcript': transcript_text,
            'lat': lat,
            'lon': lon,
            'photo_mode': 'base64' if photo_b64 else ('file' if photo_file else None),
        }), 200
    except Exception as exc:
        current_app.logger.exception('voice_camera_submit failed')
        return jsonify({'error': 'voice_camera_submit_failed', 'details': str(exc)}), 500
    finally:
        try:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass

@bp.post('/voice')
def bot_voice_incident() -> Response:
    """Принять аудио, поставить AI-обработку в очередь и быстро вернуть 202."""
    require_bot_api_key(allow_query_param=True)

    audio_file = request.files.get('audio') or request.files.get('voice') or request.files.get('file')
    if not audio_file:
        return jsonify({'error': 'audio file is required'}), 400

    raw_agent = request.form.get('user_id') or request.form.get('agent_id')
    if raw_agent is None:
        data = request.get_json(silent=True) or {}
        raw_agent = data.get('user_id') or data.get('agent_id')

    try:
        agent_id = int(raw_agent)
    except Exception:
        return jsonify({'error': 'user_id/agent_id must be integer'}), 400

    result = enqueue_voice_incident(audio_file, agent_id)
    return jsonify(result), 202


def find_duplicate_db(name: str, lat: Optional[float], lon: Optional[float], threshold_m: int = 100) -> Optional[Dict[str, Any]]:
    """
    Найти возможный дубликат среди существующих адресов и ожидающих заявок.

    Поиск выполняется сначала среди адресов, затем среди pending‑заявок.
    Критерии совпадения:
      * если координаты переданы, используется расстояние по формуле haversine.
        Если расстояние меньше threshold_m, считаем точку дубликатом.
      * если координаты отсутствуют, сравниваем названия в нижнем регистре.

    :param name: название новой точки
    :param lat: широта (может быть None)
    :param lon: долгота (может быть None)
    :param threshold_m: максимальное расстояние для совпадения (метры)
    :return: словарь {"type": "address"|"pending", "id": int} или None
    """
    nm = (name or '').strip().lower()
    # Проверяем адреса. В старой схеме базы addresses.zone_id может отсутствовать,
    # поэтому возможен OperationalError при выборке. Отлавливаем и игнорируем.
    try:
        addresses_list = Address.query.all()
    except OperationalError:
        addresses_list = []
    for addr in addresses_list:
        # Сравнение по координатам
        if lat is not None and lon is not None and addr.lat is not None and addr.lon is not None:
            try:
                dist = haversine_m(lat, lon, float(addr.lat), float(addr.lon))
                if dist <= threshold_m:
                    return {'type': 'address', 'id': addr.id}
            except Exception:
                pass
        # Сравнение по названию
        if nm and (addr.name or '').strip().lower() == nm:
            return {'type': 'address', 'id': addr.id}
    # Проверяем pending заявки. Аналогично перехватываем ошибку
    try:
        pending_list = PendingMarker.query.all()
    except OperationalError:
        pending_list = []
    for p in pending_list:
        if lat is not None and lon is not None and p.lat is not None and p.lon is not None:
            try:
                dist = haversine_m(lat, lon, float(p.lat), float(p.lon))
                if dist <= threshold_m:
                    return {'type': 'pending', 'id': p.id}
            except Exception:
                pass
        if nm and (p.name or '').strip().lower() == nm:
            return {'type': 'pending', 'id': p.id}
    return None


@bp.post('/markers')
def add_marker_from_bot() -> Response:
    """
    Создать новую заявку от бота. Проверяет API‑ключ (если задан),
    распознаёт multipart/form-data и JSON, пытается определить
    координаты, ищет дубликаты и кладёт заявку в очередь. Возвращает
    идентификатор заявки.
    """
    # проверка API‑ключа, если настроен
    require_bot_api_key(allow_query_param=True)

    # rate limit (best effort): защищает от случайного/злого флуда
    try:
        ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown").split(",")[0].strip()
        limit = int(current_app.config.get("RATE_LIMIT_BOT_MARKERS_PER_MINUTE", 60))
        ok, _info = check_rate_limit(bucket="bot_markers", ident=ip, limit=limit, window_seconds=60)
        if not ok:
            return jsonify({'error': 'rate_limited'}), 429
    except Exception:
        pass

    # Совместимость схемы: если проект обновили, а app.db остался старый,
    # то в pending_markers/addresses может не быть zone_id. Это приводит к 500 при INSERT.
    # Мягко добавляем недостающие колонки для SQLite.
    try:
        ensure_sqlite_schema_minimal()
    except Exception:
        current_app.logger.exception('ensure_sqlite_schema_minimal failed in /api/bot/markers')
    # список текущих заявок из базы. Если колонка zone_id отсутствует, игнорируем ошибку
    try:
        markers: List[PendingMarker] = PendingMarker.query.all()
    except OperationalError:
        markers = []
    # разбор тела запроса
    if request.files:
        form = request.form or {}
        name = (form.get('name') or form.get('address') or '').strip()
        notes = (form.get('notes') or form.get('description') or '').strip()
        status_str = (form.get('status') or 'Локальный доступ').strip()
        link = (form.get('link') or '').strip()
        category = (form.get('category') or 'Видеонаблюдение').strip()
        # репортёр может быть JSON-строкой
        rep_json = form.get('reporter')
        reporter_in: Dict[str, Any] = {}
        if rep_json:
            try:
                reporter_in = json.loads(rep_json)
            except Exception:
                reporter_in = {}
        reporter = {
            'surname': (reporter_in.get('surname') or '').strip(),
        }
        # Идентификаторы Telegram для идемпотентности (если бот прислал)
        user_id = (form.get('user_id') or '').strip() or None
        message_id = (form.get('message_id') or '').strip() or None
        lat = parse_coord(form.get('lat'))
        lon = parse_coord(form.get('lon'))
        # загрузка фото
        photo_file = request.files.get('photo') or request.files.get('file')
        photo_filename: Optional[str] = None
        if photo_file and '.' in photo_file.filename:
            ext = photo_file.filename.rsplit('.', 1)[1].lower()
            if ext in current_app.config['ALLOWED_EXTENSIONS']:
                unique_name = f"{uuid.uuid4().hex}.{ext}"
                dest_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
                try:
                    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
                    photo_file.save(dest_path)
                    photo_filename = unique_name
                except Exception:
                    photo_filename = None
    else:
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or data.get('address') or '').strip()
        notes = (data.get('notes') or data.get('description') or '').strip()
        status_str = (data.get('status') or 'Локальный доступ').strip()
        link = (data.get('link') or '').strip()
        category = (data.get('category') or 'Видеонаблюдение').strip()
        reporter_in = data.get('reporter') or {}
        reporter = {
            'surname': (reporter_in.get('surname') or '').strip(),
        }
        user_id = str(data.get('user_id')).strip() if data.get('user_id') is not None else None
        user_id = user_id or None
        message_id = str(data.get('message_id')).strip() if data.get('message_id') is not None else None
        message_id = message_id or None
        lat = parse_coord(data.get('lat'))
        lon = parse_coord(data.get('lon'))
        photo_filename = (data.get('photo') or '').strip() or None

    # Идемпотентность: если пришли user_id+message_id и такая заявка уже есть — возвращаем её
    if user_id and message_id:
        try:
            existing = PendingMarker.query.filter_by(user_id=user_id, message_id=message_id).first()
        except OperationalError:
            existing = None
        if existing:
            return jsonify({'pending': existing.id, 'status': 'pending', 'existing': True}), 200
    # если координаты отсутствуют или некорректны — попытаемся геокодировать
    if not in_range(lat, lon):
        coords: Optional[tuple] = None
        if name:
            # сначала офлайн: загружаем offline geocode файл (если есть)
            try:
                offline_path = current_app.config.get('OFFLINE_GEOCODE_FILE')
                if offline_path and os.path.isfile(offline_path):
                    with open(offline_path, 'r', encoding='utf-8') as fh:
                        offline_data = json.load(fh)
                        for entry in offline_data:
                            disp = (entry.get('display_name') or entry.get('address') or '').lower()
                            if name.lower() in disp:
                                lat = parse_coord(entry.get('lat'))
                                lon = parse_coord(entry.get('lon'))
                                coords = (lat, lon)
                                break
            except Exception:
                coords = None
        # если offline ничего не дал — онлайн (Nominatim)
        if not coords and name:
            try:
                params = {'q': name, 'format': 'json', 'limit': 1}
                headers = {'User-Agent': 'map-v12-app'}
                r = requests.get('https://nominatim.openstreetmap.org/search', params=params, headers=headers, timeout=10)
                jdata = r.json()
                if jdata:
                    lat_val = float(jdata[0].get('lat'))
                    lon_val = float(jdata[0].get('lon'))
                    coords = (lat_val, lon_val)
            except Exception:
                coords = None
        if coords:
            lat, lon = coords
        else:
            return jsonify({'error': 'Invalid or missing coordinates for geocoding'}), 400
    # финальная проверка координат
    if not in_range(lat, lon):
        return jsonify({'error': 'Invalid coordinates'}), 400
    # проверка на дубликаты: включено по умолчанию, отключается ?dedupe=0, форсируется ?force=1
    dedupe = str(request.args.get('dedupe', '1')).strip().lower() not in ('0', 'false')
    force = str(request.args.get('force', '0')).strip().lower() in ('1', 'true')
    dup: Optional[Dict[str, Any]] = None
    if dedupe and not force:
        # ищем среди адресов и pending
        dup = find_duplicate_db(name, lat, lon)
    if dup:
        return jsonify({'status': 'duplicate', 'duplicate_of': dup}), 200
    # создаём новую заявку. id автоматически назначит база данных
    pending_kwargs = dict(
        name=name,
        lat=lat,
        lon=lon,
        notes=notes,
        status=status_str,
        link=link,
        category=category,
        photo=photo_filename,
        reporter=reporter.get('surname') or None,
        user_id=user_id,
        message_id=message_id,
    )

    def _insert_pending() -> PendingMarker:
        p = PendingMarker(**pending_kwargs)
        db.session.add(p)
        db.session.flush()  # получаем id
        return p

    try:
        pending = _insert_pending()
    except OperationalError as e:
        # Частый кейс: старая SQLite база без колонки zone_id.
        # Пытаемся "подлечить" и повторить вставку.
        msg = str(e).lower()
        if 'pending_markers' in msg and 'zone_id' in msg and ('no column named' in msg or 'has no column named' in msg):
            db.session.rollback()
            try:
                ensure_sqlite_schema_minimal()
            except Exception:
                current_app.logger.exception('ensure_sqlite_schema_minimal retry failed in /api/bot/markers')
            try:
                pending = _insert_pending()
            except Exception:
                db.session.rollback()
                return jsonify({'error': 'db_schema_outdated', 'message': 'База данных устарела (нет zone_id). Перезапустите сервер.'}), 500
        else:
            raise

    pid = pending.id
    # история: сохраняем статус pending
    hist = PendingHistory(
        pending_id=pid,
        status='pending'
    )
    db.session.add(hist)
    db.session.commit()
    # уведомляем подключённых администраторов о новой заявке
    broadcast_event_sync('pending_created', {
        'id': pid,
        'name': name,
        'lat': lat,
        'lon': lon,
    })
    _schedule_ai_vision_for_pending(pid, photo_filename)
    return jsonify({'pending': pid, 'status': 'pending'}), 200


@bp.get('/webapp')
def bot_webapp() -> Response:
    """Мини-приложение Telegram для отправки заявки."""
    return render_template("webapp.html")


@bp.post('/webapp_submit')
def bot_webapp_submit() -> Response:
    """Приём заявки из Telegram Mini App с проверкой initData."""
    payload = request.get_json(silent=True) or {}
    user_data = getattr(g, "telegram_webapp_user", {}) or {}

    lat = parse_coord((payload.get("coords") or {}).get("lat") if isinstance(payload.get("coords"), dict) else payload.get("lat"))
    lon = parse_coord((payload.get("coords") or {}).get("lon") if isinstance(payload.get("coords"), dict) else payload.get("lon"))
    if not in_range(lat, lon):
        return jsonify({"error": "invalid_coordinates"}), 400

    category = (payload.get("category") or "Прочее").strip()
    description = (payload.get("description") or "").strip()
    photo = (payload.get("photo") or "").strip() or None

    pending = PendingMarker(
        name=f"MiniApp: {category}",
        lat=lat,
        lon=lon,
        notes=description,
        status="webapp",
        link="",
        category=category,
        photo=photo,
        reporter=(user_data.get("last_name") or user_data.get("username") or "").strip() or None,
        user_id=str(user_data.get("id")) if user_data.get("id") is not None else None,
    )
    db.session.add(pending)
    db.session.flush()
    db.session.add(PendingHistory(pending_id=pending.id, status='pending'))
    db.session.commit()

    broadcast_event_sync('pending_created', {
        'id': pending.id,
        'name': pending.name,
        'lat': lat,
        'lon': lon,
    })
    _schedule_ai_vision_for_pending(pending.id, photo)
    return jsonify({"ok": True, "pending": pending.id}), 200


@bp.get('/markers/<int:pid>')
def bot_marker_status(pid: int) -> Response:
    """
    Вернуть статус заявки: pending / approved / rejected / cancelled / unknown.
    Если approved — вернуть id созданного адреса. Требует API‑ключ, если он задан.
    """
    require_bot_api_key(allow_query_param=True)

    # rate limit (best effort)
    try:
        ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown").split(",")[0].strip()
        limit = int(current_app.config.get("RATE_LIMIT_BOT_STATUS_PER_MINUTE", 180))
        ok, _info = check_rate_limit(bucket="bot_marker_status", ident=ip, limit=limit, window_seconds=60)
        if not ok:
            return jsonify({'error': 'rate_limited'}), 429
    except Exception:
        pass
    # Проверяем историю: выбираем последнюю запись для заявки
    rec: Optional[PendingHistory] = PendingHistory.query.filter_by(pending_id=pid).order_by(PendingHistory.id.desc()).first()
    if not rec:
        # Проверим наличие заявки в таблице pending
        p = PendingMarker.query.get(pid)
        if p:
            return jsonify({'status': 'pending', 'pending': pid}), 200
        return jsonify({'status': 'unknown', 'pending': pid}), 200
    status = rec.status
    resp: Dict[str, Any] = {'status': status, 'pending': pid}
    if status == 'approved' and rec.address_id:
        resp['address_id'] = rec.address_id
    return jsonify(resp), 200


@bp.post('/markers/<int:pid>/cancel')
def bot_marker_cancel(pid: int) -> Response:
    """
    Отменить (удалить) заявку из очереди. Требует API‑ключ.
    Если заявка уже одобрена, возвращает conflict.
    """
    require_bot_api_key(allow_query_param=True)

    # rate limit (best effort)
    try:
        ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown").split(",")[0].strip()
        limit = int(current_app.config.get("RATE_LIMIT_BOT_CANCEL_PER_MINUTE", 60))
        ok, _info = check_rate_limit(bucket="bot_marker_cancel", ident=ip, limit=limit, window_seconds=60)
        if not ok:
            return jsonify({'error': 'rate_limited'}), 429
    except Exception:
        pass
    # Проверяем историю: если уже approved, нельзя отменять
    rec: Optional[PendingHistory] = PendingHistory.query.filter_by(pending_id=pid).order_by(PendingHistory.id.desc()).first()
    if rec and rec.status == 'approved':
        return jsonify({'status': 'conflict', 'message': 'already approved', 'address_id': rec.address_id}), 409
    # Удаляем pending заявку, если она существует
    p = PendingMarker.query.get(pid)
    if p:
        db.session.delete(p)
    # Записываем историю отмены
    hist = PendingHistory(
        pending_id=pid,
        status='cancelled'
    )
    db.session.add(hist)
    db.session.commit()
    return jsonify({'status': 'cancelled'}), 200


@bp.get('/my-requests/<string:user_id>')
def bot_my_requests(user_id: str) -> Response:
    """Вернуть список заявок, созданных через бота данным пользователем.

    Фильтрация происходит по Telegram user_id (поле PendingMarker.user_id).
    Доступ защищён API‑ключом BOT_API_KEY.
    """
    require_bot_api_key(allow_query_param=True)

    # rate limit (best effort)
    try:
        ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown").split(",")[0].strip()
        limit = int(current_app.config.get("RATE_LIMIT_BOT_MYREQ_PER_MINUTE", 120))
        ok, _info = check_rate_limit(bucket="bot_my_requests", ident=ip, limit=limit, window_seconds=60)
        if not ok:
            return jsonify({'error': 'rate_limited'}), 429
    except Exception:
        pass

    markers: List[PendingMarker] = (
        PendingMarker.query.filter_by(user_id=str(user_id))
        .order_by(PendingMarker.id.desc())
        .all()
    )
    if not markers:
        return jsonify({'items': []}), 200

    ids = [m.id for m in markers]
    histories: List[PendingHistory] = (
        PendingHistory.query.filter(PendingHistory.pending_id.in_(ids)).all()
    )
    latest_by_pid: Dict[int, PendingHistory] = {}
    for h in histories:
        prev = latest_by_pid.get(h.pending_id)
        if not prev:
            latest_by_pid[h.pending_id] = h
            continue
        # Берём запись с максимальным id как последнюю
        if h.id > prev.id:
            latest_by_pid[h.pending_id] = h

    items: List[Dict[str, Any]] = []
    for m in markers:
        hist = latest_by_pid.get(m.id)
        status = hist.status if hist else 'pending'
        addr_id = hist.address_id if hist else None
        created_at = getattr(m, 'created_at', None)
        items.append(
            {
                'id': m.id,
                'name': m.name or '',
                'status': status,
                'address_id': addr_id,
                'created_at': created_at.isoformat() if created_at else None,
            }
        )

    return jsonify({'items': items}), 200
