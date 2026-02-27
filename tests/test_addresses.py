"""Тесты для операций с адресами.

Проверяются создание, обновление и удаление адреса. Для операций,
требующих прав администратора, роль заносится в сессию через
session_transaction().
"""


def test_address_crud(client):
    # Назначаем роль admin в сессии
    with client.session_transaction() as sess:
        sess['role'] = 'admin'
    # Создаём адрес
    resp = client.post(
        '/api/addresses',
        json={
            'name': 'Тестовый адрес',
            'lat': 55.75,
            'lon': 37.62,
            'status': 'Локальный доступ',
            'category': 'Видеонаблюдение',
            'notes': '',
            'link': '',
        },
    )
    assert resp.status_code == 200
    addr_id = resp.get_json()['id']
    # Убеждаемся, что адрес присутствует в списке
    resp_list = client.get('/api/addresses')
    assert resp_list.status_code == 200
    addresses = resp_list.get_json()
    assert any(a['id'] == addr_id for a in addresses)
    # Обновляем адрес: добавляем описание
    resp_upd = client.put(
        f'/api/addresses/{addr_id}',
        json={'notes': 'Обновлённое описание'},
    )
    assert resp_upd.status_code == 200
    # Проверяем, что описание изменилось
    resp_list2 = client.get('/api/addresses')
    notes = [a['notes'] for a in resp_list2.get_json() if a['id'] == addr_id][0]
    assert notes == 'Обновлённое описание'
    # Удаляем адрес
    resp_del = client.delete(f'/api/addresses/{addr_id}')
    assert resp_del.status_code == 200
    # Адрес больше не возвращается
    resp_list3 = client.get('/api/addresses')
    assert all(a['id'] != addr_id for a in resp_list3.get_json())