"""Маршруты для управления инцидентами.

Этот модуль реализует CRUD‑операции для сущности ``Incident``
и связанные действия: создание, просмотр, назначение наряда и
обновление статуса. В рамках MVP большинство операций доступны
только администраторам (через cookie‑сессию). Будущие версии могут
расширить доступ для патрульных устройств с использованием
заголовков ``X-Device-ID``.
"""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from flask import request, jsonify, abort, session, current_app, Response

from ..helpers import require_admin
from ..extensions import db
from ..realtime.hub import broadcast_sync
from ..realtime.broker import get_broker
from ..security.rate_limit import check_rate_limit
from ..models import Incident, IncidentEvent, IncidentAssignment, DutyShift, TrackerDevice, Object
from ..schemas import IncidentCreateSchema, IncidentChatSendSchema

from . import bp

# SLA settings (in seconds). These could be moved to config later.
SLA_ACCEPT_LIMIT = 5 * 60  # 5 minutes to accept assignment
SLA_ENROUTE_LIMIT = 10 * 60  # 10 minutes to start moving after acceptance
SLA_ON_SCENE_LIMIT = 15 * 60  # 15 minutes to arrive on scene after enroute


# -----------------------------------------------------------------------------
# Rate limit helpers (A2)


def _rate_ident() -> str:
    """Identifier for rate limiting.

    Prefer admin username when in admin session; fall back to device header or IP.
    """
    if session.get('is_admin'):
        user = session.get('admin_username') or session.get('username') or session.get('admin_id') or 'admin'
        return f'admin:{user}'
    did = (request.headers.get('X-Device-ID') or request.headers.get('X-DEVICE-ID') or '').strip()
    if did:
        return f'dev:{did}'
    ip = (request.headers.get('CF-Connecting-IP') or request.remote_addr or 'ip')
    return f'ip:{ip}'


def _rate_limit_or_429(bucket: str, limit: int, window_seconds: int = 60):
    """Return a Flask response (429) if rate limited, else None."""
    try:
        ok, info = check_rate_limit(bucket=bucket, ident=_rate_ident(), limit=int(limit), window_seconds=int(window_seconds))
    except Exception:
        # If rate limiter is broken, do not block the request (best-effort).
        return None
    if ok:
        return None
    resp = jsonify({
        'error': 'rate_limited',
        'message': 'Too many requests',
        'bucket': bucket,
        **info.to_headers(),
    })
    resp.status_code = 429
    try:
        for k, v in info.http_headers().items():
            resp.headers[k] = v
    except Exception:
        pass
    return resp


# -----------------------------------------------------------------------------
# SLA alerts endpoint
#
# Для оперативного отображения просроченных инцидентов в командном центре
# удобно знать количество нарушений SLA по разным этапам. Этот эндпоинт
# собирает активные назначения и подсчитывает, где был нарушен лимит принятия,
# отправления и прибытия. Можно расширить, чтобы возвращать список ID
# инцидентов/назначений для подробной панели.

@bp.get("/sla_overdue")
def api_incidents_sla_overdue():
    """Получить агрегированную статистику по просроченным SLA.

    Доступно администраторам. Возвращает словарь с количеством
    нарушений лимитов на принятие (accept), выезд (enroute) и прибытие
    (on_scene). В дальнейшем может быть расширен для возврата списков
    инцидентов или детальной информации.
    """
    require_admin("viewer")
    from datetime import datetime
    now = datetime.utcnow()
    # Собираем только активные инциденты (не закрытые)
    assignments = (
        IncidentAssignment.query
        .join(Incident, Incident.id == IncidentAssignment.incident_id)
        .filter(Incident.status.in_(["new", "assigned", "enroute", "on_scene", "resolved"]))
        .all()
    )
    accept_breach = 0
    enroute_breach = 0
    onscene_breach = 0
    for a in assignments:
        # Есть assigned_at, но нет accepted_at
        if a.assigned_at and not a.accepted_at:
            if (now - a.assigned_at).total_seconds() > SLA_ACCEPT_LIMIT:
                accept_breach += 1
        # Есть accepted_at, но нет enroute_at
        elif a.accepted_at and not a.enroute_at:
            if (now - a.accepted_at).total_seconds() > SLA_ENROUTE_LIMIT:
                enroute_breach += 1
        # Есть enroute_at, но нет on_scene_at
        elif a.enroute_at and not a.on_scene_at:
            if (now - a.enroute_at).total_seconds() > SLA_ON_SCENE_LIMIT:
                onscene_breach += 1
    return jsonify({
        "accept_breach_count": accept_breach,
        "enroute_breach_count": enroute_breach,
        "on_scene_breach_count": onscene_breach,
    }), 200


