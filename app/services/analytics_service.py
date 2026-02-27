"""Сервисный слой для модуля аналитики.

Здесь размещается логика агрегации статистики по адресам и заявкам.
Маршруты в :mod:`app.analytics.routes` используют эти функции,
чтобы не содержать тяжёлую бизнес‑логику.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List

from sqlalchemy import func
from sqlalchemy.exc import OperationalError

from ..models import db, Address, PendingMarker, PendingHistory, Zone


from typing import Optional


def _pct(part: int, total: int) -> float:
    """Посчитать процент part от total.

    Возвращаем число (0..100) с плавающей точкой.
    Округление выполняем на фронте, чтобы не терять точность.
    """
    try:
        p = int(part or 0)
        t = int(total or 0)
    except (TypeError, ValueError):
        return 0.0
    if t <= 0:
        return 0.0
    return (p / t) * 100.0


def build_period_text(days: int = 7) -> Dict[str, Any]:
    """Облегчённая аналитика для текстового UI.

    В отличие от :func:`build_summary`, не строит графики/таймлайн и не
    возвращает распределения по категориям. Считаем только то, что нужно
    для простого текста.
    """
    days_clamped = max(1, min(int(days or 7), 365))
    since_dt = datetime.utcnow() - timedelta(days=days_clamped)

    # --- Адреса ---
    total_addresses = (db.session.query(func.count(Address.id)).scalar() or 0)
    added_addresses = (
        db.session.query(func.count(Address.id))
        .filter(Address.created_at >= since_dt)
        .scalar()
        or 0
    )

    # --- Заявки ---
    # Под "total" понимаем суммарное количество заявок в системе:
    # текущие pending + исторические approved/rejected.
    pending_total = (db.session.query(func.count(PendingMarker.id)).scalar() or 0)
    approved_total = (
        db.session.query(func.count(PendingHistory.id))
        .filter(PendingHistory.status == 'approved')
        .scalar()
        or 0
    )
    rejected_total = (
        db.session.query(func.count(PendingHistory.id))
        .filter(PendingHistory.status == 'rejected')
        .scalar()
        or 0
    )
    total_requests = int(pending_total or 0) + int(approved_total or 0) + int(rejected_total or 0)

    # Считаем события за период
    created_requests = (
        db.session.query(func.count(PendingMarker.id))
        .filter(PendingMarker.created_at >= since_dt)
        .scalar()
        or 0
    )
    approved_period = (
        db.session.query(func.count(PendingHistory.id))
        .filter(PendingHistory.status == 'approved', PendingHistory.timestamp >= since_dt)
        .scalar()
        or 0
    )
    rejected_period = (
        db.session.query(func.count(PendingHistory.id))
        .filter(PendingHistory.status == 'rejected', PendingHistory.timestamp >= since_dt)
        .scalar()
        or 0
    )

    return {
        'days': int(days_clamped),
        'since': since_dt.date().isoformat(),
        'addresses': {
            'total': int(total_addresses or 0),
            'added': int(added_addresses or 0),
            'added_percent': _pct(added_addresses, total_addresses),
        },
        'requests': {
            'total': int(total_requests or 0),
            'created': int(created_requests or 0),
            'created_percent': _pct(created_requests, total_requests),
            'approved_total': int(approved_total or 0),
            'approved': int(approved_period or 0),
            'approved_percent': _pct(approved_period, approved_total),
            'rejected_total': int(rejected_total or 0),
            'rejected': int(rejected_period or 0),
            'rejected_percent': _pct(rejected_period, rejected_total),
        },
    }


def build_summary(days: int = 7, zone_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Построить сводку аналитики по адресам и заявкам.

    Параметры
    ----------
    days : int, optional
        Количество дней для построения таймлайна и метрики «добавлено за N дней». Значение
        ограничивается диапазоном 1..365. По умолчанию 7.
    zone_id : int, optional
        Идентификатор зоны, по которой нужно ограничить статистику. Если None, статистика
        строится по всем данным.

    Возвращает словарь со следующей структурой::

        {
            'total': int,                # всего адресов
            'by_category': {...},        # распределение по категориям
            'by_status': {...},          # распределение по статусу доступа
            'pending': int,              # активные заявки
            'approved': int,             # одобренные заявки (исторически)
            'rejected': int,             # отклонённые заявки (исторически)
            'added_last_n': int,         # сколько адресов добавлено за N дней
            'timeline_last_n': [         # динамика по дням (выбранный период)
                {
                    'date': 'YYYY-MM-DD',
                    'addresses': int,
                    'pending_created': int,
                    'approved': int,
                    'rejected': int,
                },
                ...
            ],
            'by_zone': {...},            # распределение адресов по зонам (если не фильтруем по зоне)
            'pending_by_status': {...},  # распределение заявок по статусам
        }
    """
    # Ограничиваем значение days, чтобы избежать очень длинных интервалов
    days_clamped = max(1, min(int(days or 7), 365))

    # --- Базовые агрегаты по адресам ---

    # Считаем количество адресов, с учётом возможного фильтра по зоне
    addr_query = db.session.query(func.count(Address.id))
    if zone_id is not None:
        addr_query = addr_query.filter(Address.zone_id == zone_id)
    total_addresses = (addr_query.scalar() or 0)

    # Распределение по категориям
    cat_query = db.session.query(Address.category, func.count(Address.id))
    if zone_id is not None:
        cat_query = cat_query.filter(Address.zone_id == zone_id)
    by_category_rows = cat_query.group_by(Address.category).all()
    by_category: Dict[str, int] = {}
    for category, cnt in by_category_rows:
        key = category or 'Без категории'
        by_category[key] = int(cnt or 0)

    # Распределение по статусу доступа
    stat_query = db.session.query(Address.status, func.count(Address.id))
    if zone_id is not None:
        stat_query = stat_query.filter(Address.zone_id == zone_id)
    by_status_rows = stat_query.group_by(Address.status).all()
    by_status: Dict[str, int] = {}
    for status, cnt in by_status_rows:
        key = status or 'Не указан'
        by_status[key] = int(cnt or 0)

    # --- Распределение по зонам (только по адресам) ---

    by_zone: Dict[str, int] = {}

    # Попытка посчитать распределение по зонам. В старой схеме базы
    # addresses.zone_id может отсутствовать, поэтому завершаем без ошибок,
    # если колонка не найдена.
    if zone_id is None:
        try:
            zone_rows = (
                db.session.query(Zone.id, Zone.description, func.count(Address.id))
                .join(Address, Address.zone_id == Zone.id)
                .group_by(Zone.id, Zone.description)
                .all()
            )
            for zid, description, cnt in zone_rows:
                label = (description or '').strip() or 'Без описания зоны'
                by_zone[str(zid)] = int(cnt or 0)
            # Адреса без зоны
            no_zone_count = (
                db.session.query(func.count(Address.id))
                .filter(Address.zone_id.is_(None))
                .scalar()
                or 0
            )
            if no_zone_count:
                by_zone['none'] = int(no_zone_count)
        except OperationalError:
            by_zone = {}
    else:
        # Если фильтр по зоне, распределение по зонам не имеет смысла (одна зона)
        by_zone = {}

    # --- Агрегаты по заявкам ---

    # Количество ожидающих заявок (pending)
    pending_query = db.session.query(func.count(PendingMarker.id))
    if zone_id is not None:
        pending_query = pending_query.filter(PendingMarker.zone_id == zone_id)
    pending_count = (pending_query.scalar() or 0)

    # Исторические статусы заявок (approved / rejected)
    appr_query = db.session.query(func.count(PendingHistory.id)).filter(PendingHistory.status == 'approved')
    rej_query = db.session.query(func.count(PendingHistory.id)).filter(PendingHistory.status == 'rejected')
    if zone_id is not None:
        # Не все записи PendingHistory содержат address_id; выполняем join только если zone_id фильтр задан.
        appr_query = appr_query.join(Address, PendingHistory.address_id == Address.id).filter(Address.zone_id == zone_id)
        rej_query = rej_query.join(Address, PendingHistory.address_id == Address.id).filter(Address.zone_id == zone_id)
    approved_count = (appr_query.scalar() or 0)
    rejected_count = (rej_query.scalar() or 0)

    # Распределение активных заявок по статусам
    pending_status_query = db.session.query(PendingMarker.status, func.count(PendingMarker.id))
    if zone_id is not None:
        pending_status_query = pending_status_query.filter(PendingMarker.zone_id == zone_id)
    pending_by_status_rows = pending_status_query.group_by(PendingMarker.status).all()
    pending_by_status: Dict[str, int] = {}
    for status, cnt in pending_by_status_rows:
        key = status or 'Без статуса'
        pending_by_status[key] = int(cnt or 0)

    # --- Метрика «добавлено за N дней» ---
    since = datetime.utcnow() - timedelta(days=days_clamped)
    added_query = db.session.query(func.count(Address.id)).filter(Address.created_at >= since)
    if zone_id is not None:
        added_query = added_query.filter(Address.zone_id == zone_id)
    added_last_n = (added_query.scalar() or 0)

    # --- Таймлайн за N дней ---
    today = datetime.utcnow().date()
    timeline_last_n: List[Dict[str, Any]] = []
    # Определяем количество точек. Если период больше 60 дней, выбираем шаг,
    # чтобы не перегружать график. Всегда ограничиваем максимум 60 точек.
    total_points = min(days_clamped, 60)
    step = 1
    if days_clamped > 60:
        step = days_clamped // 60 + 1
    for i in range(total_points):
        delta = (total_points - 1 - i) * step
        day = today - timedelta(days=delta)
        day_start = datetime.combine(day, datetime.min.time())
        day_end = day_start + timedelta(days=step)
        # Считаем адреса и заявки в выбранном интервале
        addr_day_query = db.session.query(func.count(Address.id)).filter(Address.created_at >= day_start, Address.created_at < day_end)
        pend_day_query = db.session.query(func.count(PendingMarker.id)).filter(PendingMarker.created_at >= day_start, PendingMarker.created_at < day_end)
        appr_day_query = db.session.query(func.count(PendingHistory.id)).filter(PendingHistory.status == 'approved', PendingHistory.timestamp >= day_start, PendingHistory.timestamp < day_end)
        rej_day_query = db.session.query(func.count(PendingHistory.id)).filter(PendingHistory.status == 'rejected', PendingHistory.timestamp >= day_start, PendingHistory.timestamp < day_end)
        if zone_id is not None:
            addr_day_query = addr_day_query.filter(Address.zone_id == zone_id)
            pend_day_query = pend_day_query.filter(PendingMarker.zone_id == zone_id)
            # История заявок: join с Address для фильтрации по zone_id
            appr_day_query = appr_day_query.join(Address, PendingHistory.address_id == Address.id).filter(Address.zone_id == zone_id)
            rej_day_query = rej_day_query.join(Address, PendingHistory.address_id == Address.id).filter(Address.zone_id == zone_id)
        addresses_day = (addr_day_query.scalar() or 0)
        pending_created_day = (pend_day_query.scalar() or 0)
        approved_day = (appr_day_query.scalar() or 0)
        rejected_day = (rej_day_query.scalar() or 0)
        timeline_last_n.append(
            {
                'date': day.isoformat(),
                'addresses': int(addresses_day or 0),
                'pending_created': int(pending_created_day or 0),
                'approved': int(approved_day or 0),
                'rejected': int(rejected_day or 0),
            }
        )

    return {
        'total': int(total_addresses or 0),
        'by_category': by_category,
        'by_status': by_status,
        'pending': int(pending_count or 0),
        'approved': int(approved_count or 0),
        'rejected': int(rejected_count or 0),
        'added_last_n': int(added_last_n or 0),
        'timeline_last_n': timeline_last_n,
        'by_zone': by_zone,
        'pending_by_status': pending_by_status,
    }


