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


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Main keyboard with Telegram Mini App launch button."""
    mini_app_url = (os.getenv("MINI_APP_URL") or "https://example.com/miniapp").strip()
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🗺 Открыть штаб (Mini App)", web_app=WebAppInfo(url=mini_app_url))],
            [KeyboardButton(text="🚨 Сообщить об инциденте")],
        ],
        resize_keyboard=True,
    )


def quick_actions_inline() -> InlineKeyboardMarkup:
    """Inline quick actions for low-latency HQ interaction."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📍 Отправить геопозицию", callback_data="hq:send_location")],
            [InlineKeyboardButton(text="🆘 SOS", callback_data="hq:sos")],
        ]
    )
