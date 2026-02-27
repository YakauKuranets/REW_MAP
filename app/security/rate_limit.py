"""Simple rate limiting (Redis backed if available).

Usage:
    ok, info = check_rate_limit(bucket="login", ident=remote_ip, limit=10, window_seconds=60)
    if not ok: return jsonify(error="rate_limited", **info), 429
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from flask import current_app

try:
    import redis
except Exception:  # pragma: no cover
    redis = None  # type: ignore

_mem: Dict[str, Tuple[int, float]] = {}  # key -> (count, expires_at)

@dataclass
class LimitInfo:
    limit: int
    window_seconds: int
    remaining: int
    reset_in: int

    def to_headers(self) -> Dict[str, int]:
        """Return a dict suitable for embedding into JSON/details.

        Keys are lower_snake_case to match our API style.
        """
        return {
            'limit': int(self.limit),
            'window_seconds': int(self.window_seconds),
            'remaining': int(self.remaining),
            'reset_in': int(self.reset_in),
        }

    def http_headers(self) -> Dict[str, str]:
        """Return standard-ish X-RateLimit-* headers."""
        return {
            'X-RateLimit-Limit': str(int(self.limit)),
            'X-RateLimit-Remaining': str(int(self.remaining)),
            'X-RateLimit-Reset': str(int(self.reset_in)),
        }

def _redis_client():
    url = (current_app.config.get("REDIS_URL") or "").strip()
    if not url or redis is None:
        return None
    try:
        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None

def check_rate_limit(bucket: str, ident: str, limit: int, window_seconds: int) -> Tuple[bool, LimitInfo]:
    now = int(time.time())
    window_start = (now // window_seconds) * window_seconds
    key = f"rl:{bucket}:{window_start}:{ident}"
    reset_in = (window_start + window_seconds) - now
    if reset_in < 0:
        reset_in = 0

    r = _redis_client()
    if r is not None:
        try:
            # Atomic-ish: INCR + set expiry on first hit
            val = r.incr(key)
            if val == 1:
                r.expire(key, window_seconds + 5)
            remaining = max(0, limit - int(val))
            ok = int(val) <= limit
            return ok, LimitInfo(limit=limit, window_seconds=window_seconds, remaining=remaining, reset_in=reset_in)
        except Exception:
            # fall back to memory
            pass

    # In-memory fallback
    cnt, exp = _mem.get(key, (0, now + window_seconds))
    if exp <= now:
        cnt, exp = 0, now + window_seconds
    cnt += 1
    _mem[key] = (cnt, exp)
    remaining = max(0, limit - cnt)
    ok = cnt <= limit
    return ok, LimitInfo(limit=limit, window_seconds=window_seconds, remaining=remaining, reset_in=int(exp - now))
