#!/usr/bin/env python3
"""aiogram 3 bot entrypoint with Redis FSM + webhook/polling modes.

Production mode (recommended):
- set WEBHOOK_BASE_URL (e.g. https://bot.example.com)
- optional WEBHOOK_PATH (default: /telegram/webhook)
- run embedded aiohttp server on WEBHOOK_HOST:WEBHOOK_PORT

Fallback mode (dev):
- if WEBHOOK_BASE_URL is not set, bot runs long polling
"""

from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Update
from redis.asyncio import Redis

from app.bot.handlers import register_handlers
from app.bot.middlewares import LoggingMiddleware


log = logging.getLogger("map-bot")


def _get_token() -> str:
    token = (os.getenv("MAP_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("MAP_BOT_TOKEN / BOT_TOKEN is not set")
    return token


def _get_redis_url() -> str:
    return (os.getenv("REDIS_URL") or "redis://127.0.0.1:6379/0").strip()


def _build_dispatcher() -> Dispatcher:
    redis = Redis.from_url(_get_redis_url(), decode_responses=True)
    storage = RedisStorage(redis=redis)
    dp = Dispatcher(storage=storage)
    dp.update.middleware(LoggingMiddleware())
    register_handlers(dp)
    return dp


async def _webhook_handler(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    dp: Dispatcher = request.app["dp"]

    expected_secret = request.app.get("webhook_secret")
    if expected_secret:
        got_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if got_secret != expected_secret:
            return web.Response(status=401, text="unauthorized")

    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return web.Response(text="ok")


async def _run_webhook(bot: Bot, dp: Dispatcher) -> None:
    base_url = (os.getenv("WEBHOOK_BASE_URL") or "").strip().rstrip("/")
    webhook_path = (os.getenv("WEBHOOK_PATH") or "/telegram/webhook").strip()
    if not webhook_path.startswith("/"):
        webhook_path = "/" + webhook_path

    webhook_secret = (os.getenv("WEBHOOK_SECRET") or "").strip() or None
    webhook_url = f"{base_url}{webhook_path}"

    await bot.set_webhook(url=webhook_url, secret_token=webhook_secret, drop_pending_updates=True)

    app = web.Application()
    app["bot"] = bot
    app["dp"] = dp
    app["webhook_secret"] = webhook_secret
    app.router.add_post(webhook_path, _webhook_handler)

    async def _on_shutdown(_app: web.Application) -> None:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.storage.close()
        await bot.session.close()

    app.on_shutdown.append(_on_shutdown)

    host = (os.getenv("WEBHOOK_HOST") or "0.0.0.0").strip()
    port = int(os.getenv("WEBHOOK_PORT") or "8081")

    log.info("Starting webhook server on %s:%s, path=%s", host, port, webhook_path)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()

    # Keep process alive
    await asyncio.Event().wait()


async def main() -> None:
    logging.basicConfig(
        level=os.getenv("BOT_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    bot = Bot(token=_get_token(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = _build_dispatcher()

    webhook_base_url = (os.getenv("WEBHOOK_BASE_URL") or "").strip()
    if webhook_base_url:
        await _run_webhook(bot, dp)
        return

    log.warning("WEBHOOK_BASE_URL is not set: falling back to long polling (dev mode)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
