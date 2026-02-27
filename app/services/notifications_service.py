"""Сервис уведомлений (агрегированные счётчики).

Задача этого модуля — вернуть компактный словарь с числом
«важных» объектов для администратора:

- сколько входящих заявок в очереди (колокольчик);
- сколько ожидающих маркеров (pending);
- сколько непрочитанных сообщений в чате.

Эти данные используются фронтендом для отрисовки бейджей и
индикаторов (колокольчик, индикатор у кнопки чата и т.п.).
"""

from __future__ import annotations

from typing import Dict

from sqlalchemy import func

from ..extensions import db
from ..models import PendingMarker, ChatDialog, ChatMessage
from .requests_service import get_requests_count


def get_notification_counters() -> Dict[str, int]:
    """Вернуть агрегированные счётчики уведомлений.

    Структура результата:

    - ``requests`` — количество заявок (используется колокольчиком);
    - ``pending`` — синоним для количества PendingMarker (на будущее);
    - ``chat_unread`` — общее количество непрочитанных сообщений
      от пользователей во всех диалогах;
    - ``total`` — суммарное «количество дел» (requests + chat_unread).
    """
    # Заявки в очереди — считаем через существующий сервис
    requests_count = int(get_requests_count() or 0)

    # PendingMarker сейчас совпадает по смыслу с заявками, но оставляем
    # отдельное поле на будущее, если логика разъедется.
    pending_count = int(
        db.session.query(func.count(PendingMarker.id)).scalar() or 0
    )

    # Непрочитанные сообщения чата. В первую очередь используем агрегат
    # по ChatDialog.unread_for_admin, чтобы не обходить всю таблицу сообщений.
    chat_unread = (
        db.session.query(func.coalesce(func.sum(ChatDialog.unread_for_admin), 0))
        .scalar()
        or 0
    )
    chat_unread = int(chat_unread)

    # Если по каким-либо причинам диалоги ещё не созданы, делаем
    # резервный расчёт по флагу ChatMessage.is_read.
    if chat_unread == 0:
        fallback = (
            db.session.query(func.count(ChatMessage.id))
            .filter(
                ChatMessage.sender == "user",
                ChatMessage.is_read == False,  # noqa: E712
            )
            .scalar()
            or 0
        )
        chat_unread = int(fallback)

    total = int(requests_count + chat_unread)

    return {
        "requests": requests_count,
        "pending": pending_count,
        "chat_unread": chat_unread,
        "total": total,
    }
