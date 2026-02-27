import io

from app.extensions import db
from app.models import Address


def _make_admin(client):
    with client.session_transaction() as sess:
        sess['role'] = 'admin'
        sess['username'] = 'admin'


def test_api_export_addresses(client, db_session):
    _make_admin(client)

    # создаём пару адресов
    a1 = Address(name='Exp1', lat=1.0, lon=2.0, category='cat', status='open', notes='one')
    a2 = Address(name='Exp2', lat=3.0, lon=4.0, category='cat', status='closed', notes='two')
    db.session.add_all([a1, a2])
    db.session.commit()

    resp = client.get('/api/export')
    assert resp.status_code == 200
    # старый маршрут отдает CSV
    assert 'text/csv' in resp.mimetype
    text = resp.data.decode('utf-8')
    assert 'Exp1' in text and 'Exp2' in text


def test_api_import_addresses(client, db_session):
    _make_admin(client)

    csv_data = 'id,name,lat,lon,notes,status,link,category\n,Imp,10.0,20.0,desc,open,,cat\n'
    data = {
        'file': (io.BytesIO(csv_data.encode('utf-8')), 'import.csv'),
    }

    resp = client.post('/api/import', data=data, content_type='multipart/form-data')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload.get('imported', 0) >= 1

    addr = Address.query.filter_by(name='Imp').first()
    assert addr is not None
    assert addr.lat == 10.0 and addr.lon == 20.0
