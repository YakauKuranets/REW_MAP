"""Tracker module: pairing + device auth + live points (Android)."""

from flask import Blueprint

bp = Blueprint('tracker', __name__)

from . import routes  # noqa: F401