@bp.get("/stats")
def api_incidents_stats() -> Any:
    """Получить агрегированную статистику по инцидентам.

    Доступно администраторам. Возвращает общее количество
    инцидентов, а также распределение по статусам и приоритетам.
    Это полезно для KPI‑панелей в командном центре.
    """
    require_admin("viewer")
    total = Incident.query.count()
    # counts by status
    from sqlalchemy import func
    status_counts = (
        db.session.query(Incident.status, func.count(Incident.id))
        .group_by(Incident.status)
        .all()
    )
    pri_counts = (
        db.session.query(Incident.priority, func.count(Incident.id))
        .group_by(Incident.priority)
        .all()
    )
    result = {
        "total": total,
        "by_status": {s if s is not None else "unknown": c for s, c in status_counts},
        "by_priority": {int(p) if p is not None else "unknown": c for p, c in pri_counts},
    }
    return jsonify(result), 200


def _get_current_user() -> tuple[str, str]:
    """Определить отправителя (тип и id) из сессии или заголовков.

    Администраторы идентифицируются через cookie‑сессию
    (``session['is_admin']``); устройства передают ``X-Device-ID``. В дальнейшем
    это можно расширить на bearer‑токены или OAuth.

    Возвращает `(sender_type, sender_id)`. Бросает 403, если
    идентификация не удалась.
    """
    if session.get("is_admin"):
        sender_type = "admin"
        sender_id = str(session.get("admin_id") or session.get("username") or "admin")
        return sender_type, sender_id
    device_id = (request.headers.get("X-Device-ID") or "").strip()
    if device_id:
        return "tracker", device_id
    abort(403)




@bp.post("/<int:incident_id>/chat/send")
def api_incident_chat_send(incident_id: int) -> tuple[Response, int] | Response:
    """Send incident chat message via HTTP -> DB -> Redis Pub/Sub pipeline."""
    require_admin("viewer")

    incident: Incident | None = Incident.query.get(incident_id)
    if incident is None:
        return jsonify({"error": "incident_not_found"}), 404

    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}
    try:
        contract: IncidentChatSendSchema = IncidentChatSendSchema.model_validate(payload)
    except ValidationError as exc:
        return jsonify({"error": "validation_failed", "details": exc.errors()}), 400

    sender_type, fallback_sender_id = _get_current_user()
    role: str = "dispatcher" if sender_type == "admin" else "agent"
    author_id: str = contract.author_id or fallback_sender_id
    author_name: str = str(session.get("admin_username") or session.get("username") or author_id)
    text: str = contract.text

    chat_payload: Dict[str, Any] = {
        "author_id": author_id,
        "author": author_name,
        "role": role,
        "text": text,
    }

    chat_event = IncidentEvent(
        incident_id=incident_id,
        event_type="chat_message",
        payload=chat_payload,
        ts=datetime.utcnow(),
    )
    db.session.add(chat_event)
    db.session.commit()

    timestamp_iso: str = chat_event.ts.isoformat() if chat_event.ts else datetime.utcnow().isoformat()
    message_envelope: Dict[str, Any] = {
        "id": chat_event.id,
        "author": author_name,
        "role": role,
        "text": text,
        "timestamp": timestamp_iso,
    }

    broker_payload: Dict[str, Any] = {
        "event": "CHAT_MESSAGE",
        "incident_id": incident_id,
        "message": message_envelope,
    }

    if not get_broker().publish_event("map_updates", broker_payload):
        current_app.logger.warning("incident chat publish failed", extra={"incident_id": incident_id, "message_id": chat_event.id})

    return jsonify({"status": "delivered"}), 201


