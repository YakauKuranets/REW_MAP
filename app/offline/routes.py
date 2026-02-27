"""
Минимальный набор маршрутов для офлайн‑модуля.

Пока реализована только выдача списка городов для загрузки
офлайн‑карт. При желании сюда можно перенести остальные
функции (stream загрузки, удаление, управление наборами и т.п.).
"""

from __future__ import annotations

import json
import math
import os
import shutil
import re
import time
from typing import Any, Dict, List, Optional

import requests
from compat_flask import Response, current_app, jsonify, request, session

from ..helpers import require_admin
from ..audit.logger import log_admin_action
from ..models import Address
from ..extensions import db

from . import bp


@bp.get('/cities')
def offline_cities():
    """Вернуть список городов и регионов, доступных для офлайн‑режима."""
    return jsonify([
        {'code': 'minsk', 'name': 'Минск'},
        {'code': 'vitebsk', 'name': 'Витебск'},
        {'code': 'grodno', 'name': 'Гродно'},
        {'code': 'gomel', 'name': 'Гомель'},
        {'code': 'brest', 'name': 'Брест'},
        {'code': 'mogilev', 'name': 'Могилёв'},
        {'code': 'minsk_region', 'name': 'Минская область'},
        {'code': 'vitebsk_region', 'name': 'Витебская область'},
        {'code': 'grodno_region', 'name': 'Гродненская область'},
        {'code': 'gomel_region', 'name': 'Гомельская область'},
        {'code': 'brest_region', 'name': 'Брестская область'},
        {'code': 'mogilev_region', 'name': 'Могилёвская область'},
    ])

# ---------------------------------------------------------------------------
# Константы для офлайн‑карт и геокодирования
# ---------------------------------------------------------------------------

# Границы городов и регионов для загрузки тайлов. Эти координаты
# обрезают область скачивания, чтобы ограничить количество тайлов.
# Значения подобраны из оригинального приложения и совпадают с теми,
# что были в монолитной версии.
CITY_BOUNDS: Dict[str, tuple] = {
    'minsk': (53.7, 53.9, 27.45, 27.65),
    'vitebsk': (55.09, 55.29, 30.10, 30.30),
    'grodno': (53.6, 53.8, 23.6, 23.9),
    'gomel': (52.35, 52.55, 30.90, 31.10),
    'brest': (52.0, 52.2, 23.6, 23.8),
    'mogilev': (53.85, 54.05, 30.2, 30.4),
    'minsk_region': (53.0, 55.5, 26.0, 29.5),
    'vitebsk_region': (55.0, 56.5, 28.0, 31.5),
    'grodno_region': (52.8, 54.7, 23.0, 26.0),
    'gomel_region': (52.0, 54.0, 28.0, 32.0),
    'brest_region': (51.6, 53.5, 23.0, 26.0),
    'mogilev_region': (53.0, 54.5, 28.5, 32.0),
}

# ---------------------------------------------------------------------------
# Функции для управления активным набором тайлов
# ---------------------------------------------------------------------------

# Безопасные имена наборов: только латиница/цифры/дефис/подчёркивание
_SAFE_SET_RE = re.compile(r"^[a-z0-9_-]{1,64}$")


def _safe_set_name(raw: str) -> str | None:
    """Нормализовать имя набора офлайн‑тайлов.

    Возвращает:
    - ''  -> набор по умолчанию ('download')
    - str -> валидное имя набора
    - None -> имя невалидно (попытка path traversal/мусорные символы)
    """
    if raw is None:
        return ''
    name = (raw or '').strip().lower()
    if not name or name == 'download':
        return ''
    if _SAFE_SET_RE.fullmatch(name):
        return name
    return None


def _safe_tiles_set_dir(sets_dir: str, set_name: str) -> str | None:
    """Безопасно построить путь к директории набора внутри sets_dir."""
    if not sets_dir or not set_name:
        return None
    base_real = os.path.realpath(sets_dir)
    target_real = os.path.realpath(os.path.join(sets_dir, set_name))
    if not target_real.startswith(base_real + os.sep):
        return None
    return target_real


