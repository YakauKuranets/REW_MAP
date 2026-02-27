"""Простая in-memory система ограничения скорости.

Ограничивает количество вызовов определённого действия в заданное окно
времени. Используется для защиты чата от спама и чрезмерной нагрузки.

Замечание: эти счётчики хранятся в памяти процесса, поэтому при
многопроцессном развёртывании ограничения действуют только внутри
конкретного процесса. Для production можно заменить на Redis или иной
внешний стор.
"""

from __future__ import annotations

import time
from typing import Dict, Tuple

_records: Dict[Tuple[str, str, str], Dict[str, float]] = {}

def check_rate(key: Tuple[str, str, str], window_seconds: float, limit: int) -> bool:
    """Проверить, допускается ли ещё один вызов для данного ключа.

    Args:
        key: Кортеж, идентифицирующий отправителя и тип действия.
        window_seconds: Длительность окна в секундах.
        limit: Максимальное количество вызовов в этом окне.

    Returns:
        True, если действие разрешено (счётчик увеличен), иначе False.
    """
    now = time.time()
    rec = _records.get(key)
    if not rec or now - rec["last_reset"] >= window_seconds:
        # Начинаем новое окно
        _records[key] = {"last_reset": now, "count": 1}
        return True
    if rec["count"] >= limit:
        # Достигнут лимит
        return False
    # Увеличиваем счётчик
    rec["count"] += 1
    return True