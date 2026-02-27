"""
Пакет для работы с заявками (requests) в интерфейсе администратора.

Маршруты возвращают pending‑заявки с укороченной структурой для
отображения в всплывающем списке и позволяют удалить заявку.
"""

from compat_flask import Blueprint

bp = Blueprint('requests', __name__)

from . import routes  # noqa: F401
