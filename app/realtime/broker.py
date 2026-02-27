"""Redis broker helpers for realtime Pub/Sub.

Python здесь выступает:
- Publisher'ом UI-событий в Redis (канал map_updates)
- Consumer'ом telemetry_save_queue для батч-сохранения координат в БД
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

try:
    import redis.asyncio as redis_async
    from redis import Redis
except Exception:  # pragma: no cover
    redis_async = None  # type: ignore[assignment]
    Redis = None  # type: ignore[assignment]


DEFAULT_CHANNEL = "map_updates"
DEFAULT_TELEMETRY_QUEUE = "telemetry_save_queue"
MATRIX_NOISE_CHANNEL = "realtime_events"

logger = logging.getLogger(__name__)


def get_redis_url() -> str:
    """Return REDIS_URL from Flask config or environment."""
    try:
        from compat_flask import current_app

        url = (current_app.config.get("REDIS_URL") or "").strip()
        if url:
            return url
    except Exception:
        pass
    return (os.getenv("REDIS_URL") or "").strip()


def get_channel() -> str:
    try:
        from compat_flask import current_app

        channel = (current_app.config.get("REALTIME_REDIS_CHANNEL") or "").strip()
        if channel:
            return channel
    except Exception:
        pass
    return (os.getenv("REALTIME_REDIS_CHANNEL") or DEFAULT_CHANNEL).strip() or DEFAULT_CHANNEL


def _parse_ts(raw: Any) -> datetime:
    if raw is None:
        return datetime.now(timezone.utc)
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return datetime.now(timezone.utc)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except Exception:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


def _normalize_telemetry_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    body = payload.get("data") if isinstance(payload.get("data"), dict) else payload

    user_id = body.get("user_id")
    lat = body.get("lat")
    lon = body.get("lon")
    if user_id is None or lat is None or lon is None:
        return None

    try:
        return {
            "user_id": str(user_id),
            "lat": float(lat),
            "lon": float(lon),
            "accuracy_m": float(body.get("accuracy_m")) if body.get("accuracy_m") is not None else None,
            "kind": str(body.get("kind") or "live")[:16],
            "ts": _parse_ts(body.get("ts")),
            "raw_json": json.dumps(body, ensure_ascii=False),
        }
    except Exception:
        return None


class RedisBroker:
    """Publisher/subscriber broker over Redis Pub/Sub."""

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self.redis_url = (redis_url or get_redis_url()).strip()
        self._sync_client: Optional[Redis] = None

    def _get_sync_client(self) -> Optional[Redis]:
        if not self.redis_url or Redis is None:
            return None
        if self._sync_client is None:
            # Переиспользуем один клиент на процесс: без connect/disconnect на каждый publish.
            self._sync_client = Redis.from_url(self.redis_url, decode_responses=True)
        return self._sync_client

    def publish_event(self, channel: str, payload: Dict[str, Any]) -> bool:
        """Publish raw payload dict into channel."""
        client = self._get_sync_client()
        if client is None:
            return False

        body = json.dumps(payload, ensure_ascii=False)
        try:
            client.publish(channel, body)
            return True
        except Exception:
            # В случае stale-соединения пробуем 1 re-connect и повтор.
            try:
                self._sync_client = Redis.from_url(self.redis_url, decode_responses=True)
                assert self._sync_client is not None
                self._sync_client.publish(channel, body)
                return True
            except Exception:
                return False

    async def listener(
        self,
        channel: str,
        on_message: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Listen channel forever and pass decoded payload to callback."""
        if not self.redis_url or redis_async is None:
            return

        redis_conn = redis_async.from_url(self.redis_url, decode_responses=True)
        pubsub = redis_conn.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for msg in pubsub.listen():
                if not msg or msg.get("type") != "message":
                    continue
                raw = msg.get("data")
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    await on_message(payload)
        finally:
            try:
                await pubsub.unsubscribe(channel)
            except Exception:
                pass
            try:
                await pubsub.close()
            except Exception:
                pass
            try:
                await redis_conn.close()
            except Exception:
                pass


