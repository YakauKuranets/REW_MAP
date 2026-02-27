"""Тесты для административных маршрутов.

Административные эндпоинты предоставляют сводку и списки
заявок/адресов для бота. Эти тесты проверяют, что базовые
операции работают и возвращают корректную структуру данных.
"""


def test_admin_summary(client):
    resp = client.get('/admin/summary')
    assert resp.status_code == 200
    data = resp.get_json()
    # В ответе должны быть ключи с числом заявок и адресов
    assert 'pending_count' in data
    assert 'approved_count' in data
    assert 'rejected_count' in data
    assert 'new_addresses' in data
    assert 'total_addresses' in data