"""
Маршруты для работы с адресами.

Этот модуль реализует REST‑API для списка адресов. Адреса хранятся
в JSON‑файле, поэтому операции чтения и записи производятся через
функции модуля storage. Для операций, требующих авторизации,
используется вспомогательная функция require_admin().
"""

import os
import uuid
from io import StringIO
from typing import Any, Dict, List, Optional

from compat_flask import Response, jsonify, request, current_app, send_from_directory

from ..helpers import (
    parse_coord,
    in_range,
    filter_items,
    get_item,
    require_admin,
    ensure_zone_access,
    get_current_admin,
)
from ..models import Address
from ..sockets import broadcast_event_sync
from ..extensions import db

from . import bp


def _allowed_file(filename: str) -> bool:
    """Проверить, имеет ли файл допустимое расширение."""
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config['ALLOWED_EXTENSIONS']


@bp.get('/addresses')
def list_addresses() -> Response:
    """Вернуть список адресов с поддержкой фильтров и (опционально) пагинацией.

    Если в запросе указаны параметры page/per_page, возвращается объект вида:
        {
            "items": [...],
            "page": 1,
            "per_page": 50,
            "total": 123
        }

    Если параметров пагинации нет — поведение как раньше: возвращается
    просто список адресов.
    """
    # Параметры фильтрации
    q = (request.args.get('q') or '').strip()
    category = (request.args.get('category') or '').strip()
    status = (request.args.get('status') or '').strip()

    query = Address.query

    # Ограничение по зонам для не-superadmin администраторов:
    # superadmin видит все адреса, остальные — только в своих зонах.
    admin = get_current_admin()
    if admin is not None and getattr(admin, 'role', None) != 'superadmin':
        zone_ids = [z.id for z in admin.zones]
        if zone_ids:
            query = query.filter(Address.zone_id.in_(zone_ids))
        else:
            # Нет привязанных зон — адреса недоступны.
            query = query.filter(False)

    if q:
        like_pattern = f"%{q}%"
        query = query.filter(
            (Address.name.ilike(like_pattern)) | (Address.notes.ilike(like_pattern))
        )
    if category:
        query = query.filter(Address.category == category)
    if status:
        query = query.filter(Address.status == status)

    # Базовая сортировка: сначала новые (по дате создания, потом по id)
    query = query.order_by(Address.created_at.desc(), Address.id.desc())

    # Опциональная пагинация
    page_raw = request.args.get('page')
    per_page_raw = request.args.get('per_page')
    if page_raw or per_page_raw:
        try:
            page = int(page_raw or 1)
        except (TypeError, ValueError):
            page = 1
        try:
            per_page = int(per_page_raw or 100)
        except (TypeError, ValueError):
            per_page = 100

        page = max(page, 1)
        # Не даём сильно раздувать страницу
        per_page = min(max(per_page, 1), 500)

        total = query.count()
        items = [
            addr.to_dict()
            for addr in query.offset((page - 1) * per_page).limit(per_page).all()
        ]
        return jsonify(
            {
                "items": items,
                "page": page,
                "per_page": per_page,
                "total": total,
            }
        )

    # Старое поведение: вернуть все элементы списком
    items = [addr.to_dict() for addr in query.all()]
    return jsonify(items)


