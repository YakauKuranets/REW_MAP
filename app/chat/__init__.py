"""Blueprint for chat functionality.

Этот модуль определяет Blueprint для обмена сообщениями между
администратором и пользователями Telegram‑бота. Маршруты позволяют
получать список разговоров, читать историю сообщений и отправлять
новые сообщения. Поддерживается отправка сообщений от имени
администратора и пользователя.

"""

from compat_flask import Blueprint

bp = Blueprint('chat', __name__, url_prefix='/api/chat')

from . import routes  # noqa: F401  # импортирует маршруты