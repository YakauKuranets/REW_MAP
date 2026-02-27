"""Маршруты для геокодирования.

Весь алгоритм вынесен в :mod:`app.services.geocode_service`.
Здесь остаётся только HTTP-обёртка и разбор параметров запроса.
"""

from __future__ import annotations

from compat_flask import jsonify, request, make_response

from . import bp
from ..services.geocode_service import geocode


@bp.get("/geocode")
def api_geocode():
    """Выполнить геокодирование с использованием офлайн‑базы и Nominatim."""
    q = request.args.get('q', '').strip()
    try:
        limit = int(request.args.get('limit', 1))
    except (TypeError, ValueError):
        limit = 1
    lang = request.args.get('lang', 'ru').strip() or 'ru'

    results = geocode(q=q, limit=limit, lang=lang)
    resp = make_response(jsonify(results))
    # Геокодер можно кэшировать немного дольше, так как данные редко меняются
    resp.headers['Cache-Control'] = 'public, max-age=300'
    return resp
