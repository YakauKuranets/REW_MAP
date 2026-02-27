"""Blueprint для управления администраторами (AdminUser).

Маршруты расположены под префиксом /api/admin/users и предполагают
использование только из защищённого админского интерфейса.
"""

from compat_flask import Blueprint

bp = Blueprint("admin_users", __name__, url_prefix="/api/admin/users")

from . import routes  # noqa: E402,F401
