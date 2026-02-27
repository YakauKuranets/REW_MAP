from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx


def build_dutytracker_deeplink(base_url: str, token: str) -> str:
    base_url = (base_url or "").strip().rstrip("/")
    token = (token or "").strip()
    return f"dutytracker://bootstrap?base_url={quote(base_url, safe='')}&token={quote(token, safe='')}"


def build_dutytracker_intent_link(base_url: str, token: str) -> str:
    """intent://-ссылка для более надёжного открытия на Android."""
    base_url = (base_url or "").strip().rstrip("/")
    token = (token or "").strip()
    q_base = quote(base_url, safe='')
    q_token = quote(token, safe='')
    return (
        "intent://bootstrap"
        f"?base_url={q_base}&token={q_token}"
        "#Intent;scheme=dutytracker;package=com.mapv12.dutytracker;end"
    )




def build_dutytracker_open_url(base_url: str, token: str) -> str:
    """HTTP-ссылка на страницу открытия, чтобы Telegram inline-кнопки принимали URL."""
    base_url = (base_url or "").strip().rstrip("/")
    token = (token or "").strip()
    return f"{base_url}/open/dutytracker?token={quote(token, safe='')}"

def send_telegram_message(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: Optional[str] = None,
    disable_web_preview: bool = True,
    timeout_sec: int = 12,
) -> Dict[str, Any]:
    """Best-effort отправка сообщения через Telegram Bot API.

    Proxy:
      TELEGRAM_PROXY — опционально. Поддерживаются http(s) прокси.
      SOCKS прокси потребуют установленного socksio (опциональная зависимость httpx).
    """
    bot_token = (bot_token or "").strip()
    if not bot_token:
        raise ValueError("bot_token is empty")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data: Dict[str, Any] = {
        "chat_id": str(chat_id),
        "text": text,
        "disable_web_page_preview": bool(disable_web_preview),
    }
    if parse_mode:
        data["parse_mode"] = parse_mode
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)

    proxy = (os.environ.get("TELEGRAM_PROXY") or "").strip() or None

    with httpx.Client(proxy=proxy, timeout=timeout_sec) as client:
        r = client.post(url, data=data)
        # Telegram часто возвращает 200 с ok=false — поэтому парсим JSON всегда
        try:
            payload = r.json()
        except Exception:
            payload = {"ok": False, "error": "invalid_json", "status_code": r.status_code, "text": r.text[:1000]}
        return payload


def send_dutytracker_connect_button(
    bot_token: str,
    tg_user_id: str,
    base_url: str,
    token: str,
    pair_code: str,
) -> Dict[str, Any]:
    # Telegram Bot API не принимает intent:// и custom-scheme в URL для inline-кнопок.
    # Поэтому даём http-страницу (/open/dutytracker), которая сама пытается открыть приложение.
    open_url = build_dutytracker_open_url(base_url, token)
    deeplink = build_dutytracker_deeplink(base_url, token)
    intent_link = build_dutytracker_intent_link(base_url, token)

    text = (
        "✅ DutyTracker: привязка готова\n"
        f"BASE_URL: {base_url}\n"
        f"Код привязки: {pair_code}\n\n"
        "1) Нажмите кнопку «Открыть страницу привязки».\n"
        "2) В браузере подтвердите открытие DutyTracker.\n"
        "3) Если не привязалось автоматически — откройте приложение и нажмите «Привязать».\n\n"
        "Если кнопка не сработала, откройте ссылку вручную:\n"
        f"{open_url}\n\n"
        "Запасной вариант (вручную, если надо):\n"
        f"{deeplink}\n"
        f"{intent_link}"
    )
    reply_markup = {
        "inline_keyboard": [
            [{"text": "Открыть страницу привязки", "url": open_url}],
        ]
    }
    return send_telegram_message(bot_token, tg_user_id, text, reply_markup=reply_markup)
