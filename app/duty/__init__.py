"""Duty (наряды) модуль: смены, трекинг, обеды и журнал."""

from flask import Blueprint

bp = Blueprint('duty', __name__)

from . import routes  # noqa: F401
