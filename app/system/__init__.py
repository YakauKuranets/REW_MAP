"""System helper endpoints (LAN info, diagnostics)."""

from flask import Blueprint

bp = Blueprint("system", __name__)

from . import routes  # noqa: F401