def _rate_limit(key: str, seconds: int = 2) -> tuple[bool, int]:
    """Простейший лимитер по сессии (чтобы не спамить тяжёлыми операциями)."""
    try:
        now = time.time()
        last = float(session.get(key) or 0)
        if now - last < seconds:
            return False, int(seconds - (now - last) + 0.999)
        session[key] = now
        return True, 0
    except Exception:
        return True, 0


def _atomic_write_text(path: str, content: str) -> None:
    """Атомарно записать текстовый файл (temp -> replace)."""
    if not path:
        return
    dir_name = os.path.dirname(path) or '.'
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix='.tmp_', dir=dir_name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(content)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except Exception:
                pass
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def _atomic_write_json(path: str, obj: Any) -> None:
    """Атомарно записать JSON."""
    _atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))

def get_active_tiles_set() -> str:
    """Прочитать имя активного офлайн‑набора тайлов из файла.

    Если файл не существует или пустой, возвращается пустая строка,
    что соответствует набору по умолчанию 'download'.
    """
    path = current_app.config.get('ACTIVE_TILES_FILE')
    if not path:
        return ''
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            raw = fh.read().strip()
            safe = _safe_set_name(raw)
            return safe if safe is not None else ''
    except Exception:
        return ''


def set_active_tiles_set(name: str) -> None:
    """Установить активный офлайн‑набор тайлов (безопасно и атомарно).

    Имя набора записывается в конфигурационный файл. Пустая строка
    или 'download' сбрасывают активный набор к набору по умолчанию.
    Невалидное имя также приводит к сбросу (защита от path traversal).
    """
    path = current_app.config.get('ACTIVE_TILES_FILE')
    if not path:
        return

    safe = _safe_set_name(name)
    if safe is None:
        safe = ''
    _atomic_write_text(path, safe.strip())


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def deg2num(lat_deg: float, lon_deg: float, zoom: int) -> tuple:
    """Преобразовать географические координаты в номер тайла (x, y).

    Используется для вычисления диапазона тайлов, которые нужно
    скачать, ограничивая область интереса. Формула взята из
    спецификации OSM.
    """
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = (lon_deg + 180.0) / 360.0 * n
    ytile = (1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n
    return xtile, ytile


def summarise_tiles(dir_path: str) -> Dict[str, Any]:
    """Собрать статистику по тайлам в каталоге.

    Возвращает словарь с ключами levels (список объектов z/tiles),
    total_tiles (общее количество тайлов) и size_bytes (общий размер в байтах).
    """
    levels: List[Dict[str, Any]] = []
    total_tiles = 0
    total_size = 0
    try:
        if os.path.isdir(dir_path):
            for name in os.listdir(dir_path):
                z_dir = os.path.join(dir_path, name)
                if not os.path.isdir(z_dir):
                    continue
                try:
                    z_int = int(name)
                except Exception:
                    continue
                tile_count = 0
                level_size = 0
                for root, dirs, files in os.walk(z_dir):
                    for f in files:
                        if f.lower().endswith('.png'):
                            tile_count += 1
                            try:
                                size = os.path.getsize(os.path.join(root, f))
                                level_size += size
                            except Exception:
                                pass
                if tile_count > 0:
                    levels.append({'z': z_int, 'tiles': tile_count})
                    total_tiles += tile_count
                    total_size += level_size
            levels.sort(key=lambda d: d['z'])
    except Exception:
        pass
    return {
        'levels': levels,
        'total_tiles': total_tiles,
        'size_bytes': total_size,
    }


# ---------------------------------------------------------------------------
# Эндпоинты офлайн‑карт
# ---------------------------------------------------------------------------

@bp.get('/map/stream')
def offline_map_stream() -> Response:
    """
    Скачать тайлы для выбранного города и диапазона масштабов.

    Отправляет клиенту поток серверных событий (Server-Sent Events)
    с данными прогресса и завершения.  Тайлы сохраняются в каталог
    по умолчанию или в указанный набор.  Область ограничивается
    выбранным городом из CITY_BOUNDS.
    """
    require_admin()
    ok, wait = _rate_limit('rl_offline_map_stream', seconds=3)
    if not ok:
        return jsonify({'error': 'too many requests', 'retry_after': wait}), 429

    city = (request.args.get('city') or 'minsk').lower()
    zmin = request.args.get('zmin', '6')
    zmax = request.args.get('zmax', '14')
    try:
        zmin_int = max(0, min(18, int(zmin)))
    except Exception:
        zmin_int = 6
    try:
        zmax_int = max(0, min(18, int(zmax)))
    except Exception:
        zmax_int = 14
    # ограничиваем максимальный зум для областей
    if city.endswith('_region'):
        zmax_int = min(zmax_int, 16)
    # нормализуем диапазон
    if zmin_int > zmax_int:
        zmin_int, zmax_int = zmax_int, zmin_int
    # получаем границы для города; если нет — используем Минск
    bounds = CITY_BOUNDS.get(city, CITY_BOUNDS['minsk'])
    lat_min, lat_max, lon_min, lon_max = bounds
    # определяем набор для хранения
    set_name = (request.args.get('set') or '').strip()
    if set_name:
        # оставляем только буквы, цифры, дефис и подчёркивание
        filtered = ''.join(ch for ch in set_name if ch.isalnum() or ch in ('-', '_')).lower()
        set_name = filtered or 'download'
    if not set_name:
        set_name = f"{city}_z{zmax_int}"
    if set_name == 'download':
        target_dir = current_app.config.get('DOWNLOAD_TILES_DIR')
    else:
        sets_dir = current_app.config.get('TILES_SETS_DIR')
        # sets_dir может быть не задан в конфиге
        if not sets_dir:
            return jsonify({'error': 'tiles sets dir is not configured'}), 500
        os.makedirs(sets_dir, exist_ok=True)
        # set_name уже фильтруется выше, но дополнительно проверим строго
        safe = _safe_set_name(set_name)
        if safe is None or safe == '':
            return jsonify({'error': 'invalid set name'}), 400
        target_dir = _safe_tiles_set_dir(sets_dir, safe)
        if not target_dir:
            return jsonify({'error': 'invalid set path'}), 400
    # функция генерации SSE
    def generate():
        total = 0
        ranges: List[tuple] = []
        # вычисляем количество тайлов и диапазоны
        for z in range(zmin_int, zmax_int + 1):
            try:
                x_min_f, y_max_f = deg2num(lat_max, lon_min, z)
                x_max_f, y_min_f = deg2num(lat_min, lon_max, z)
            except Exception:
                continue
            x0 = int(math.floor(min(x_min_f, x_max_f)))
            x1 = int(math.floor(max(x_min_f, x_max_f)))
            y0 = int(math.floor(min(y_min_f, y_max_f)))
            y1 = int(math.floor(max(y_min_f, y_max_f)))
            # ограничиваем диапазон индексов
            limit = 2 ** z
            x0 = max(0, min(x0, limit - 1))
            x1 = max(0, min(x1, limit - 1))
            y0 = max(0, min(y0, limit - 1))
            y1 = max(0, min(y1, limit - 1))
            if x1 < x0 or y1 < y0:
                continue
            total += (x1 - x0 + 1) * (y1 - y0 + 1)
            ranges.append((z, x0, x1, y0, y1))
        done = 0
        for (z, x0, x1, y0, y1) in ranges:
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    done += 1
                    # путь к файлу
                    dir_z = os.path.join(target_dir, str(z), str(x))
                    file_path = os.path.join(dir_z, f"{y}.png")
                    # если файл уже существует — пропускаем загрузку
                    if not os.path.isfile(file_path):
                        try:
                            # создаём каталоги
                            os.makedirs(dir_z, exist_ok=True)
                            url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                            r = requests.get(url, timeout=15)
                            if r.ok:
                                with open(file_path, 'wb') as fh:
                                    fh.write(r.content)
                        except Exception:
                            # ошибки при загрузке игнорируем
                            pass
                    # отправляем прогресс
                    pct = int(done * 100 / total) if total else 100
                    payload = {'type': 'progress', 'pct': pct, 'done': done, 'total': total}
                    yield f"data: {json.dumps(payload)}\n\n"
        # завершение
        yield 'data: {"type":"done"}\n\n'
    return Response(generate(), mimetype='text/event-stream')


@bp.post('/map:delete')
def offline_map_delete() -> Response:
    """Удалить все загруженные тайлы карты (download)."""
    require_admin()
    ok, wait = _rate_limit('rl_offline_map_delete', seconds=2)
    if not ok:
        return jsonify({'error': 'too many requests', 'retry_after': wait}), 429
    try:
        path = current_app.config.get('DOWNLOAD_TILES_DIR')
        if path and os.path.isdir(path):
            shutil.rmtree(path)
    except Exception:
        pass
    log_admin_action('offline.map_delete_all')
    return ('', 204)


@bp.get('/map/files')
def offline_map_files() -> Response:
    """Вернуть список тайлов по уровням для директории download.

    Требует административных прав, так как доступ к информации
    об офлайн‑данных должен быть ограничен.
    """
    require_admin()
    summary = summarise_tiles(current_app.config.get('DOWNLOAD_TILES_DIR'))
    return jsonify({
        'levels': summary['levels'],
        'total_tiles': summary['total_tiles'],
        'size_bytes': summary['size_bytes'],
    })


@bp.get('/map/sets')
def offline_map_sets() -> Response:
    """Вернуть список доступных наборов офлайн‑карт и активный набор.

    Только администратор может просматривать наборы.  В ответе
    присутствует список наборов, каждый со статистикой по тайлам, и
    имя активного набора.
    """
    require_admin()
    sets: List[Dict[str, Any]] = []
    # набор по умолчанию
    default_summary = summarise_tiles(current_app.config.get('DOWNLOAD_TILES_DIR'))
    sets.append({'name': 'download', **default_summary})
    # named sets
    sets_dir = current_app.config.get('TILES_SETS_DIR')
    if sets_dir and os.path.isdir(sets_dir):
        try:
            for name in os.listdir(sets_dir):
                safe = _safe_set_name(name)
                if safe is None or safe == '':
                    continue
                set_dir = _safe_tiles_set_dir(sets_dir, safe) or ''
                if not set_dir or not os.path.isdir(set_dir):
                    continue
                summary = summarise_tiles(set_dir)
                sets.append({'name': name, **summary})
        except Exception:
            pass
    active = get_active_tiles_set() or 'download'
    return jsonify({'sets': sets, 'active': active})


@bp.post('/map/activate')
def offline_map_activate() -> Response:
    """Активировать указанный набор офлайн‑карт.

    В теле запроса (JSON или form-data) должен присутствовать ключ
    `set`. Пустое значение или 'download' сбрасывает активный набор.
    Требует административных прав.
    """
    require_admin()
    ok, wait = _rate_limit('rl_offline_map_activate', seconds=2)
    if not ok:
        return jsonify({'error': 'too many requests', 'retry_after': wait}), 429

    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}
    raw = (data.get('set') or request.form.get('set') or '').strip()

    safe = _safe_set_name(raw)
    if safe is None:
        return jsonify({'error': 'invalid set name'}), 400

    # reset to default
    if safe == '':
        set_active_tiles_set('')
        return jsonify({'status': 'ok', 'active': 'download'})

    sets_dir = current_app.config.get('TILES_SETS_DIR')
    if not sets_dir:
        return jsonify({'error': 'tiles sets dir is not configured'}), 500

    dir_path = _safe_tiles_set_dir(sets_dir, safe)
    if not dir_path:
        return jsonify({'error': 'invalid set path'}), 400
    if not os.path.isdir(dir_path):
        return jsonify({'error': 'set not found'}), 404

    set_active_tiles_set(safe)
    active = get_active_tiles_set() or 'download'
    return jsonify({'status': 'ok', 'active': active})




