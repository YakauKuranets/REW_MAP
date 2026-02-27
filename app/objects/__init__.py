"""Blueprint for objects API.

Этот пакет реализует REST‑API для управления объектами (адресами с
описанием и множеством камер). Используется в интерфейсе "Map v12"
для создания записей с адресом и связанных камер.
"""

from compat_flask import Blueprint

bp = Blueprint('objects', __name__)

from . import routes  # noqa: F401  # import routes to register endpoints