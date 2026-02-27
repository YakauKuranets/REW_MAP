"""Minimal Prometheus-style metrics without extra dependencies.

Enable via config:
  - ENABLE_METRICS=1
  - METRICS_PATH=/metrics (default)
  - METRICS_ALLOW_PUBLIC=0 (default; only localhost)
  - METRICS_API_KEY=... (optional; allows remote scraping when key matches)
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Tuple

from compat_flask import Response, g, request, current_app

_req_total: Dict[Tuple[str, str, str], int] = defaultdict(int)
_req_dur_sum: Dict[Tuple[str, str], float] = defaultdict(float)
_req_dur_cnt: Dict[Tuple[str, str], int] = defaultdict(int)

@dataclass(frozen=True)
class MetricsSnapshot:
    req_total: Dict[Tuple[str, str, str], int]
    dur_sum: Dict[Tuple[str, str], float]
    dur_cnt: Dict[Tuple[str, str], int]

def _endpoint_label() -> str:
    # Flask gives something like 'chat.api_list_conversations'. It's stable across runs.
    ep = request.endpoint or "unknown"
    return ep

def before_request() -> None:
    g._metrics_start = time.perf_counter()

def after_request(resp: Response) -> Response:
    try:
        method = request.method
        endpoint = _endpoint_label()
        status = str(resp.status_code)
        _req_total[(method, endpoint, status)] += 1

        start = getattr(g, "_metrics_start", None)
        if start is not None:
            dur = max(0.0, time.perf_counter() - start)
            _req_dur_sum[(method, endpoint)] += dur
            _req_dur_cnt[(method, endpoint)] += 1
    except Exception:
        # Metrics must never break the request flow.
        pass
    return resp

def snapshot() -> MetricsSnapshot:
    return MetricsSnapshot(dict(_req_total), dict(_req_dur_sum), dict(_req_dur_cnt))

def render_prometheus_text() -> str:
    s = snapshot()
    lines = []
    lines.append("# HELP http_requests_total Total HTTP requests.")
    lines.append("# TYPE http_requests_total counter")
    for (method, endpoint, status), val in sorted(s.req_total.items()):
        lines.append(f'http_requests_total{{method="{method}",endpoint="{endpoint}",status="{status}"}} {val}')

    lines.append("# HELP http_request_duration_seconds_sum Total time spent serving requests.")
    lines.append("# TYPE http_request_duration_seconds_sum counter")
    for (method, endpoint), val in sorted(s.dur_sum.items()):
        lines.append(f'http_request_duration_seconds_sum{{method="{method}",endpoint="{endpoint}"}} {val}')

    lines.append("# HELP http_request_duration_seconds_count Number of timed requests.")
    lines.append("# TYPE http_request_duration_seconds_count counter")
    for (method, endpoint), val in sorted(s.dur_cnt.items()):
        lines.append(f'http_request_duration_seconds_count{{method="{method}",endpoint="{endpoint}"}} {val}')
    lines.append("")
    # Включаем chat2 метрики
    try:
        # Импорт отложен, чтобы избежать циклических зависимостей
        from ..event_chat.metrics import snapshot as chat_snapshot
        chat_metrics = chat_snapshot()
        for name, val in sorted(chat_metrics.items()):
            pname = name.replace("-", "_")
            # Объявляем каждую метрику как счётчик (counter)
            lines.append(f"# TYPE {pname} counter")
            lines.append(f"{pname} {val}")
    except Exception:
        # Метрики не должны прерывать вывод
        pass
    lines.append("")
    return "\n".join(lines)

def metrics_response() -> Response:
    # Default deny from non-local unless explicitly allowed.
    allow_public = bool(current_app.config.get("METRICS_ALLOW_PUBLIC"))
    if not allow_public:
        expected = (current_app.config.get("METRICS_API_KEY") or "").strip()
        if expected:
            provided = (request.headers.get("X-API-KEY") or "").strip()
            if not provided:
                provided = (request.args.get("api_key") or "").strip()
            if provided == expected:
                return Response(render_prometheus_text(), status=200, mimetype="text/plain; version=0.0.4")

        ra = request.remote_addr or ""
        if ra not in ("127.0.0.1", "::1"):
            return Response("forbidden\n", status=403, mimetype="text/plain; version=0.0.4")
    return Response(render_prometheus_text(), status=200, mimetype="text/plain; version=0.0.4")