@bp.delete('/map/sets/<set_name>')
def offline_map_delete_set(set_name: str) -> Response:
    """Удалить указанный именованный набор офлайн‑тайлов.

    Набор 'download' удалить невозможно. Если удаляемый набор был
    активным, активный набор сбрасывается. Требует административных прав.
    """
    require_admin()
    ok, wait = _rate_limit('rl_offline_map_delete_set', seconds=2)
    if not ok:
        return jsonify({'error': 'too many requests', 'retry_after': wait}), 429

    safe = _safe_set_name(set_name)
    if safe is None or safe == '':
        return jsonify({'error': 'invalid set name'}), 400

    sets_dir = current_app.config.get('TILES_SETS_DIR')
    if not sets_dir:
        return jsonify({'error': 'tiles sets dir is not configured'}), 500

    dir_path = _safe_tiles_set_dir(sets_dir, safe)
    if not dir_path:
        return jsonify({'error': 'invalid set path'}), 400

    try:
        if os.path.isdir(dir_path):
            shutil.rmtree(dir_path)
    except Exception:
        # не раскрываем детали файловой системы
        return jsonify({'error': 'failed to delete set'}), 500

    # сброс активного набора, если нужно
    if (get_active_tiles_set() or '') == safe:
        set_active_tiles_set('')

    log_admin_action('offline.map_delete_set', {'set': safe})
    return jsonify({'status': 'ok'})




