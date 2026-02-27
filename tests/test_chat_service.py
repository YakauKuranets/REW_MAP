from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import ChatMessage, PendingMarker
from app.services import chat_service


@pytest.fixture(autouse=True)
def patch_external(monkeypatch):
    """Подменяем отправку в Telegram и WebSocket, чтобы не дергать внешние сервисы."""
    def fake_send_telegram_message(user_id, text):
        return True, None

    def fake_broadcast_event_sync(event, payload):
        # Ничего не делаем
        return None

    monkeypatch.setattr("app.services.chat_service.send_telegram_message", fake_send_telegram_message)
    monkeypatch.setattr("app.services.chat_service.broadcast_event_sync", fake_broadcast_event_sync)


def test_list_conversations_and_unread(db_session):
    # Подготовим данные: один пользователь с тремя сообщениями
    user_id = "123"
    m1 = ChatMessage(user_id=user_id, text="hi", sender="user")
    m2 = ChatMessage(user_id=user_id, text="hello", sender="admin")
    m3 = ChatMessage(user_id=user_id, text="again", sender="user")
    db.session.add_all([m1, m2, m3])

    # Немного другой пользователь
    m4 = ChatMessage(user_id="456", text="yo", sender="user")
    db.session.add(m4)

    db.session.commit()

    conversations = chat_service.list_conversations()
    ids = {c["user_id"] for c in conversations}
    assert {"123", "456"}.issubset(ids)

    conv_123 = next(c for c in conversations if c["user_id"] == "123")
    # Должны быть непрочитанные сообщения от пользователя
    assert conv_123["unread"] == 2
    assert conv_123["last_text"] in {"again", "hello"}


def test_get_history_marks_user_messages_as_read(db_session):
    user_id = "777"
    m1 = ChatMessage(user_id=user_id, text="hi", sender="user", is_read=False)
    m2 = ChatMessage(user_id=user_id, text="reply", sender="admin", is_read=True)
    db.session.add_all([m1, m2])
    db.session.commit()

    history = chat_service.get_history(user_id)
    assert len(history) == 2

    # после вызова user-сообщения должны быть прочитанными
    db.session.refresh(m1)
    assert m1.is_read is True


def test_send_message_creates_record_and_calls_external(db_session):
    user_id = "999"

    result = chat_service.send_message(user_id=user_id, text="hello", sender="admin")
    assert result["text"] == "hello"
    assert result["sender"] == "admin"

    msg = ChatMessage.query.filter_by(user_id=user_id).first()
    assert msg is not None
    assert msg.text == "hello"
