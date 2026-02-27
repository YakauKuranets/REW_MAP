from io import StringIO

import pytest

from app.extensions import db
from app.models import Address
from app.services.addresses_service import (
    filter_addresses,
    create_address_from_form,
    export_addresses_csv,
    import_addresses_from_csv,
)


def test_filter_addresses_basic(db_session):
    a1 = Address(name='Shop', lat=1.0, lon=2.0, category='store', status='open', notes='Продукты')
    a2 = Address(name='School', lat=3.0, lon=4.0, category='edu', status='closed', notes='Школа')
    a3 = Address(name='Big Shop', lat=5.0, lon=6.0, category='store', status='open', notes='Большой магазин')
    db.session.add_all([a1, a2, a3])
    db.session.commit()

    # фильтр по категории
    res = filter_addresses(category='store')
    names = {r['name'] for r in res}
    assert names == {'Shop', 'Big Shop'}

    # фильтр по статусу
    res2 = filter_addresses(status='closed')
    assert len(res2) == 1
    assert res2[0]['name'] == 'School'

    # поиск по подстроке
    res3 = filter_addresses(q='shop')
    names3 = {r['name'] for r in res3}
    assert names3 == {'Shop', 'Big Shop'}


def test_create_address_from_form_success_without_photo(app, db_session, tmp_path):
    # настройка папки для загрузки, хотя фото не будет
    app.config['UPLOAD_FOLDER'] = str(tmp_path)

    class DummyFiles:
        def get(self, name):
            return None

    form = {
        'name': 'Point',
        'lat': '10.0',
        'lon': '20.0',
        'notes': 'desc',
        'status': 'open',
        'link': 'http://example.com',
        'category': 'cat1',
    }

    with app.app_context():
        ok, payload = create_address_from_form(form, DummyFiles())
        assert ok is True
        assert 'id' in payload
        addr = Address.query.get(payload['id'])
        assert addr is not None
        assert addr.name == 'Point'
        assert addr.lat == 10.0 and addr.lon == 20.0


def test_create_address_from_form_validation_errors(app, db_session, tmp_path):
    app.config['UPLOAD_FOLDER'] = str(tmp_path)

    class DummyFiles:
        def get(self, name):
            return None

    # нет координат
    form_missing = {'name': 'NoCoords', 'lat': '', 'lon': ''}
    with app.app_context():
        ok, payload = create_address_from_form(form_missing, DummyFiles())
        assert ok is False
        assert 'error' in payload

    # координаты вне диапазона
    form_bad = {'name': 'BadCoords', 'lat': '999', 'lon': '999'}
    with app.app_context():
        ok2, payload2 = create_address_from_form(form_bad, DummyFiles())
        assert ok2 is False
        assert 'out of range' in payload2.get('error', '')


def test_export_and_import_addresses_roundtrip(app, db_session):
    a1 = Address(name='A1', lat=1.0, lon=2.0, category='cat', status='open', notes='one')
    a2 = Address(name='A2', lat=3.0, lon=4.0, category='cat', status='closed', notes='two')
    db.session.add_all([a1, a2])
    db.session.commit()

    with app.app_context():
        csv_data = export_addresses_csv()

    # очистим таблицу и импортируем обратно
    for addr in Address.query.all():
        db.session.delete(addr)
    db.session.commit()

    with app.app_context():
        stream = StringIO(csv_data)
        result = import_addresses_from_csv(stream)

    assert result['imported'] >= 2
    assert Address.query.count() >= 2
