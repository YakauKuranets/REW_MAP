import json


def test_analytics_summary(client, app_ctx):
    """Проверяем, что эндпоинт /api/analytics/summary возвращает корректную структуру."""
    # Создаем тестовые данные
    from app.models import db, Address, PendingMarker, PendingHistory
    # Удаляем всё
    db.session.query(Address).delete()
    db.session.query(PendingMarker).delete()
    db.session.query(PendingHistory).delete()
    db.session.commit()
    # Добавляем три адреса
    addr1 = Address(name='A1', lat=0, lon=0, status='Локальный доступ', category='Видеонаблюдение')
    addr2 = Address(name='A2', lat=0, lon=0, status='Удаленный доступ', category='Домофон')
    addr3 = Address(name='A3', lat=0, lon=0, status='Удаленный доступ', category='Видеонаблюдение')
    db.session.add_all([addr1, addr2, addr3])
    # Добавляем одну активную заявку
    pending = PendingMarker(name='P', lat=0, lon=0, user_id='123', notes='')
    db.session.add(pending)
    # Добавляем историю: одна одобрена, одна отклонена
    hist1 = PendingHistory(pending_id=1, status='approved', address_id=1)
    hist2 = PendingHistory(pending_id=2, status='rejected', address_id=None)
    db.session.add_all([hist1, hist2])
    db.session.commit()
    # Запросим сводку
    resp = client.get('/api/analytics/summary')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    # Проверяем ключи
    assert 'total' in data
    assert 'by_category' in data
    assert 'by_status' in data
    assert 'pending' in data
    assert 'approved' in data
    assert 'rejected' in data
    assert 'added_last_7d' in data
    # Проверяем значения
    assert data['total'] == 3
    assert data['pending'] == 1
    assert data['approved'] == 1
    assert data['rejected'] == 1