"""Maintenance / operational endpoints (admin-only).

Contains best-effort utilities for production operation:
- retention cleanup

All routes MUST be protected by require_admin.
"""

from compat_flask import Blueprint

bp = Blueprint("maintenance", __name__, url_prefix="/api/admin")

from . import routes  # noqa: E402,F401
