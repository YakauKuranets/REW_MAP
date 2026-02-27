"""Callback query handlers for command center bridge."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ...realtime.broker import get_channel, get_broker
from ..keyboards.inline import CALL_ACCEPT, CALL_ON_SITE, CALL_SOS

router = Router(name="callbacks")


def _publish_map_update(payload: dict) -> None:
    get_broker().publish_event(get_channel(), payload)


@router.callback_query(F.data == CALL_ACCEPT)
async def on_accept_call(callback: CallbackQuery) -> None:
    """Handle 'accept call' click with immediate ack + event publish."""
    agent_id = int(callback.from_user.id)
    _publish_map_update({"event": "agent_accept_call", "agent_id": agent_id})
    await callback.answer("Вызов принят")


@router.callback_query(F.data == CALL_ON_SITE)
async def on_agent_on_site(callback: CallbackQuery) -> None:
    """Handle 'on site' action, edit message and publish bridge event."""
    agent_id = int(callback.from_user.id)

    if callback.message:
        await callback.message.edit_text("✅ Статус обновлен: агент на месте.")

    _publish_map_update({"event": "agent_on_site", "agent_id": agent_id})
    await callback.answer("Отметка отправлена")


@router.callback_query(F.data == CALL_SOS)
async def on_sos(callback: CallbackQuery) -> None:
    """Handle SOS click and publish emergency event for command center."""
    agent_id = int(callback.from_user.id)
    _publish_map_update({"event": "agent_sos", "agent_id": agent_id})
    await callback.answer("SOS отправлен в штаб", show_alert=True)