@bp.post('/addresses')
def create_address() -> Response:
    """Создать новый адрес. Только администратор."""
    require_admin()
    # multipart: обрабатываем формы и файлы
    if request.files:
        form = request.form or {}
        name = (form.get('name') or form.get('address') or '').strip()
        notes = (form.get('notes') or form.get('description') or '').strip()
        lat = parse_coord(form.get('lat'))
        lon = parse_coord(form.get('lon'))
        status_str = (form.get('status') or '').strip()
        link = (form.get('link') or '').strip()
        category = (form.get('category') or '').strip()
        # зона (опционально)
        zone_id = None
        if 'zone_id' in form:
            try:
                raw_zone = form.get('zone_id')
                if raw_zone not in (None, ''):
                    zone_id = int(raw_zone)
            except (TypeError, ValueError):
                zone_id = None
        if zone_id is not None:
            ensure_zone_access(zone_id)
        # проверка координат
        if not in_range(lat, lon):
            return jsonify({'error': 'Invalid coordinates'}), 400
        # обработка загружаемого изображения
        photo_file = request.files.get('photo') or request.files.get('file')
        photo_filename: Optional[str] = None
        if photo_file and _allowed_file(photo_file.filename):
            ext = photo_file.filename.rsplit('.', 1)[1].lower()
            unique_name = f"{uuid.uuid4().hex}.{ext}"
            dest_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
            try:
                os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
                photo_file.save(dest_path)
                photo_filename = unique_name
            except Exception:
                photo_filename = None
        # создаём запись в базе
        address = Address(
            name=name,
            lat=lat,
            lon=lon,
            notes=notes,
            status=status_str,
            link=link,
            category=category,
            zone_id=zone_id,
            photo=photo_filename,
        )
        db.session.add(address)
        db.session.commit()
        # Рассылаем событие о создании адреса через WebSocket
        try:
            broadcast_event_sync('address_created', address.to_dict())
        except Exception:
            current_app.logger.exception('Ошибка отправки события address_created')
        return jsonify({'id': address.id}), 200
    # JSON
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or data.get('address') or '').strip()
    notes = (data.get('notes') or data.get('description') or '').strip()
    lat = parse_coord(data.get('lat'))
    lon = parse_coord(data.get('lon'))
    status_str = (data.get('status') or '').strip()
    link = (data.get('link') or '').strip()
    category = (data.get('category') or '').strip()
    zone_id = None
    if 'zone_id' in data:
        try:
            raw_zone = data.get('zone_id')
            if raw_zone not in (None, ''):
                zone_id = int(raw_zone)
        except (TypeError, ValueError):
            zone_id = None
    if zone_id is not None:
        ensure_zone_access(zone_id)
    if not in_range(lat, lon):
        return jsonify({'error': 'Invalid coordinates'}), 400
    address = Address(
        name=name,
        lat=lat,
        lon=lon,
        notes=notes,
        status=status_str,
        link=link,
        category=category,
        zone_id=zone_id,
    )
    db.session.add(address)
    db.session.commit()
    try:
        broadcast_event_sync('address_created', address.to_dict())
    except Exception:
        current_app.logger.exception('Ошибка отправки события address_created')
    return jsonify({'id': address.id}), 200