@bp.post("")
def api_incidents_create() -> tuple[Response, int] | Response:
    """Создать новый инцидент.

    Доступно только администраторам. Клиент отправляет JSON с
    полями:

      - ``object_id`` — идентификатор связанного объекта (опционально);
      - ``lat``, ``lon`` — координаты (обязательно, если нет ``object_id``);
      - ``address`` — человекочитаемый адрес (строка);
      - ``description`` — описание инцидента;
      - ``priority`` — целочисленный приоритет (1 – высокий, 5 – низкий);

    В ответ возвращается созданный инцидент и событие ``incident_created``
    в realtime‑канал.
    """
    # Проверяем права администратора (editor минимально)
    require_admin("editor")
    rl = _rate_limit_or_429('incidents_write', current_app.config.get('RATE_LIMIT_INCIDENTS_WRITE_PER_MINUTE', 180), 60)
    if rl is not None:
        return rl
    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}

    # Pydantic validation (FastAPI-style): validates key contract fields.
    candidate_location = (payload.get("location") or payload.get("address") or "").strip()
    if not candidate_location and payload.get("lat") is not None and payload.get("lon") is not None:
        candidate_location = f"{payload.get('lat')},{payload.get('lon')}"
    candidate_title = (payload.get("title") or payload.get("address") or "Incident").strip()
    candidate_description = (payload.get("description") or "No description").strip()
    try:
        contract = IncidentCreateSchema.model_validate({
            "title": candidate_title,
            "description": candidate_description,
            "level": payload.get("level", payload.get("priority", 3)),
            "location": candidate_location or "Unknown",
        })
    except ValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.errors()}), 400

    object_id = payload.get("object_id")
    lat = payload.get("lat")
    lon = payload.get("lon")
    address = (payload.get("address") or contract.location).strip() or None
    description = contract.description
    priority = contract.level

    # Нормализуем приоритет (по умолчанию 3)
    try:
        priority = 3 if priority is None else int(priority)
    except Exception:
        priority = 3

    # Если есть object_id и координаты не заданы — попробуем взять их у объекта
    obj = None
    if object_id and (lat is None or lon is None):
        try:
            obj = Object.query.get(object_id)
            if obj is not None:
                lat = obj.lat
                lon = obj.lon
                if not address:
                    address = (obj.name or '').strip() or None
        except Exception:
            obj = None

    status_in = (payload.get("status") or "").strip().lower() or None

    # Разрешаем задать статус при создании (например, closed для архивной записи)
    allowed_statuses = {"new", "assigned", "enroute", "on_scene", "resolved", "closed"}
    status = status_in if (status_in in allowed_statuses) else "new"

    # Если object_id не передан, lat/lon должны быть
    if not object_id and (lat is None or lon is None):
        return jsonify({"error": "lat and lon are required if object_id is not provided"}), 400

    inc = Incident(
        object_id=object_id,
        lat=lat,
        lon=lon,
        address=address,
        description=description,
        priority=priority,
        status=status,
        created_at=datetime.utcnow(),
    )
    db.session.add(inc)
    db.session.commit()

    # Записываем событие
    ev = IncidentEvent(
        incident_id=inc.id,
        event_type="created",
        payload_json=json.dumps({"object_id": object_id}) if object_id else None,
        ts=inc.created_at,
    )
    db.session.add(ev)
    db.session.commit()

    # Отправляем realtime‑уведомление
    try:
        broadcast_sync("incident_created", inc.to_dict())
    except Exception:
        current_app.logger.debug("Failed to broadcast incident_created", exc_info=True)

    return jsonify(inc.to_dict()), 201


