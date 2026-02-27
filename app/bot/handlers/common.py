"""Common bot handlers (aiogram 3)."""

from __future__ import annotations

import os

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from ..keyboards.inline import dispatch_actions_keyboard, terminal_webapp_keyboard
from ..keyboards.main import get_main_keyboard

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Entry command with Mini App + inline quick actions."""
    await message.answer(
        "🚀 Бот переведен на aiogram 3.\n"
        "Используйте меню ниже для запуска Mini App и быстрых действий.",
        reply_markup=get_main_keyboard(),
    )
    await message.answer("Быстрые действия:", reply_markup=dispatch_actions_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start — старт\n"
        "/help — помощь\n/terminal — открыть TWA-терминал\n\n"
        "Inline-кнопки используются для мгновенной связи со штабом."
    )


@router.message(Command("terminal"))
async def cmd_terminal(message: Message) -> None:
    """Open agent terminal Mini App via Telegram WebApp button."""
    base_url = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    terminal_url = f"{base_url}/webapp" if base_url else "https://your-production-domain.com/webapp"
    await message.answer(
        "🛰 Откройте терминал агента:",
        reply_markup=terminal_webapp_keyboard(terminal_url),
    )