@bp.route('/addresses/<item_id>', methods=['PUT', 'DELETE'])
def update_delete_address(item_id: str) -> Response:
    """Обновить или удалить конкретный адрес. Только администратор."""
    # Запрашиваем объект по ID
    address = Address.query.get(item_id)
    if not address:
        return jsonify({'error': 'Not found'}), 404
    # Проверяем доступ к текущей зоне адреса (если она задана)
    if address.zone_id is not None:
        ensure_zone_access(address.zone_id)
    if request.method == 'DELETE':
        require_admin()
        # Удаляем адрес из базы
        db.session.delete(address)
        db.session.commit()
        # событие об удалении адреса
        try:
            broadcast_event_sync('address_deleted', {'id': int(item_id)})
        except Exception:
            current_app.logger.exception('Ошибка отправки события address_deleted')
        return jsonify({'status': 'ok'}), 200
    # PUT: обновить
    require_admin()
    # multipart PUT: file upload
    if request.files:
        form = request.form or {}
        # parse coords or use existing
        new_lat = parse_coord(form.get('lat')) if 'lat' in form else address.lat
        new_lon = parse_coord(form.get('lon')) if 'lon' in form else address.lon
        if not in_range(new_lat, new_lon):
            return jsonify({'error': 'Invalid coordinates'}), 400
        # зона (опционально, при обновлении можно сменить)
        zone_id = address.zone_id
        if 'zone_id' in form:
            try:
                raw_zone = form.get('zone_id')
                if raw_zone not in (None, ''):
                    zone_id = int(raw_zone)
            except (TypeError, ValueError):
                zone_id = address.zone_id
        if zone_id is not None:
            ensure_zone_access(zone_id)
        # update primitive fields if provided
        if 'name' in form or 'address' in form:
            address.name = (form.get('name') or form.get('address') or address.name or '').strip()
        if 'notes' in form or 'description' in form:
            address.notes = (form.get('notes') or form.get('description') or address.notes or '').strip()
        address.lat = new_lat
        address.lon = new_lon
        address.zone_id = zone_id
        if 'status' in form:
            address.status = (form.get('status') or '').strip()
        if 'link' in form:
            address.link = (form.get('link') or '').strip()
        if 'category' in form:
            address.category = (form.get('category') or '').strip()
        # Флаг удаления фотографии
        remove_photo_flag = form.get('remove_photo')
        # Обработка новой фотографии
        photo_file = request.files.get('photo') or request.files.get('file')
        if photo_file and _allowed_file(photo_file.filename):
            # Сохраняем новое фото и удаляем старое (если оно было)
            ext = photo_file.filename.rsplit('.', 1)[1].lower()
            unique_name = f"{uuid.uuid4().hex}.{ext}"
            dest_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
            try:
                os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
                photo_file.save(dest_path)
                prev = address.photo
                address.photo = unique_name
                # удалить старую фотографию, если изменилась
                if prev and prev != unique_name:
                    try:
                        os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], prev))
                    except Exception:
                        pass
            except Exception:
                pass
        elif remove_photo_flag and str(remove_photo_flag).lower() in ('1', 'true', 'yes'):
            # Пользователь запросил удаление фото и не прикрепил новое
            prev = address.photo
            address.photo = None
            if prev:
                try:
                    os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], prev))
                except Exception:
                    pass
        db.session.commit()
        # событие об обновлении адреса
        try:
            broadcast_event_sync('address_updated', address.to_dict())
        except Exception:
            current_app.logger.exception('Ошибка отправки события address_updated')
        return jsonify({'status': 'ok'}), 200
    # JSON PUT
    data = request.get_json(silent=True) or {}
    new_lat = parse_coord(data.get('lat')) if 'lat' in data else address.lat
    new_lon = parse_coord(data.get('lon')) if 'lon' in data else address.lon
    if not in_range(new_lat, new_lon):
        return jsonify({'error': 'Invalid coordinates'}), 400
    # зона (опционально, при обновлении можно сменить)
    zone_id = address.zone_id
    if 'zone_id' in data:
        try:
            raw_zone = data.get('zone_id')
            if raw_zone not in (None, ''):
                zone_id = int(raw_zone)
        except (TypeError, ValueError):
            zone_id = address.zone_id
    if zone_id is not None:
        ensure_zone_access(zone_id)
    # Обновляем поля, если они присутствуют в запросе
    if 'name' in data or 'address' in data:
        address.name = (data.get('name') or data.get('address') or address.name or '').strip()
    if 'notes' in data or 'description' in data:
        address.notes = (data.get('notes') or data.get('description') or address.notes or '').strip()
    address.lat = new_lat
    address.lon = new_lon
    address.zone_id = zone_id
    if 'status' in data:
        address.status = (data.get('status') or '').strip()
    if 'link' in data:
        address.link = (data.get('link') or '').strip()
    if 'category' in data:
        address.category = (data.get('category') or '').strip()
    # Флаг удаления фото (JSON boolean or string)
    remove_photo = data.get('remove_photo')
    if remove_photo and str(remove_photo).lower() in ('1', 'true', 'yes'):  # truthy
        prev = address.photo
        address.photo = None
        if prev:
            try:
                os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], prev))
            except Exception:
                pass
    db.session.commit()
    return jsonify({'status': 'ok'}), 200


