"""API-key helpers.

В проекте есть несколько "не-cookie" клиентов:
  - Telegram-бот
  - Android трекер (использует device token)

Для Telegram-бота используем единый ключ BOT_API_KEY.

Если BOT_API_KEY не задан — поведение остаётся совместимым
с историческим режимом (эндпоинты не требуют ключа).
"""

from __future__ import annotations

from dataclasses import dataclass

from compat_flask import abort, current_app, request


@dataclass
class ApiKeyInfo:
    expected: str
    provided: str


def require_bot_api_key(allow_query_param: bool = True) -> ApiKeyInfo | None:
    """Проверить ключ BOT_API_KEY.

    Returns:
        ApiKeyInfo если ключ включен (даже при успехе) или None, если ключ не задан.
    """
    expected = (current_app.config.get("BOT_API_KEY") or "").strip()
    if not expected:
        return None

    provided = (request.headers.get("X-API-KEY") or "").strip()
    if not provided and allow_query_param:
        provided = (request.args.get("api_key") or "").strip()

    if provided != expected:
        abort(403)

    return ApiKeyInfo(expected=expected, provided=provided)
