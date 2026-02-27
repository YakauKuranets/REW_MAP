from flask import Blueprint

bp = Blueprint("alerting", __name__, url_prefix="/api/alerts")

from . import routes  # noqa: E402,F401
