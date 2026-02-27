"""Handlers registry for aiogram 3 bot."""

from aiogram import Dispatcher

from .callbacks import router as callbacks_router
from .common import router as common_router
from .voice import router as voice_router


def register_handlers(dp: Dispatcher) -> None:
    """Register all bot routers."""
    dp.include_router(common_router)
    dp.include_router(callbacks_router)
    dp.include_router(voice_router)
