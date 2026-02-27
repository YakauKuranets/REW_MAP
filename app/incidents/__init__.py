"""Blueprint for incidents API.

Эта директория содержит маршруты для управления инцидентами (B2 feature).
Инциденты представляют собой точки/метки на карте с жизненным циклом
(``new`` → ``assigned`` → ``enroute`` → ``on_scene`` → ``resolved`` → ``closed``)
и могут быть назначены нарядам (shifts). В каждый инцидент могут
принадлежать одно или несколько назначений, а также список событий
(``IncidentEvent``), отражающих историю изменений.

Blueprint регистрируется в ``app/__init__.py`` под префиксом
``/api/incidents``.
"""

from compat_flask import Blueprint

# Создаём blueprint с префиксом /api/incidents
bp = Blueprint('incidents', __name__, url_prefix='/api/incidents')

# Импорт маршрутов для регистрации
from . import routes  # noqa: F401