def build_audit_log(limit: int = 50) -> Dict[str, Any]:
    """Построить ленту последних действий (аудит).

    Использует уже существующие сущности:

    * Address       — создание адресов;
    * PendingMarker — создание заявок;
    * PendingHistory — изменение статусов заявок.

    Возвращает упрощённую структуру::

        {
            "events": [
                {"ts": "ISO", "kind": "address_created", "text": "..."},
                ...
            ]
        }
    """
    events: List[Dict[str, Any]] = []

    # Созданные адреса (оборачиваем в try на случай отсутствия колонки zone_id)
    try:
        addr_rows = (
            db.session.query(Address.id, Address.name, Address.created_at, Zone.description)
            .outerjoin(Zone, Address.zone_id == Zone.id)
            .order_by(Address.created_at.desc())
            .limit(limit)
            .all()
        )
        for addr_id, name, created_at, zone_desc in addr_rows:
            if not created_at:
                continue
            z_label = (zone_desc or '').strip()
            if not z_label:
                z_label = 'Без зоны'
            text = f"Создан адрес '{name or ''}' (зона: {z_label})"
            events.append(
                {
                    "ts": created_at,
                    "kind": "address_created",
                    "text": text,
                }
            )
    except OperationalError:
        # fallback: выбираем адреса без join'а и не упоминаем зону
        addr_rows = (
            db.session.query(Address.id, Address.name, Address.created_at)
            .order_by(Address.created_at.desc())
            .limit(limit)
            .all()
        )
        for addr_id, name, created_at in addr_rows:
            if not created_at:
                continue
            text = f"Создан адрес '{name or ''}'"
            events.append(
                {
                    "ts": created_at,
                    "kind": "address_created",
                    "text": text,
                }
            )

    # Созданные заявки
    pending_rows = (
        db.session.query(
            PendingMarker.id,
            PendingMarker.name,
            PendingMarker.created_at,
            PendingMarker.reporter,
        )
        .order_by(PendingMarker.created_at.desc())
        .limit(limit)
        .all()
    )
    for pid, name, created_at, reporter in pending_rows:
        if not created_at:
            continue
        reporter_label = (reporter or '').strip() or 'неизвестный отправитель'
        text = f"Новая заявка '{name or ''}' от {repr(reporter_label)}"
        events.append(
            {
                "ts": created_at,
                "kind": "pending_created",
                "text": text,
            }
        )

    # История изменения статусов заявок
    hist_rows = (
        db.session.query(
            PendingHistory.pending_id,
            PendingHistory.status,
            PendingHistory.timestamp,
            PendingHistory.address_id,
        )
        .order_by(PendingHistory.timestamp.desc())
        .limit(limit)
        .all()
    )
    for pending_id, status, ts, address_id in hist_rows:
        if not ts:
            continue
        status_label = status or 'unknown'
        if address_id:
            text = f"Заявка #{pending_id}: статус {status_label} (адрес #{address_id})"
        else:
            text = f"Заявка #{pending_id}: статус {status_label}"
        events.append(
            {
                "ts": ts,
                "kind": "pending_status",
                "text": text,
            }
        )

    # Отсортировать по времени и ограничить
    events_sorted = sorted(events, key=lambda e: e["ts"], reverse=True)[:limit]

    # Сериализуем ts в ISO-строку
    result_events: List[Dict[str, Any]] = []
    for ev in events_sorted:
        ts_val = ev["ts"]
        if hasattr(ts_val, "isoformat"):
            ts_str = ts_val.isoformat()
        else:
            ts_str = str(ts_val)
        result_events.append(
            {
                "ts": ts_str,
                "kind": ev["kind"],
                "text": ev["text"],
            }
        )

    return {"events": result_events}