@bp.get("")
def api_incidents_list():
    """Получить список инцидентов.

    Поддерживает фильтры по статусу, приоритету, полнотекстовому
    поиску, лимиту и смещению. Доступно администраторам (viewer).
    В будущем можно разрешить патрулям получать свои назначенные
    инциденты.

    Query‑параметры:
      - ``status`` — строка или список через запятую
      - ``priority`` — число или список через запятую
      - ``q`` — строка поиска по адресу и описанию (case‑insensitive)
      - ``from``/``created_from`` — ограничить поиск инцидентов, созданных **не ранее** указанной даты (ISO)
      - ``to``/``created_to`` — ограничить поиск инцидентов, созданных **не позднее** указанной даты (ISO)
      - ``limit`` — максимум записей (по умолчанию 50)
      - ``offset`` — смещение (по умолчанию 0)
    """
    require_admin("viewer")
    status_filter = request.args.get("status")
    priority_filter = request.args.get("priority")
    qterm = (request.args.get("q") or "").strip().lower()
    tagterm = (request.args.get("tag") or request.args.get("object_tag") or "").strip().lower()
    # limits and pagination
    try:
        limit = int(request.args.get("limit") or 50)
    except Exception:
        limit = 50
    try:
        offset = int(request.args.get("offset") or 0)
    except Exception:
        offset = 0

    # optional created_at filters (ISO dates)
    created_from = (request.args.get("from") or request.args.get("created_from") or "").strip()
    created_to = (request.args.get("to") or request.args.get("created_to") or "").strip()

    query = Incident.query
    if status_filter:
        statuses = [s.strip() for s in str(status_filter).split(",") if s.strip()]
        query = query.filter(Incident.status.in_(statuses))
    if priority_filter:
        try:
            priorities = [int(p) for p in str(priority_filter).split(",") if p.strip()]
            query = query.filter(Incident.priority.in_(priorities))
        except Exception:
            pass
    if qterm:
        like = f"%{qterm}%"
        # address and description can be NULL, so guard with ilike
        query = query.filter(
            (Incident.address.ilike(like)) | (Incident.description.ilike(like))
        )

    # optional tag filter (по тегам объекта и имени объекта)
    if tagterm:
        tag_like = f"%{tagterm}%"
        # Incident.object relationship exists; filter incidents whose object has matching tags/name
        query = query.filter(
            Incident.object.has((Object.tags.ilike(tag_like)) | (Object.name.ilike(tag_like)))
        )
    # apply date filters
    from_dt = None
    to_dt = None
    from datetime import datetime
    try:
        if created_from:
            # support date or datetime
            from_dt = datetime.fromisoformat(created_from)
    except Exception:
        from_dt = None
    try:
        if created_to:
            to_dt = datetime.fromisoformat(created_to)
    except Exception:
        to_dt = None
    if from_dt:
        query = query.filter(Incident.created_at >= from_dt)
    if to_dt:
        query = query.filter(Incident.created_at <= to_dt)
    incidents = (
        query.order_by(Incident.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return jsonify([i.to_dict() for i in incidents]), 200


@bp.get("/geo")
def api_incidents_geo():
    """Лёгкий гео‑список инцидентов для слоя на карте.

    В отличие от /api/incidents возвращает *минимум* полей (без таймлайна,
    назначений и вложенных объектов), чтобы быстро перерисовывать слой
    на карте при панорамировании.

    Поддерживаемые параметры:
      - bbox=west,south,east,north (float)  (опционально)
      - status=... (csv)
      - priority=... (csv)
      - tag=... (фильтр по тегам/имени объекта)
      - limit (по умолчанию 500)
    """
    require_admin("viewer")

    # bbox
    bbox = (request.args.get("bbox") or "").strip()
    west = south = east = north = None
    if bbox:
        try:
            parts = [float(x) for x in bbox.split(",")]
            if len(parts) == 4:
                west, south, east, north = parts
        except Exception:
            west = south = east = north = None

    status_filter = request.args.get("status")
    priority_filter = request.args.get("priority")
    tagterm = (request.args.get("tag") or request.args.get("object_tag") or "").strip().lower()

    try:
        limit = int(request.args.get("limit") or 500)
    except Exception:
        limit = 500
    limit = max(1, min(limit, 2000))

    # лёгкая выборка: только нужные колонки
    q = (
        db.session.query(
            Incident.id,
            Incident.lat,
            Incident.lon,
            Incident.status,
            Incident.priority,
            Incident.address,
            Incident.created_at,
            Incident.object_id,
            Object.name.label("object_name"),
            Object.tags.label("object_tags"),
        )
        .outerjoin(Object, Object.id == Incident.object_id)
        .filter(Incident.lat.isnot(None), Incident.lon.isnot(None))
    )

    if status_filter:
        statuses = [s.strip() for s in str(status_filter).split(",") if s.strip()]
        if statuses:
            q = q.filter(Incident.status.in_(statuses))

    if priority_filter:
        try:
            priorities = [int(p) for p in str(priority_filter).split(",") if p.strip()]
            if priorities:
                q = q.filter(Incident.priority.in_(priorities))
        except Exception:
            pass

    if tagterm:
        like = f"%{tagterm}%"
        q = q.filter((Object.tags.ilike(like)) | (Object.name.ilike(like)))

    if west is not None and south is not None and east is not None and north is not None:
        # leaflets bounds: west<=lon<=east, south<=lat<=north
        q = q.filter(Incident.lon >= west, Incident.lon <= east, Incident.lat >= south, Incident.lat <= north)

    rows = q.order_by(Incident.created_at.desc()).limit(limit).all()

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "lat": float(r.lat) if r.lat is not None else None,
                "lon": float(r.lon) if r.lon is not None else None,
                "status": r.status,
                "priority": int(r.priority) if r.priority is not None else None,
                "address": r.address,
                "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
                "object": {
                    "id": r.object_id,
                    "name": r.object_name,
                    "tags": r.object_tags,
                }
                if r.object_id
                else None,
            }
        )

    return jsonify(out), 200


