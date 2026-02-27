import json

from app.extensions import redis_client


def publish_progress(task_id: str, current: int, total: int, found: bool = False, password: str | None = None):
    """Публикует прогресс выполнения задачи в Redis канал."""
    message = {
        "type": "progress",
        "current": int(current),
        "total": int(total),
        "percent": int(current / total * 100) if total else 0,
        "found": bool(found),
    }
    if password:
        message["password"] = password
    redis_client.publish(f"task:{task_id}", json.dumps(message, ensure_ascii=False))
