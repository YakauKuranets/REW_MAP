import asyncio
import functools
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _is_serialization_failure(exc: Exception) -> bool:
    sqlstate = getattr(exc, "sqlstate", None)
    if sqlstate == "40001":
        return True
    txt = str(exc)
    return "40001" in txt or "SerializationFailure" in txt or "serialization failure" in txt.lower()


def retry_on_serialization_failure(max_retries: int = 3, delay: float = 0.5):
    """Retry wrapper for CockroachDB serialization conflicts (SQLSTATE 40001)."""

    def decorator(func: Callable[..., Any]):
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                for attempt in range(max_retries):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        if _is_serialization_failure(e):
                            logger.warning(
                                "[CockroachDB] Конфликт транзакций (Попытка %s/%s). Повтор через %.2fs...",
                                attempt + 1,
                                max_retries,
                                delay,
                            )
                            await asyncio.sleep(delay * (attempt + 1))
                            continue
                        raise
                logger.error("[CockroachDB] Транзакция окончательно провалена после всех попыток.")
                raise Exception("Max retries reached for CockroachDB transaction")

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if _is_serialization_failure(e):
                        logger.warning(
                            "[CockroachDB] Конфликт транзакций (Попытка %s/%s). Повтор через %.2fs...",
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        import time

                        time.sleep(delay * (attempt + 1))
                        continue
                    raise
            logger.error("[CockroachDB] Транзакция окончательно провалена после всех попыток.")
            raise Exception("Max retries reached for CockroachDB transaction")

        return sync_wrapper

    return decorator
