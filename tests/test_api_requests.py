from app.extensions import db
from app.models import PendingMarker, Address


def _make_admin(client):
    with client.session_transaction() as sess:
        sess['role'] = 'admin'
        sess['username'] = 'admin'


def test_requests_count_and_list(client, db_session):
    _make_admin(client)

    # создаём пару pending-заявок
    p1 = PendingMarker(name='P1', lat=1.0, lon=2.0)
    p2 = PendingMarker(name='P2', lat=3.0, lon=4.0)
    db.session.add_all([p1, p2])
    db.session.commit()

    rv_count = client.get('/api/requests/count')
    assert rv_count.status_code == 200
    data_count = rv_count.get_json()
    assert data_count['count'] == 2

    rv_list = client.get('/api/requests/pending')
    assert rv_list.status_code == 200
    items = rv_list.get_json()
    ids = {item['id'] for item in items}
    assert ids == {p1.id, p2.id}


def test_requests_detail_and_delete(client, db_session):
    _make_admin(client)

    addr = Address(name='Addr', lat=10.0, lon=20.0, notes='', status='open', link='', category='cat1')
    db.session.add(addr)
    db.session.commit()

    p = PendingMarker(name='Addr', lat=10.0, lon=20.0, notes='note', status='new', link='', category='cat1', photo='pic.png')
    db.session.add(p)
    db.session.commit()

    # detail
    rv_detail = client.get(f'/api/requests/{p.id}')
    assert rv_detail.status_code == 200
    detail = rv_detail.get_json()
    assert detail['name'] == 'Addr'
    assert detail['photo'] == 'pic.png'

    # delete
    rv_del = client.delete(f'/api/requests/{p.id}')
    assert rv_del.status_code == 200
    data_del = rv_del.get_json()
    assert data_del['status'] == 'ok'
    assert data_del['deleted'] is True

    # заявка должна быть удалена
    assert PendingMarker.query.get(p.id) is None

    # фото должно быть привязано к адресу
    db.session.refresh(addr)
    assert addr.photo == 'pic.png'
