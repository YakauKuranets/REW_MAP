import json

from app.extensions import db
from app.models import Address


def test_api_analytics_summary(client, db_session):
    # создаём пару адресов
    a1 = Address(name='A1', lat=1.0, lon=2.0, category='cat1', status='open')
    a2 = Address(name='A2', lat=3.0, lon=4.0, category='cat2', status='closed')
    db.session.add_all([a1, a2])
    db.session.commit()

    rv = client.get('/api/analytics/summary')
    assert rv.status_code == 200
    data = rv.get_json()
    assert data['total'] >= 2
    assert 'by_category' in data
    assert 'by_status' in data


def test_api_geocode_offline_and_online(monkeypatch, client, app, tmp_path):
    # офлайн база
    offline_data = [
        {'name': 'Somewhere', 'display_name': 'Somewhere nice', 'lat': '1.23', 'lon': '4.56'},
    ]
    offline_file = tmp_path / 'geocode_api.json'
    offline_file.write_text(json.dumps(offline_data), encoding='utf-8')
    app.config['OFFLINE_GEOCODE_FILE'] = str(offline_file)

    # 1) офлайн-хит
    rv = client.get('/api/geocode', query_string={'q': 'some'})
    assert rv.status_code == 200
    data = rv.get_json()
    assert len(data) == 1
    assert data[0]['display_name'] == 'Somewhere nice'

    # 2) без офлайна → онлайн
    app.config['OFFLINE_GEOCODE_FILE'] = None

    class DummyResponse:
        def __init__(self, ok, payload):
            self.ok = ok
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, params=None, headers=None, timeout=10):
        return DummyResponse(True, [
            {'display_name': 'Online from API', 'lat': '9.99', 'lon': '8.88'}
        ])

    monkeypatch.setattr('app.services.geocode_service.requests.get', fake_get)

    rv2 = client.get('/api/geocode', query_string={'q': 'online'})
    assert rv2.status_code == 200
    data2 = rv2.get_json()
    assert len(data2) == 1
    assert data2[0]['display_name'] == 'Online from API'
