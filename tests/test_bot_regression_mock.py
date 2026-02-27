import importlib
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture()
def bot_module(monkeypatch):
    monkeypatch.setenv("MAP_BOT_TOKEN", "test-token")
    monkeypatch.setenv("BOT_API_KEY", "k")
    if "bot" in list(importlib.sys.modules):
        importlib.reload(importlib.import_module("bot"))
    mod = importlib.import_module("bot")
    return importlib.reload(mod)


@pytest.fixture()
def fake_update():
    msg = SimpleNamespace(text="", reply_text=AsyncMock())
    user = SimpleNamespace(id=777, username="tester", full_name="Test User")
    return SimpleNamespace(message=msg, effective_message=msg, effective_user=user)


@pytest.fixture()
def fake_context():
    return SimpleNamespace(user_data={})


def test_connect_returns_intent_link(bot_module, fake_update, fake_context, monkeypatch):
    async def _ok(*_args, **_kwargs):
        return True

    async def _req(*_args, **_kwargs):
        return {"status": "approved", "_http_status": 200}

    async def _status(*_args, **_kwargs):
        return {
            "_http_status": 200,
            "request": {
                "issued": {
                    "base_url": "https://example.local",
                    "pair_code": "111222",
                    "bootstrap_token": "btok",
                }
            },
        }

    monkeypatch.setattr(bot_module, "_ensure_service_role", _ok)
    monkeypatch.setattr(bot_module, "_mobile_connect_request", _req)
    monkeypatch.setattr(bot_module, "_mobile_connect_status", _status)

    asyncio.run(bot_module.cmd_connect(fake_update, fake_context))

    call = fake_update.message.reply_text.await_args
    text = call.args[0] if call.args else call.kwargs.get("text")
    assert "intent://bootstrap" in text


def test_unit_sos_checkin_flows(bot_module, fake_update, fake_context, monkeypatch):
    async def _ok(*_args, **_kwargs):
        return True

    async def _post(path, payload):
        if path.endswith("set_unit"):
            return {"ok": True}
        if path.endswith("/sos/last"):
            return {"ok": True}
        return {"ok": True, "shift_id": 1}

    monkeypatch.setattr(bot_module, "_ensure_service_role", _ok)
    monkeypatch.setattr(bot_module, "_duty_post_json", _post)

    fake_update.message.text = "/unit A-01"
    asyncio.run(bot_module.cmd_unit(fake_update, fake_context))
    last_call = fake_update.message.reply_text.await_args_list[-1]
    last_text = last_call.args[0] if last_call.args else last_call.kwargs.get("text")
    assert "A-01" in last_text

    asyncio.run(bot_module.cmd_sos(fake_update, fake_context))
    last_call = fake_update.message.reply_text.await_args_list[-1]
    last_text = last_call.args[0] if last_call.args else last_call.kwargs.get("text")
    assert "SOS отправлен" in last_text

    asyncio.run(bot_module.cmd_checkin(fake_update, fake_context))
    assert fake_context.user_data.get("await_duty_checkin") is True


def test_chat_unread_for_user_counter(bot_module, monkeypatch):
    class DummyResponse:
        def __init__(self):
            self.text = '{"unread_for_user": 3}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"unread_for_user": 3}

    monkeypatch.setattr(bot_module.requests, "get", lambda *args, **kwargs: DummyResponse())
    unread = asyncio.run(bot_module._fetch_unread_for_user("777"))
    assert unread == 3
