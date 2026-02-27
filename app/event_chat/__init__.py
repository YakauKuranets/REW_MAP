"""Blueprint for event-driven chat (shift/incident/direct).

Этот модуль определяет Flask‑Blueprint для работы с новым чат‑интерфейсом,
который реализует обмен сообщениями на основе событийного лога. Все
маршруты начинаются с префикса ``/api/chat2``.
"""

from compat_flask import Blueprint

# Новый namespace: /api/chat2
bp = Blueprint("event_chat", __name__, url_prefix="/api/chat2")

from . import routes  # noqa: F401, E402