# ---------------------------------------------------------------------------
# Эндпоинты офлайн‑геокодера
# ---------------------------------------------------------------------------

@bp.get('/geocode/files')
def offline_geocode_files() -> Response:
    """Вернуть информацию о файле офлайн‑геокодирования.

    Администратор получает список файлов (обычно один), размер и
    количество записей.  Если файла нет, возвращаются пустые поля.
    """
    require_admin()
    files: List[str] = []
    entries: Optional[int] = None
    size_bytes: Optional[int] = None
    modified: Optional[str] = None
    path = current_app.config.get('OFFLINE_GEOCODE_FILE')
    if path and os.path.isfile(path):
        files.append(os.path.basename(path))
        try:
            size_bytes = os.path.getsize(path)
        except Exception:
            size_bytes = None
        try:
            mtime = os.path.getmtime(path)
            modified = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
        except Exception:
            modified = None
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
                if isinstance(data, list):
                    entries = len(data)
        except Exception:
            entries = None
    return jsonify({'files': files, 'entries': entries, 'size_bytes': size_bytes, 'modified': modified})


@bp.get('/geocode/entries')
def offline_geocode_entries() -> Response:
    """Вернуть список записей в офлайн‑файле геокодера.

    Администратор получает список объектов с полями id, display_name,
    lat и lon.  Идентификатор — это индекс записи в массиве.
    """
    require_admin()
    entries: List[Dict[str, Any]] = []
    path = current_app.config.get('OFFLINE_GEOCODE_FILE')
    if path and os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
                if isinstance(data, list):
                    for idx, rec in enumerate(data):
                        display_name = rec.get('display_name') or rec.get('address') or ''
                        entries.append({'id': idx, 'display_name': display_name, 'lat': rec.get('lat'), 'lon': rec.get('lon')})
        except Exception:
            pass
    return jsonify({'entries': entries})


