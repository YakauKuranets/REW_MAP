"""Handshake upload API blueprint."""

from flask import Blueprint

bp = Blueprint("handshake", __name__, url_prefix="/api/video/handshake")

from . import routes  # noqa: F401
