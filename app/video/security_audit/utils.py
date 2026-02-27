# -*- coding: utf-8 -*-
"""Вспомогательные функции и классы для имитации поведения пользователя."""

import random
import time
from typing import Dict


class RequestBehavior:
    """Имитация HTTP-запросов реального браузера."""

    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    ]

    @classmethod
    def headers(cls) -> Dict[str, str]:
        """Возвращает случайный набор HTTP-заголовков."""
        return {
            'User-Agent': random.choice(cls.USER_AGENTS),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Connection': 'keep-alive',
        }

    @classmethod
    def delay(cls, min_sec: float = 1.0, max_sec: float = 3.0):
        """Случайная задержка для имитации человеческого поведения."""
        time.sleep(random.uniform(min_sec, max_sec))