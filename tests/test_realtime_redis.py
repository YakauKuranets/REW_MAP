import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.realtime import broker as broker_module
from app.realtime.broker import RedisBroker


class _FakeBus:
    def __init__(self):
        self.subscribers = {}

    def add_subscriber(self, channel: str, q: asyncio.Queue) -> None:
        self.subscribers.setdefault(channel, []).append(q)

    def publish(self, channel: str, payload: str) -> None:
        for q in list(self.subscribers.get(channel, [])):
            q.put_nowait({"type": "message", "data": payload})


class _FakeSyncRedis:
    _bus = _FakeBus()

    @classmethod
    def from_url(cls, _url: str, decode_responses: bool = True):
        return cls()

    def publish(self, channel: str, payload: str) -> None:
        self._bus.publish(channel, payload)


class _FakePubSub:
    def __init__(self, bus: _FakeBus):
        self._bus = bus
        self._queue = asyncio.Queue()

    async def subscribe(self, channel: str):
        self._bus.add_subscriber(channel, self._queue)

    async def listen(self):
        while True:
            yield await self._queue.get()

    async def unsubscribe(self, channel: str):
        return None

    async def close(self):
        return None


class _FakeAsyncRedisConn:
    def __init__(self, bus: _FakeBus):
        self._bus = bus

    def pubsub(self):
        return _FakePubSub(self._bus)

    async def close(self):
        return None


class _FakeAsyncRedisModule:
    @staticmethod
    def from_url(_url: str, decode_responses: bool = True):
        return _FakeAsyncRedisConn(_FakeSyncRedis._bus)


def test_redis_broker_publishes_to_two_listeners_under_50ms(monkeypatch):
    monkeypatch.setattr(broker_module, "Redis", _FakeSyncRedis)
    monkeypatch.setattr(broker_module, "redis_async", _FakeAsyncRedisModule)

    async def _run():
        broker = RedisBroker(redis_url="redis://fake")
        got = []
        done = asyncio.Event()

        async def _cb(payload):
            got.append(payload)
            if len(got) >= 2:
                done.set()

        task1 = asyncio.create_task(broker.listener("map_updates", _cb))
        task2 = asyncio.create_task(broker.listener("map_updates", _cb))

        await asyncio.sleep(0.01)
        t0 = time.perf_counter()
        ok = broker.publish_event("map_updates", {"event": "pending_created", "data": {"id": 777}})
        assert ok is True

        await asyncio.wait_for(done.wait(), timeout=0.5)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 50
        assert len(got) >= 2
        assert all(item.get("event") == "pending_created" for item in got[:2])

        task1.cancel()
        task2.cancel()
        await asyncio.gather(task1, task2, return_exceptions=True)

    asyncio.run(_run())


def _build_init_data(bot_token: str, user: dict) -> str:
    data = {
        "auth_date": "1700000000",
        "query_id": "AAEAAAE",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(data.items(), key=lambda kv: kv[0]))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    sig = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    data["hash"] = sig
    return urlencode(data)


def test_webapp_submit_publishes_pending_created_to_redis(client, app, monkeypatch):
    class FakeBroker:
        def __init__(self):
            self.published = []

        def publish_event(self, channel, payload):
            self.published.append((channel, payload))
            return True

    fake = FakeBroker()
    monkeypatch.setattr("app.realtime.broker.get_broker", lambda: fake)

    token = "bot-secret"
    app.config["TELEGRAM_BOT_TOKEN"] = token
    init_data = _build_init_data(token, {"id": 12345, "username": "miniuser", "last_name": "Иванов"})

    rv = client.post(
        "/api/bot/webapp_submit",
        json={
            "category": "Охрана",
            "description": "Описание из мини-аппа",
            "coords": {"lat": 53.9, "lon": 27.56},
            "photo": "https://cdn.example/img.jpg",
            "initData": init_data,
        },
    )
    assert rv.status_code == 200
    assert fake.published, "No Redis publish happened"
    channel, payload = fake.published[-1]
    assert channel == "map_updates"
    assert payload.get("event") == "pending_created"
    assert isinstance(payload.get("data"), dict)
