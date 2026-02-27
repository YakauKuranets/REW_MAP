"""Отправка push‑уведомлений через FCM/APNs.

Для работы необходим ключ ``FCM_SERVER_KEY`` в конфигурации Flask.
Если ключ не задан или ``CHAT2_PUSH_ENABLED`` не включён, функция
``send_push`` silently returns without doing anything.
"""

from __future__ import annotations

from typing import Dict, List, Optional
import json
import logging

import requests
from compat_flask import current_app

FCM_URL = "https://fcm.googleapis.com/fcm/send"

def send_push(title: str, body: str, tokens: List[str], data: Optional[Dict[str, str]] = None) -> Dict[str, int]:
    """Отправить push‑уведомление на список токенов.

    Args:
        title: Заголовок уведомления.
        body: Основной текст.
        tokens: Список устройств (FMC токены).
        data: Дополнительные данные (ключ-строка).

    Returns:
        Словарь с количеством успешно отправленных уведомлений.
    """
    if not tokens:
        return {"sent": 0}
    app = current_app._get_current_object()
    if not app.config.get("CHAT2_PUSH_ENABLED"):
        return {"sent": 0}
    server_key = app.config.get("FCM_SERVER_KEY")
    if not server_key:
        app.logger.debug("FCM_SERVER_KEY is not configured; push disabled")
        return {"sent": 0}
    headers = {
        "Authorization": f"key={server_key}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, any] = {
        "registration_ids": tokens,
        "notification": {
            "title": title,
            "body": body,
        },
    }
    if data:
        payload["data"] = data
    try:
        resp = requests.post(FCM_URL, headers=headers, data=json.dumps(payload), timeout=5)
        if resp.ok:
            try:
                res = resp.json()
                sent = int(res.get("success") or 0)
            except Exception:
                sent = 0
            return {"sent": sent}
        else:
            current_app.logger.debug("FCM push failed: %s %s", resp.status_code, resp.text)
    except Exception as exc:
        logging.getLogger(__name__).debug("FCM push error: %s", exc)
    return {"sent": 0}