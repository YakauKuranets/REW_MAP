# -*- coding: utf-8 -*-
"""
Клиент для маршрутизации трафика через распределённую сеть прокси.
Используется для снижения нагрузки на целевые ресурсы и скрытия источника запросов
при authorised тестировании. Базируется на протоколе SOCKS5.
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

# Адрес прокси-сервера в Docker-сети (можно переопределить через переменную окружения)
PROXY_URL = os.getenv("PROXY_SOCKS5", "socks5h://proxy:9050")


def get_proxy_session() -> requests.Session:
    """
    Возвращает сессию requests, настроенную на использование прокси.
    Все запросы через эту сессию будут проходить через заданный SOCKS5-прокси.
    """
    session = requests.Session()
    session.proxies = {
        'http': PROXY_URL,
        'https': PROXY_URL,
    }
    return session


def check_current_ip() -> str:
    """
    Проверяет внешний IP-адрес, с которого выполняются запросы через прокси.
    Позволяет убедиться, что маршрутизация работает корректно.
    """
    try:
        session = get_proxy_session()
        response = session.get("https://api.ipify.org?format=json", timeout=10)
        ip = response.json().get("ip")
        logger.info("[Proxy] Текущий внешний IP: %s", ip)
        return ip
    except Exception as exc:
        logger.error("[Proxy] Ошибка подключения к прокси: %s", exc)
        return "DISCONNECTED"
