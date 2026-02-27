"""Тесты для API чата.

Эти тесты проверяют, что сервер корректно обрабатывает создание
сообщений, получение истории и список диалогов.
"""

def test_chat_empty(client):
    # Сначала список диалогов должен быть пустым
    resp = client.get('/api/chat/conversations')
    assert resp.status_code == 200
    assert resp.get_json() == []
    # История для несуществующего пользователя тоже пустая
    resp2 = client.get('/api/chat/42')
    assert resp2.status_code == 200
    assert resp2.get_json() == []


def test_chat_send_and_fetch(client):
    # Отправляем два сообщения: от пользователя и от админа
    user_id = '42'
    # Сообщение от пользователя (без заголовка X-Admin)
    r1 = client.post(f'/api/chat/{user_id}', json={'text': 'Привет, админ!'})
    assert r1.status_code == 201
    msg1 = r1.get_json()
    assert msg1['sender'] == 'user'
    assert msg1['text'] == 'Привет, админ!'
    # Сообщение от администратора
    r2 = client.post(
        f'/api/chat/{user_id}',
        json={'text': 'Здравствуйте, чем помочь?'},
        headers={'X-Admin': '1'},
    )
    assert r2.status_code == 201
    msg2 = r2.get_json()
    assert msg2['sender'] == 'admin'
    # Получаем историю и проверяем порядок
    hist = client.get(f'/api/chat/{user_id}')
    assert hist.status_code == 200
    msgs = hist.get_json()
    assert len(msgs) == 2
    assert msgs[0]['sender'] == 'user'
    assert msgs[1]['sender'] == 'admin'