@bp.delete('/geocode/entries/<int:idx>')
def offline_geocode_delete_entry(idx: int) -> Response:
    """Удалить одну запись из офлайн‑геокодера по её индексу.

    После удаления файл перезаписывается и список в памяти не
    обновляется (чтение происходит по файлу при обращении). Требует
    административных прав.
    """
    require_admin()
    path = current_app.config.get('OFFLINE_GEOCODE_FILE')
    remaining: Optional[int] = None
    if path and os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            if isinstance(data, list) and 0 <= idx < len(data):
                data.pop(idx)
                try:
                    with open(path, 'w', encoding='utf-8') as fh:
                        json.dump(data, fh, ensure_ascii=False, indent=2)
                    remaining = len(data)
                except Exception:
                    pass
        except Exception:
            pass
    return jsonify({'status': 'ok', 'remaining': remaining})


@bp.post('/geocode:delete')
def offline_geocode_delete() -> Response:
    """Удалить файл офлайн‑геокода и очистить кэш."""
    require_admin()
    ok, wait = _rate_limit('rl_offline_geocode_delete', seconds=2)
    if not ok:
        return jsonify({'error': 'too many requests', 'retry_after': wait}), 429
    try:
        path = current_app.config.get('OFFLINE_GEOCODE_FILE')
        if path and os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass
    log_admin_action('offline.geocode_delete')
    return ('', 204)