@bp.get("/<int:incident_id>")
def api_incidents_get(incident_id: int):
    """Получить одну запись инцидента вместе с событиями и назначениями."""
    require_admin("viewer")
    inc = Incident.query.filter_by(id=incident_id).first()
    if not inc:
        return jsonify({"error": "incident not found"}), 404
    return jsonify(inc.to_dict()), 200



@bp.route("/<int:incident_id>", methods=["PUT", "PATCH"])
def api_incidents_update(incident_id: int):
    """Обновить инцидент (минимальный CRUD для Command Center).

    Доступно администраторам (editor). Поддерживаемые поля в JSON:
      - lat, lon
      - address
      - description
      - priority
      - status
      - object_id

    Возвращает обновлённый инцидент.
    """
    require_admin("editor")
    rl = _rate_limit_or_429('incidents_write', current_app.config.get('RATE_LIMIT_INCIDENTS_WRITE_PER_MINUTE', 180), 60)
    if rl is not None:
        return rl

    inc = Incident.query.filter_by(id=incident_id).first()
    if not inc:
        return jsonify({"error": "incident not found"}), 404

    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}

    # object_id
    object_id = payload.get("object_id")
    if object_id is not None:
        try:
            inc.object_id = int(object_id) if str(object_id).strip() != "" else None
        except Exception:
            inc.object_id = None

    # coords
    if payload.get("lat") is not None:
        try:
            inc.lat = float(payload.get("lat"))
        except Exception:
            pass
    if payload.get("lon") is not None:
        try:
            inc.lon = float(payload.get("lon"))
        except Exception:
            pass

    # text fields
    if "address" in payload:
        addr = (payload.get("address") or "").strip()
        inc.address = addr or None
    if "description" in payload:
        desc = (payload.get("description") or "").strip()
        inc.description = desc or None

    # priority/status
    if "priority" in payload:
        try:
            inc.priority = int(payload.get("priority")) if payload.get("priority") is not None else None
        except Exception:
            pass
    if "status" in payload:
        st = (payload.get("status") or "").strip().lower()
        if st:
            inc.status = st

    # audit event
    try:
        ev = IncidentEvent(
            incident_id=inc.id,
            event_type="updated",
            payload_json=json.dumps({k: payload.get(k) for k in ["lat","lon","address","description","priority","status","object_id"] if k in payload}),
            ts=datetime.utcnow(),
        )
        db.session.add(ev)
    except Exception:
        pass

    db.session.commit()

    # realtime
    try:
        broadcast_sync("incident_updated", inc.to_dict())
    except Exception:
        current_app.logger.debug("Failed to broadcast incident_updated", exc_info=True)

    return jsonify(inc.to_dict()), 200


@bp.route("/<int:incident_id>", methods=["DELETE"])
def api_incidents_delete(incident_id: int):
    """Удалить инцидент.

    Доступно администраторам (editor). Удаляет инцидент и связанные события/назначения.
    """
    require_admin("editor")
    rl = _rate_limit_or_429('incidents_write', current_app.config.get('RATE_LIMIT_INCIDENTS_WRITE_PER_MINUTE', 180), 60)
    if rl is not None:
        return rl

    inc = Incident.query.filter_by(id=incident_id).first()
    if not inc:
        return jsonify({"error": "incident not found"}), 404

    payload = {"id": inc.id, "lat": inc.lat, "lon": inc.lon}

    try:
        db.session.delete(inc)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "delete_failed", "message": str(e)}), 500

    try:
        broadcast_sync("incident_deleted", payload)
    except Exception:
        current_app.logger.debug("Failed to broadcast incident_deleted", exc_info=True)

    return jsonify({"ok": True, "id": payload["id"]}), 200


