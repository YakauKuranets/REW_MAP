"""Blueprint для аналитики.

Маршруты:

- `GET /api/analytics/summary` — возвращает агрегацию по объектам и заявкам.
"""

from compat_flask import Blueprint

# Blueprint `analytics` будет зарегистрирован в app/__init__.py с префиксом /api/analytics
bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')

from . import routes  # noqa: F401