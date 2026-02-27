"""Сервис для работы с административными ролями и правами.

Содержит функции для:

- определения текущего администратора по имени пользователя;
- проверки роли (viewer/editor/superadmin);
- проверки доступа к зонам;
- начальной инициализации супер‑админа по конфигу приложения.
"""

from __future__ import annotations

from typing import Optional

from compat_flask import current_app
from compat_werkzeug_security import check_password_hash

from ..extensions import db
from ..models import AdminUser, Zone

# Порядок «старшинства» ролей
ROLE_ORDER = {
    'viewer': 0,
    'editor': 1,
    'superadmin': 2,
}


def get_admin_by_username(username: str) -> Optional[AdminUser]:
    """Найти администратора по имени пользователя."""
    if not username:
        return None
    return AdminUser.query.filter_by(username=username).first()


def has_role(admin: Optional[AdminUser], min_role: str = 'editor') -> bool:
    """Проверить, что у администратора роль не ниже указанной."""
    if admin is None:
        return False
    cur = ROLE_ORDER.get(admin.role or 'viewer', 0)
    need = ROLE_ORDER.get(min_role, 0)
    return cur >= need


def has_zone_access(admin: Optional[AdminUser], zone_id: Optional[int]) -> bool:
    """Проверить доступ администратора к заданной зоне.

    superadmin имеет доступ ко всем зонам.
    Если zone_id is None, доступ разрешён (нет ограничения).
    """
    if zone_id is None or admin is None:
        # Если нет зоны или админа — считаем, что отдельной проверки нет.
        return True
    if admin.role == 'superadmin':
        return True
    return any(z.id == zone_id for z in admin.zones)


def attach_zone(admin: AdminUser, zone_id: int) -> None:
    """Привязать админа к зоне, если он ещё не привязан."""
    zone = Zone.query.get(zone_id)
    if not zone:
        return
    if zone not in admin.zones:
        admin.zones.append(zone)
        db.session.commit()


def bootstrap_superadmin_from_config(app) -> None:
    """Создать (или обновить) супер‑админа из конфигурации.

    Использует ADMIN_USERNAME и ADMIN_PASSWORD_HASH:

    - если пользователь с таким username уже есть, обновляет ему
      роль до superadmin и пароль до актуального хеша;
    - если нет — создаёт нового активного супер‑админа.

    Это позволяет постепенно переехать с конфигурационного
    пользователя на полноценную модель AdminUser, не ломая
    существующую авторизацию.
    """
    with app.app_context():
        username = app.config.get('ADMIN_USERNAME')
        password_hash = app.config.get('ADMIN_PASSWORD_HASH')
        if not username or not password_hash:
            return

        admin = AdminUser.query.filter_by(username=username).first()
        if admin is None:
            admin = AdminUser(
                username=username,
                password_hash=password_hash,
                role='superadmin',
                is_active=True,
            )
            db.session.add(admin)
        else:
            admin.password_hash = password_hash
            if admin.role != 'superadmin':
                admin.role = 'superadmin'
            admin.is_active = True

        db.session.commit()


def verify_admin_credentials(username: str, password: str) -> Optional[AdminUser]:
    """Проверить логин/пароль администратора по базе AdminUser.

    Возвращает объект AdminUser при успехе, иначе None.
    """
    if not username or not password:
        return None
    admin = AdminUser.query.filter_by(username=username, is_active=True).first()
    if not admin:
        return None
    if not admin.password_hash:
        return None
    if not check_password_hash(admin.password_hash, password):
        return None
    return admin