@bp.get('/geocode/stream')
def offline_geocode_stream() -> Response:
    """Построить офлайн‑базу геокода на основе текущих адресов.

    Проходит по всем сохранённым адресам, пытаясь определить
    координаты. Если они есть, берёт существующие значения,
    иначе делает запрос к Nominatim.  Результаты записывает в
    файл OFFLINE_GEOCODE_FILE.  Клиенту отправляются события
    прогресса, затем завершения.
    
    Важно: т.к. генератор выполняется вне контекста запроса,
    необходимые параметры (список адресов и путь к файлу)
    извлекаются заранее, до создания генератора. Это избегает
    ошибок "Working outside of application context".
    """
    require_admin()
    ok, wait = _rate_limit('rl_offline_geocode_stream', seconds=3)
    if not ok:
        return jsonify({'error': 'too many requests', 'retry_after': wait}), 429

    # Получаем адреса из базы данных до начала генерации. Если
    # таблица адресов пуста, база геокодирования также будет
    # пустой. Сохраняем список как словари для упрощения обработки.
    items = [addr.to_dict() for addr in Address.query.all()]
    total = len(items)
    offline_path: Optional[str] = current_app.config.get('OFFLINE_GEOCODE_FILE')

    def generate():
        done = 0
        offline_entries: List[Dict[str, Any]] = []
        for it in items:
            name = (it.get('name') or it.get('address') or '').strip()
            lat = it.get('lat')
            lon = it.get('lon')
            # если координаты отсутствуют, пытаемся геокодировать
            if (lat is None or lon is None) and name:
                try:
                    params = {'q': name, 'format': 'json', 'limit': 1, 'accept-language': 'ru'}
                    r = requests.get(
                        'https://nominatim.openstreetmap.org/search',
                        params=params,
                        headers={'User-Agent': 'map-v12-offline'},
                        timeout=10,
                    )
                    if r.ok:
                        data = r.json()
                        if isinstance(data, list) and data:
                            lat = float(data[0].get('lat', lat))
                            lon = float(data[0].get('lon', lon))
                except Exception:
                    pass
            if lat is not None and lon is not None:
                offline_entries.append({'display_name': name, 'lat': lat, 'lon': lon})
            done += 1
            pct = int(done * 100 / total) if total else 100
            step_msg = f'{done}/{total}'
            payload = {'type': 'progress', 'pct': pct, 'step': step_msg}
            yield f"data: {json.dumps(payload)}\n\n"
        # сохраняем файл офлайн‑геокода (если путь задан)
        if offline_path:
            try:
                _atomic_write_json(offline_path, offline_entries)
            except Exception:
                pass
        yield 'data: {"type":"done"}\n\n'

    return Response(generate(), mimetype='text/event-stream')
