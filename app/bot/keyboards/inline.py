"""Inline keyboards for cyber UI quick actions."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


CALL_ACCEPT = "dispatch:accept"
CALL_ON_SITE = "dispatch:on_site"
CALL_SOS = "dispatch:sos"


def dispatch_actions_keyboard() -> InlineKeyboardMarkup:
    """Return inline keyboard for one-tap dispatcher actions."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Принять вызов", callback_data=CALL_ACCEPT)],
            [InlineKeyboardButton(text="На месте 📍", callback_data=CALL_ON_SITE)],
            [InlineKeyboardButton(text="🚨 SOS", callback_data=CALL_SOS)],
        ]
    )


def terminal_webapp_keyboard(url: str) -> InlineKeyboardMarkup:
    """Inline button that opens Telegram Mini App terminal."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть Терминал", web_app=WebAppInfo(url=url))]]
    )
