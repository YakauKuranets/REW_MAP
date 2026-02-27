"""Terminal connectivity API blueprint."""

from compat_flask import Blueprint

bp = Blueprint("terminals", __name__, url_prefix="/api/terminals")

from . import routes  # noqa: F401