@bp.get("/<int:incident_id>/events")
def api_incident_events(incident_id: int):
    """Получить список событий таймлайна инцидента.

    Доступно администраторам (viewer). Возвращает массив событий
    отсортированный по времени возрастания. Каждое событие включает
    поля ``id``, ``event_type``, ``payload`` (распарсенный JSON) и ``ts``
    (ISO‑строка).
    """
    require_admin("viewer")
    inc = Incident.query.filter_by(id=incident_id).first()
    if not inc:
        return jsonify({"error": "incident not found"}), 404
    events = IncidentEvent.query.filter_by(incident_id=incident_id).order_by(IncidentEvent.ts.asc()).all()
    result = []
    for ev in events:
        try:
            payload = json.loads(ev.payload_json) if ev.payload_json else None
        except Exception:
            payload = None
        result.append({
            "id": ev.id,
            "incident_id": ev.incident_id,
            "event_type": ev.event_type,
            "payload": payload,
            "ts": ev.ts.isoformat() if ev.ts else None,
        })
    return jsonify(result), 200


@bp.get("/<int:incident_id>/assignments")
def api_incident_assignments(incident_id: int):
    """Получить назначения для инцидента с вычислением SLA.

    Доступно администраторам. Возвращает список назначений с
    временными метками и полями SLA‑нарушений, чтобы диспетчер
    мог видеть, где требуется внимание. В будущем это может быть
    расширено конфигурацией SLA через переменные окружения.
    """
    require_admin("viewer")
    inc = Incident.query.filter_by(id=incident_id).first()
    if not inc:
        return jsonify({"error": "incident not found"}), 404
    assignments = IncidentAssignment.query.filter_by(incident_id=incident_id).all()
    now = datetime.utcnow()
    result: List[Dict[str, Any]] = []
    for a in assignments:
        # Вычисляем нарушения SLA: если событие ещё не произошло и прошло больше лимита
        sla_accept_breach = False
        sla_enroute_breach = False
        sla_onscene_breach = False
        if a.assigned_at:
            if not a.accepted_at:
                if (now - a.assigned_at).total_seconds() > SLA_ACCEPT_LIMIT:
                    sla_accept_breach = True
            elif not a.enroute_at:
                if (now - a.accepted_at).total_seconds() > SLA_ENROUTE_LIMIT:
                    sla_enroute_breach = True
            elif not a.on_scene_at:
                if (now - a.enroute_at).total_seconds() > SLA_ON_SCENE_LIMIT:
                    sla_onscene_breach = True
        result.append({
            "id": a.id,
            "shift_id": a.shift_id,
            "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
            "accepted_at": a.accepted_at.isoformat() if a.accepted_at else None,
            "enroute_at": a.enroute_at.isoformat() if a.enroute_at else None,
            "on_scene_at": a.on_scene_at.isoformat() if a.on_scene_at else None,
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
            "closed_at": a.closed_at.isoformat() if a.closed_at else None,
            "sla_accept_breach": sla_accept_breach,
            "sla_enroute_breach": sla_enroute_breach,
            "sla_onscene_breach": sla_onscene_breach,
        })
    return jsonify(result), 200


@bp.post("/<int:incident_id>/assign")
def api_incident_assign(incident_id: int):
    """Назначить наряд на инцидент.

    Доступно только администраторам. JSON‑параметры:
      - ``shift_id`` — идентификатор смены/наряда.
    Создаёт запись ``IncidentAssignment`` и обновляет статус инцидента на
    ``assigned``. Если назначение уже существует, возвращает текущее
    назначение без изменений.
    """
    require_admin("editor")
    rl = _rate_limit_or_429('incidents_write', current_app.config.get('RATE_LIMIT_INCIDENTS_WRITE_PER_MINUTE', 180), 60)
    if rl is not None:
        return rl
    inc = Incident.query.filter_by(id=incident_id).first()
    if not inc:
        return jsonify({"error": "incident not found"}), 404
    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}
    shift_id = payload.get("shift_id")
    if not shift_id:
        return jsonify({"error": "shift_id is required"}), 400
    # Проверяем, что shift существует
    shift = DutyShift.query.filter_by(id=shift_id).first()
    if not shift:
        return jsonify({"error": "shift not found"}), 404
    # Проверяем, нет ли уже назначения для этого shift
    assignment = IncidentAssignment.query.filter_by(incident_id=incident_id, shift_id=shift_id).first()
    now = datetime.utcnow()
    if assignment:
        return jsonify(assignment.to_dict()), 200
    assignment = IncidentAssignment(
        incident_id=incident_id,
        shift_id=shift_id,
        assigned_at=now,
    )
    inc.status = "assigned"
    db.session.add(assignment)
    db.session.commit()
    # Добавляем событие
    ev = IncidentEvent(
        incident_id=incident_id,
        event_type="assigned",
        payload_json=json.dumps({"shift_id": shift_id}),
        ts=now,
    )
    db.session.add(ev)
    db.session.commit()
    # Отправляем realtime уведомления
    try:
        broadcast_sync("incident_updated", inc.to_dict())
    except Exception:
        current_app.logger.debug("Failed to broadcast incident_updated", exc_info=True)
    return jsonify(assignment.to_dict()), 201


