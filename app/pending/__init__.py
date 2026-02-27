"""
Пакет для работы с ожидающими заявками (pending markers).

Blueprint pending_bp содержит маршруты для списка заявок и операций
администратора (approve/reject/clear). Эти заявки создаются через
бот или API и хранятся в JSON‑файле.
"""

from compat_flask import Blueprint

bp = Blueprint('pending', __name__)

from . import routes  # noqa: F401
