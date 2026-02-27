from io import BytesIO

from app.services.general_service import export_addresses_root, import_addresses_root
from app.services import addresses_service
from app.models import Address
from app.extensions import db


class DummyFileStorage:
    def __init__(self, data: str):
        self.stream = BytesIO(data.encode('utf-8'))


def test_export_addresses_root_uses_addresses_service(monkeypatch, app, db_session):
    # подготовим один адрес
    addr = Address(name='A1', lat=1.0, lon=2.0, category='cat', status='open', notes='n')
    db.session.add(addr)
    db.session.commit()

    captured = {}

    def fake_export():
        captured['called'] = True
        return 'id,name\n1,A1\n'

    monkeypatch.setattr('app.services.general_service.export_addresses_csv', fake_export)

    with app.app_context():
        csv_data = export_addresses_root()

    assert captured.get('called') is True
    assert 'A1' in csv_data


def test_import_addresses_root_uses_addresses_service(monkeypatch, app, db_session):
    csv_data = 'id,name,lat,lon,notes,status,link,category\n,New,1.0,2.0,desc,open,,cat\n'
    file_storage = DummyFileStorage(csv_data)

    called = {}

    def fake_import(stream):
        # читаем всё, чтобы убедиться, что пришли именно наши данные
        content = stream.read()
        called['data'] = content
        return {'imported': 1}

    monkeypatch.setattr('app.services.general_service.import_addresses_from_csv', fake_import)

    with app.app_context():
        result = import_addresses_root(file_storage)

    assert result == {'imported': 1}
    assert b'New' in called.get('data', b'')