_broker_singleton: Optional[RedisBroker] = None


def get_broker() -> RedisBroker:
    global _broker_singleton
    if _broker_singleton is None:
        _broker_singleton = RedisBroker()
    return _broker_singleton


def publish(event: str, data: Dict[str, Any]) -> bool:
    """Backward-compatible helper for existing call-sites."""
    payload = {"event": event, "data": data}
    return get_broker().publish_event(get_channel(), payload)


async def subscribe_forever(
    *,
    redis_url: str,
    channel: str,
    on_event: Callable[[str, Dict[str, Any]], Awaitable[None]],
) -> None:
    """Backward-compatible listener: maps payload to ``on_event(event, data)``."""
    broker = RedisBroker(redis_url=redis_url)

    async def _on_payload(payload: Dict[str, Any]) -> None:
        event = payload.get("event")
        data = payload.get("data")
        if isinstance(event, str) and isinstance(data, dict):
            await on_event(event, data)

    await broker.listener(channel, _on_payload)


async def matrix_telemetry_stream(
    redis_client: Any,
    *,
    channel: str = MATRIX_NOISE_CHANNEL,
) -> None:
    """Background generator of synthetic cyber telemetry for frontend HUD."""
    logger.info("Запуск потока системной телеметрии [MATRIX_NOISE]...")
    try:
        while True:
            payload = {
                "event": "SYS_TELEMETRY",
                "data": {
                    "cpu_load": round(random.uniform(12.0, 98.9), 1),
                    "ram_usage": round(random.uniform(45.0, 88.5), 1),
                    "active_nodes": random.randint(120, 500),
                    "net_traffic": f"{random.randint(10, 999)} MB/s",
                    "hex_dump": "".join(random.choices("0123456789ABCDEF", k=24)),
                },
            }
            await redis_client.publish(channel, json.dumps(payload, ensure_ascii=False))
            await asyncio.sleep(random.uniform(0.3, 1.5))
    except asyncio.CancelledError:
        logger.info("Поток телеметрии остановлен.")
        raise



def flush_telemetry_batch(points: list[Dict[str, Any]]) -> int:
    """Bulk insert telemetry points into DB in one transaction."""
    if not points:
        return 0

    from ..extensions import db
    from ..models import TrackingPoint

    db.session.bulk_insert_mappings(TrackingPoint, points)
    db.session.commit()
    return len(points)


async def consume_telemetry_save_queue(
    *,
    channel: str = DEFAULT_TELEMETRY_QUEUE,
    batch_size: int = 100,
    flush_interval_sec: float = 0.5,
) -> None:
    """Consume telemetry queue and flush points to DB in batches."""
    if redis_async is None:
        return

    redis_url = get_redis_url()
    if not redis_url:
        return

    try:
        from compat_flask import current_app

        app_ctx_manager = current_app.app_context()
    except Exception:
        from app import create_app

        app_ctx_manager = create_app().app_context()

    with app_ctx_manager:
        redis_conn = redis_async.from_url(redis_url, decode_responses=True)
        pubsub = redis_conn.pubsub()
        await pubsub.subscribe(channel)

        batch: list[Dict[str, Any]] = []
        loop = asyncio.get_running_loop()
        last_flush = loop.time()

        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "message":
                    raw = msg.get("data")
                    if raw:
                        try:
                            payload = json.loads(raw)
                            if isinstance(payload, dict):
                                norm = _normalize_telemetry_payload(payload)
                                if norm is not None:
                                    batch.append(norm)
                        except Exception:
                            pass

                now = loop.time()
                if batch and (len(batch) >= batch_size or (now - last_flush) >= flush_interval_sec):
                    try:
                        flush_telemetry_batch(batch)
                    finally:
                        batch.clear()
                        last_flush = now
        finally:
            if batch:
                try:
                    flush_telemetry_batch(batch)
                finally:
                    batch.clear()
            try:
                await pubsub.unsubscribe(channel)
            except Exception:
                pass
            try:
                await pubsub.close()
            except Exception:
                pass
            try:
                await redis_conn.close()
            except Exception:
                pass
