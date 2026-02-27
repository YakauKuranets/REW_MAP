"""Video proxy API blueprint."""

from compat_flask import Blueprint

bp = Blueprint("video", __name__, url_prefix="/api/video")

from . import routes  # noqa: F401