@bp.post("/<int:incident_id>/status")
def api_incident_update_status(incident_id: int):
    """Обновить статус реакции для назначения.

    Доступ разрешён как администраторам, так и устройствам (patrol).
    JSON‑параметры:
      - ``shift_id`` — идентификатор смены; если не передан, то
        попытка найти назначение для текущего пользователя по
        ``_get_current_user``;
      - ``status`` — новое состояние: one of
        ``accepted``, ``enroute``, ``on_scene``, ``resolved``, ``closed``.

    Функция обновляет соответствующее поле в ``IncidentAssignment``,
    обновляет статус инцидента и записывает событие ``IncidentEvent``.
    Возвращает обновлённое назначение.
    """
    # Определяем пользователя: админ или устройство
    sender_type, sender_id = _get_current_user()
    rl = _rate_limit_or_429('incidents_write', current_app.config.get('RATE_LIMIT_INCIDENTS_WRITE_PER_MINUTE', 180), 60)
    if rl is not None:
        return rl
    inc = Incident.query.filter_by(id=incident_id).first()
    if not inc:
        return jsonify({"error": "incident not found"}), 404
    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}
    status = (payload.get("status") or "").strip().lower()
    shift_id = payload.get("shift_id")
    if not status:
        return jsonify({"error": "status is required"}), 400
    # Определяем допустимые статусы
    allowed = {
        'accepted': 'accepted_at',
        'enroute': 'enroute_at',
        'on_scene': 'on_scene_at',
        'resolved': 'resolved_at',
        'closed': 'closed_at',
    }
    if status not in allowed:
        return jsonify({"error": "invalid status"}), 400
    # Находим назначение
    assignment: Optional[IncidentAssignment] = None
    if shift_id:
        assignment = IncidentAssignment.query.filter_by(incident_id=incident_id, shift_id=shift_id).first()
    else:
        # Если shift_id не передан, ищем назначение по отправителю
        if sender_type == 'tracker':
            # Найти устройство по public_id (sender_id) и определить пользователя (user_id)
            device = TrackerDevice.query.filter_by(public_id=sender_id).first()
            if device:
                # Найти активную смену пользователя
                shift = DutyShift.query.filter_by(user_id=device.user_id, ended_at=None).order_by(DutyShift.started_at.desc()).first()
                if shift:
                    assignment = IncidentAssignment.query.filter_by(incident_id=incident_id, shift_id=shift.id).first()
    if not assignment:
        return jsonify({"error": "assignment not found"}), 404
    now = datetime.utcnow()
    setattr(assignment, allowed[status], now)
    # Обновляем статус инцидента в зависимости от действия
    if status == 'accepted':
        inc.status = 'assigned'
    elif status == 'enroute':
        inc.status = 'enroute'
    elif status == 'on_scene':
        inc.status = 'on_scene'
    elif status == 'resolved':
        inc.status = 'resolved'
    elif status == 'closed':
        inc.status = 'closed'
    # Записываем событие
    ev = IncidentEvent(
        incident_id=incident_id,
        event_type=status,
        payload_json=json.dumps({"shift_id": assignment.shift_id}),
        ts=now,
    )
    db.session.add(ev)
    db.session.commit()
    # realtime update
    try:
        broadcast_sync("incident_updated", inc.to_dict())
    except Exception:
        current_app.logger.debug("Failed to broadcast incident_updated", exc_info=True)
    return jsonify(assignment.to_dict()), 200