@bp.post('/addresses:batchDelete')
def batch_delete_addresses() -> Response:
    """Удалить несколько адресов сразу. Только администратор."""
    require_admin()
    data = request.get_json(silent=True) or {}
    ids: List[str] = data.get('ids', [])
    removed = 0
    for item_id in ids:
        address = Address.query.get(item_id)
        if not address:
            continue
        # Проверяем доступ к зоне каждого адреса
        if address.zone_id is not None:
            try:
                ensure_zone_access(address.zone_id)
            except Exception:
                # Если нет доступа к конкретной зоне, пропускаем этот адрес
                continue
        db.session.delete(address)
        removed += 1
    db.session.commit()
    return jsonify({'deleted': removed})


@bp.get('/export')
def export_addresses() -> Response:
    """Экспортировать текущие адреса в CSV."""
    items = [addr.to_dict() for addr in Address.query.all()]
    output = StringIO()
    import csv

    writer = csv.writer(output)
    writer.writerow(['id', 'name', 'lat', 'lon', 'notes', 'status', 'link', 'category'])
    for item in items:
        writer.writerow([
            item.get('id'),
            item.get('name') or item.get('address'),
            item.get('lat'),
            item.get('lon'),
            item.get('notes') or item.get('description'),
            item.get('status'),
            item.get('link'),
            item.get('category'),
        ])
    output.seek(0)
    return Response(
        output.read(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=addresses.csv'},
    )


@bp.get('/export.xlsx')
def export_addresses_xlsx() -> Response:
    """Экспортировать текущие адреса в формате Excel (XLSX).

    Создаёт таблицу со всеми полями адреса, чтобы пользователь мог
    открыть её в Excel и работать с данными напрямую.
    """
    from openpyxl import Workbook
    from io import BytesIO

    items = [addr.to_dict() for addr in Address.query.all()]
    wb = Workbook()
    ws = wb.active
    ws.title = 'Addresses'
    # Заголовки столбцов
    header = ['id', 'name', 'lat', 'lon', 'notes', 'status', 'link', 'category']
    ws.append(header)
    for item in items:
        ws.append([
            item.get('id'),
            item.get('name') or item.get('address'),
            item.get('lat'),
            item.get('lon'),
            item.get('notes') or item.get('description'),
            item.get('status'),
            item.get('link'),
            item.get('category'),
        ])
    # Записываем файл в буфер
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename=addresses.xlsx'},
    )


@bp.post('/import')
def import_addresses() -> Response:
    """Импортировать адреса из CSV. Только администратор."""
    require_admin()
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No file provided'}), 400
    imported = 0
    try:
        stream = StringIO(file.stream.read().decode('utf-8'))
        import csv

        reader = csv.DictReader(stream)
        for row in reader:
            name = (row.get('name') or row.get('address') or '').strip()
            notes = (row.get('notes') or row.get('description') or '').strip()
            lat = parse_coord(row.get('lat'))
            lon = parse_coord(row.get('lon'))
            status_str = (row.get('status') or '').strip()
            link = (row.get('link') or '').strip()
            category = (row.get('category') or '').strip()
            if not in_range(lat, lon):
                continue
            existing_id = row.get('id')
            if existing_id:
                # Обновить существующую запись
                addr = Address.query.get(existing_id)
                if addr:
                    addr.name = name
                    addr.lat = lat
                    addr.lon = lon
                    addr.notes = notes
                    addr.status = status_str
                    addr.link = link
                    addr.category = category
                    imported += 1
                    continue
            # Создать новую запись
            addr = Address(
                name=name,
                lat=lat,
                lon=lon,
                notes=notes,
                status=status_str,
                link=link,
                category=category,
            )
            db.session.add(addr)
            imported += 1
        db.session.commit()
        return jsonify({'imported': imported}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.get('/uploads/<path:filename>')
def uploaded_file(filename: str) -> Response:
    """Отдать загруженный файл. Используется для фотографий."""
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)
