"""Простейшие счётчики метрик для chat2.

Эти счётчики увеличиваются при отправке сообщений, медиа, ошибках
ограничения скорости и отправке push‑уведомлений. Они могут быть
экспортированы в формате Prometheus через глобальный endpoint или
специальный маршрут.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict

_counters: Dict[str, int] = defaultdict(int)

def inc(metric: str, value: int = 1) -> None:
    """Увеличить значение счётчика.

    Args:
        metric: Имя счётчика, например ``chat2_messages_sent_total``.
        value: Приращение (по умолчанию 1).
    """
    _counters[metric] += value

def snapshot() -> Dict[str, int]:
    """Получить копию текущих значений всех счётчиков."""
    return dict(_counters)

def render_prometheus() -> str:
    """Сформировать текст в формате Prometheus с именами chat2_*"""
    lines = []
    for name, val in sorted(_counters.items()):
        pname = name.replace("-", "_")
        lines.append(f"{pname} {val}")
    return "\n".join(lines)