"""System helper endpoints (LAN info, diagnostics)."""

from compat_flask import Blueprint

bp = Blueprint("system", __name__)

from . import routes  # noqa: F401
