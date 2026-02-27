"""Тесты для проверки списка диалогов с учётом активных и прошедших заявок.

Эти тесты проверяют, что пользователь, отправивший заявку (pending),
но ещё не отправивший сообщений в чат, появляется в списке диалогов.
Также проверяем, что история для такого пользователя пустая.
"""

def test_chat_conversations_include_pending_user(client):
    """Создаём заявку от пользователя без сообщений и убеждаемся,
    что он появляется в списке диалогов."""
    from app.models import db, PendingMarker
    # Создаём pending‑заявку с user_id '99'
    with client.application.app_context():
        p = PendingMarker(name='Точка для чата', user_id='99')
        db.session.add(p)
        db.session.commit()
    # Запрашиваем список диалогов
    resp = client.get('/api/chat/conversations')
    assert resp.status_code == 200
    convs = resp.get_json()
    # Ищем пользователя 99
    found = next((c for c in convs if c['user_id'] == '99'), None)
    assert found is not None, "Пользователь из pending должен быть в списке диалогов"
    # Для пользователя без сообщений last_text должен быть пустым
    assert found['last_text'] == ''
    assert found['last_sender'] == 'user'
    # Проверяем, что история диалога пустая
    hist_resp = client.get('/api/chat/99')
    assert hist_resp.status_code == 200
    assert hist_resp.get_json() == []