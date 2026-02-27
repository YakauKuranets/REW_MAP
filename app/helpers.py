"""
Вспомогательные функции для обработки запросов.

Содержит функции для парсинга координат, проверки диапазона,
фильтрации адресов, поиска дубликатов и декоратор для проверки
административных прав. Эти функции используются во многих
маршрутах и вынесены в отдельный модуль для переиспользования.
"""

import math
from typing import Any, Dict, List, Optional

from compat_flask import abort, session
from .services.permissions_service import get_admin_by_username, has_role, has_zone_access


def parse_coord(value: Any) -> Optional[float]:
    """
    Преобразовать значение координаты в float.

    Возвращает None для пустых значений или ошибок преобразования.
    """
    if value is None:
        return None
    try:
        s = str(value).strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None


def in_range(lat: Optional[float], lon: Optional[float]) -> bool:
    """Проверить, входят ли координаты в допустимый диапазон."""
    if lat is not None and not (-90 <= lat <= 90):
        return False
    if lon is not None and not (-180 <= lon <= 180):
        return False
    return True


def filter_items(items: List[Dict[str, Any]], query: str = "", category: str = "", status: str = "") -> List[Dict[str, Any]]:
    """
    Отфильтровать список адресов по запросу, категории и статусу.

    Возвращает новый список.
    """
    res: List[Dict[str, Any]] = []
    q_lower = query.lower()
    for item in items:
        if query:
            val = (item.get("name") or item.get("address") or "")
            if q_lower not in val.lower():
                continue
        if category and category != item.get("category", ""):
            continue
        if status and status != item.get("status", ""):
            continue
        res.append(item)
    return res


def get_item(items: List[Dict[str, Any]], item_id: str) -> Optional[Dict[str, Any]]:
    """Найти один элемент по идентификатору."""
    for item in items:
        if str(item.get("id")) == str(item_id):
            return item
    return None


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    """
    Посчитать расстояние между двумя точками на сфере с радиусом
    Земли (приблизительно 6371 км). Результат возвращается в метрах.
    Если одна из координат None, возвращается бесконечность.
    """
    if None in (lat1, lon1, lat2, lon2):
        return float("inf")
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(1 - a), math.sqrt(a))


def find_duplicate(name: str, lat: Optional[float], lon: Optional[float], items: List[Dict[str, Any]], pending: List[Dict[str, Any]], threshold_m: int = 100):
    """
    Ищет похожую запись среди существующих адресов и ожидающих.
    Возвращает dict {'type': 'address'|'pending', 'id': int} либо None.
    Критерий:
      - если есть координаты, ближе threshold_m;
      - иначе по совпадению имени (регистронезависимо).
    """
    nm = (name or "").strip().lower()
    # Смотрим среди сохранённых адресов
    for it in items:
        if lat is not None and lon is not None and it.get("lat") is not None:
            try:
                dist = haversine_m(lat, lon, float(it["lat"]), float(it["lon"]))
                if dist <= threshold_m:
                    return {"type": "address", "id": int(it["id"])}
            except Exception:
                pass
        if nm and (it.get("name") or it.get("address") or "").strip().lower() == nm:
            return {"type": "address", "id": int(it["id"])}
    # Среди ожидающих
    for it in pending:
        if lat is not None and lon is not None and it.get("lat") is not None:
            try:
                dist = haversine_m(lat, lon, float(it["lat"]), float(it["lon"]))
                if dist <= threshold_m:
                    return {"type": "pending", "id": int(it["id"])}
            except Exception:
                pass
        if nm and (it.get("name") or "").strip().lower() == nm:
            return {"type": "pending", "id": int(it["id"])}
    return None


def require_admin(min_role: str = "editor") -> None:
    """
    Проверить, что пользователь обладает правами администратора.

    Важно: простое наличие session["role"] == "admin" больше НЕ даёт доступ.
    Админский доступ выдаётся только после успешного /login (маркер is_admin)
    и/или при наличии активного AdminUser в базе.
    """
    # Требуем явный маркер успешной аутентификации.
    # Редирект для HTML делается в errorhandler(403) (см. app/__init__.py),
    # чтобы не требовать от маршрутов "return require_admin(...)".
    if not session.get("is_admin"):
        abort(403)

    username = session.get("admin_username") or session.get("username")
    admin = get_admin_by_username(username) if username else None

    # Новый путь: AdminUser (рекомендуемый)
    if admin and has_role(admin, min_role):
        session.setdefault("role", "admin")
        return

    # Легаси путь: один админ из конфига (считаем как superadmin),
    # но только если username совпал и сессия помечена как is_admin.
    try:
        from compat_flask import current_app
        stored_user = current_app.config.get("ADMIN_USERNAME")
    except Exception:
        stored_user = None

    if stored_user and username == stored_user:
        session.setdefault("role", "admin")
        return

    abort(403)


def get_current_admin():
    """Получить текущего администратора по данным сессии.

    Используется сервис permissions_service и значения
    session['admin_username'] / session['username'].
    """
    username = session.get("admin_username") or session.get("username")
    if not username:
        return None
    return get_admin_by_username(username)


def ensure_zone_access(zone_id):
    """Бросить 403, если у текущего админа нет доступа к зоне.

    superadmin имеет доступ ко всем зонам. Если zone_id is None,
    считается, что ограничений по зоне нет.
    """
    admin = get_current_admin()
    if not has_zone_access(admin, zone_id):
        abort(403)

