"""Service access ("Служба" по заявке)."""

from flask import Blueprint

bp = Blueprint("service_access", __name__)

from . import routes  # noqa: F401
