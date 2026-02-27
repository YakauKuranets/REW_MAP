from app.extensions import db
from app.models import PendingMarker


def _make_admin(client):
    # Устанавливаем роль администратора напрямую через сессию
    with client.session_transaction() as sess:
        sess['role'] = 'admin'
        sess['username'] = 'admin'


def test_pending_count_public(client, db_session):
    # публичный эндпоинт /api/pending/count
    rv = client.get('/api/pending/count')
    assert rv.status_code == 200
    data = rv.get_json()
    assert 'count' in data
    assert data['count'] == 0

    # создаём пару заявок и проверяем, что счётчик обновился
    p1 = PendingMarker(name='P1', lat=1.0, lon=2.0)
    p2 = PendingMarker(name='P2', lat=3.0, lon=4.0)
    db.session.add_all([p1, p2])
    db.session.commit()

    rv2 = client.get('/api/pending/count')
    assert rv2.status_code == 200
    data2 = rv2.get_json()
    assert data2['count'] == 2


def test_pending_admin_flow_list_approve_reject_clear(client, db_session):
    _make_admin(client)

    # создаём три заявки
    p1 = PendingMarker(name='P1', lat=1.0, lon=2.0)
    p2 = PendingMarker(name='P2', lat=3.0, lon=4.0)
    p3 = PendingMarker(name='P3', lat=5.0, lon=6.0)
    db.session.add_all([p1, p2, p3])
    db.session.commit()

    # список pending
    rv = client.get('/api/pending')
    assert rv.status_code == 200
    items = rv.get_json()
    assert len(items) == 3

    # approve p1
    rv_appr = client.post(f'/api/pending/{p1.id}/approve')
    assert rv_appr.status_code == 200
    data_appr = rv_appr.get_json()
    assert data_appr['status'] == 'ok'
    assert 'id' in data_appr  # id созданного адреса

    # reject p2
    rv_rej = client.post(f'/api/pending/{p2.id}/reject')
    assert rv_rej.status_code == 200
    data_rej = rv_rej.get_json()
    assert data_rej['status'] == 'ok'
    assert data_rej['remaining'] == 1  # осталась одна заявка

    # clear все оставшиеся
    rv_clear = client.post('/api/pending/clear')
    assert rv_clear.status_code == 200
    data_clear = rv_clear.get_json()
    assert data_clear['status'] == 'ok'
