import json


def test_address_crud(client):
    """Проверить создание, редактирование и удаление адреса через API."""
    # Создание адреса
    resp = client.post('/api/addresses', json={
        'name': 'Test Place',
        'lat': 10.0,
        'lon': 20.0,
        'notes': 'Тестовое описание',
        'status': 'Локальный доступ',
        'category': 'Видеонаблюдение',
        'link': ''
    })
    assert resp.status_code in (200, 201)
    addr = resp.get_json()
    addr_id = addr['id']
    # Получение списка адресов
    resp = client.get('/api/addresses')
    assert resp.status_code == 200
    data = resp.get_json()
    assert any(a['id'] == addr_id for a in data['items'])
    # Обновление адреса
    resp = client.put(f'/api/addresses/{addr_id}', json={
        'notes': 'Новое описание',
        'link': 'http://example.com',
    })
    assert resp.status_code == 200
    upd = resp.get_json()
    assert upd['notes'] == 'Новое описание'
    # Удаление адреса
    resp = client.delete(f'/api/addresses/{addr_id}')
    assert resp.status_code == 200
    # Проверяем, что адрес больше не существует
    resp = client.get('/api/addresses')
    assert addr_id not in [a['id'] for a in resp.get_json()['items']]


def test_chat_api(client):
    """Проверить API чата: создание сообщений и получение истории."""
    # Отправляем первое сообщение от пользователя user1
    resp = client.post('/api/chat/1', json={ 'text': 'Привет', 'sender': 'user' })
    assert resp.status_code in (200, 201)
    # Отправляем ответ от администратора
    resp = client.post('/api/chat/1', headers={'X-Admin': '1'}, json={ 'text': 'Здравствуйте' })
    assert resp.status_code in (200, 201)
    # Запрашиваем список диалогов
    resp = client.get('/api/chat/conversations')
    convs = resp.get_json()
    assert any(conv['user_id'] == '1' for conv in convs)
    # Запрашиваем историю диалога
    resp = client.get('/api/chat/1')
    history = resp.get_json()
    assert len(history) == 2


def test_admin_endpoints(client):
    """Проверяем административные GET‑эндпоинты summary, addresses, applications."""
    # Создаём пару адресов
    for i in range(2):
        client.post('/api/addresses', json={'name': f'A{i}', 'lat':0, 'lon':0})
    # Создаём заявку через pending_marker напрямую
    from app.models import db, PendingMarker, PendingHistory, Address
    # Создадим pending запись
    with client.application.app_context():
        p = PendingMarker(name='Req', lat=0, lon=0, user_id='2')
        db.session.add(p)
        db.session.commit()
        # Добавим запись истории
        h = PendingHistory(pending_id=p.id, status='approved', address_id=1)
        db.session.add(h)
        db.session.commit()
    # summary
    resp = client.get('/admin/summary')
    assert resp.status_code == 200
    summary = resp.get_json()
    assert 'pending' in summary and 'approved' in summary
    # addresses (админ выдаёт первые 10 адресов)
    resp = client.get('/admin/addresses')
    assert resp.status_code == 200
    addrs = resp.get_json()
    assert addrs['total'] >= 2
    # applications: pending
    resp = client.get('/admin/applications', query_string={'status': 'pending'})
    assert resp.status_code == 200
    # applications: approved
    resp = client.get('/admin/applications', query_string={'status': 'approved'})
    assert resp.status_code == 200
    # applications: rejected (none yet)
    resp = client.get('/admin/applications', query_string={'status': 'rejected'})
    assert resp.status_code == 200