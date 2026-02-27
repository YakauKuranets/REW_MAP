"""Bot keyboards: Mini App and inline quick actions."""

from __future__ import annotations

import os

from aiogram.types import (
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    WebAppInfo,
)


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Main keyboard with Telegram Mini App launch button."""
    terminal_url = (os.getenv("MINI_APP_URL") or "https://your-production-domain.com/webapp").strip()
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌐 Развернуть Терминал (WebGPU)", web_app=WebAppInfo(url=terminal_url))],
            [KeyboardButton(text="🚨 SOS / Экстренный Сброс")],
        ],
        resize_keyboard=True,
    )


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Backward-compatible alias for existing handlers."""
    return get_main_keyboard()


def quick_actions_inline() -> InlineKeyboardMarkup:
    """Inline quick actions for low-latency HQ interaction."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📍 Отправить геопозицию", callback_data="hq:send_location")],
            [InlineKeyboardButton(text="🆘 SOS", callback_data="hq:sos")],
        ]
    )
