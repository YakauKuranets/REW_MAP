"""Сервисный слой для работы с адресами.

Все операции выборки/создания/обновления/удаления адресов,
а также импорт/экспорт вынесены в отдельные функции. Это
позволяет повторно использовать их и упрощает написание тестов.
"""

from __future__ import annotations

import os
import uuid

from io import StringIO
from typing import Any, Dict, List, Optional, Tuple

from compat_flask import current_app
from sqlalchemy import or_

from ..extensions import db
from ..models import Address
from ..helpers  import parse_coord, in_range




def _allowed_file(filename: str) -> bool:
    """Проверить, что имя файла имеет допустимое расширение."""
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    allowed = current_app.config.get('ALLOWED_EXTENSIONS') or {'png', 'jpg', 'jpeg', 'gif'}
    return ext in allowed

def filter_addresses(
    q: str = "",
    category: str = "",
    status: str = "",
) -> List[Dict[str, Any]]:
    """Вернуть список адресов с учётом фильтров."""
    query = Address.query
    q = (q or "").strip()
    category = (category or "").strip()
    status = (status or "").strip()

    if q:
        like_pattern = f"%{q}%"
        query = query.filter(
            or_(Address.name.ilike(like_pattern), Address.notes.ilike(like_pattern))
        )
    if category:
        query = query.filter(Address.category == category)
    if status:
        query = query.filter(Address.status == status)

    return [a.to_dict() for a in query.all()]


def create_address_from_form(form, files) -> Tuple[bool, Dict[str, Any]]:
    """Создать адрес по данным HTML‑формы.

    Возвращает кортеж (ok, payload), где ok показывает успешность
    операции, а payload содержит либо данные ошибки, либо id адреса.
    """
    name = (form.get('name') or form.get('address') or '').strip()
    notes = (form.get('notes') or form.get('description') or '').strip()
    lat = parse_coord(form.get('lat'))
    lon = parse_coord(form.get('lon'))
    status_str = (form.get('status') or '').strip()
    link = (form.get('link') or '').strip()
    category = (form.get('category') or '').strip()

    if not name or lat is None or lon is None:
        return False, {'error': 'name, lat, lon are required'}

    if not in_range(lat, lon):
        return False, {'error': 'coordinates out of range'}

    photo_filename = None
    file = files.get('photo') if hasattr(files, 'get') else None
    if file and file.filename:
        if not _allowed_file(file.filename):
            return False, {'error': 'invalid file type'}
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        ext = file.filename.rsplit('.', 1)[1].lower()
        uid = uuid.uuid4().hex
        photo_filename = f'{uid}.{ext}'
        file.save(os.path.join(upload_folder, photo_filename))

    addr = Address(
        name=name,
        lat=lat,
        lon=lon,
        notes=notes,
        status=status_str,
        link=link,
        category=category,
        photo=photo_filename,
    )
    db.session.add(addr)
    db.session.commit()

    return True, {'id': addr.id}


def export_addresses_csv() -> str:
    """Экспортировать адреса в CSV‑строку."""
    items = [addr.to_dict() for addr in Address.query.all()]
    output = StringIO()
    import csv

    writer = csv.writer(output)
    writer.writerow(['id', 'name', 'lat', 'lon', 'notes', 'status', 'link', 'category'])
    for item in items:
        writer.writerow(
            [
                item.get('id', ''),
                item.get('name', ''),
                item.get('lat', ''),
                item.get('lon', ''),
                item.get('notes', ''),
                item.get('status', ''),
                item.get('link', ''),
                item.get('category', ''),
            ]
        )
    return output.getvalue()


def import_addresses_from_csv(stream) -> Dict[str, Any]:
    """Импортировать адреса из CSV‑потока.

    Аргумент ``stream`` должен предоставлять метод ``read()`` и
    возвращать строку CSV (например, объект StringIO).
    """
    import csv

    reader = csv.DictReader(stream)
    imported = 0

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
            addr = Address.query.get(existing_id)
        else:
            addr = None

        if addr is None:
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
        else:
            addr.name = name
            addr.lat = lat
            addr.lon = lon
            addr.notes = notes
            addr.status = status_str
            addr.link = link
            addr.category = category

        imported += 1

    db.session.commit()
    return {'imported': imported}
