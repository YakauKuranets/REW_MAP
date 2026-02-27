import pytest

from app.extensions import db
from app.models import ChatMessage
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


def test_api_chat_conversations(client, db_session):
    user_id = "123"
    m1 = ChatMessage(user_id=user_id, text="hi", sender="user")
    m2 = ChatMessage(user_id=user_id, text="hello", sender="admin")
    db.session.add_all([m1, m2])
    db.session.commit()

    rv = client.get('/api/chat/conversations')
    assert rv.status_code == 200
    data = rv.get_json()
    assert isinstance(data, list)
    assert any(c['user_id'] == user_id for c in data)


def test_api_chat_history_and_send(client, db_session):
    user_id = "777"
    m1 = ChatMessage(user_id=user_id, text="old", sender="user")
    db.session.add(m1)
    db.session.commit()

    # история
    rv_hist = client.get(f'/api/chat/{user_id}')
    assert rv_hist.status_code == 200
    hist = rv_hist.get_json()
    assert len(hist) == 1
    assert hist[0]['text'] == 'old'

    # отправка нового сообщения от админа
    rv_send = client.post(f'/api/chat/{user_id}', json={'text': 'hello from admin', 'sender': 'admin'})
    assert rv_send.status_code == 201
    msg = rv_send.get_json()
    assert msg['text'] == 'hello from admin'
    assert msg['sender'] == 'admin'

    # история теперь содержит два сообщения
    rv_hist2 = client.get(f'/api/chat/{user_id}')
    assert rv_hist2.status_code == 200
    hist2 = rv_hist2.get_json()
    texts = [m['text'] for m in hist2]
    assert 'old' in texts and 'hello from admin' in texts
