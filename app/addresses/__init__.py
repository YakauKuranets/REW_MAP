"""
Пакет для работы с адресами.

Blueprint addresses_bp содержит маршруты для получения,
создания, обновления и удаления адресов. Здесь не
используется база данных; данные хранятся в JSON‑файле.
"""

from compat_flask import Blueprint

bp = Blueprint('addresses', __name__)

from . import routes  # noqa: F401
