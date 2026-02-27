from app.extensions import db
from app.models import PendingMarker, Address
from app.services.requests_service import (
    get_requests_count,
    list_pending_for_menu,
    get_request_details,
    delete_request,
)


def _create_pending(name="P1", lat=1.0, lon=2.0, photo="photo.jpg"):
    p = PendingMarker(name=name, lat=lat, lon=lon, notes="note", status="new", link="", category="cat1", photo=photo)
    db.session.add(p)
    db.session.commit()
    return p


def test_requests_count_and_list(db_session):
    assert get_requests_count() == 0
    p1 = _create_pending("P1")
    p2 = _create_pending("P2")

    assert get_requests_count() == 2
    items = list_pending_for_menu()
    ids = {item["id"] for item in items}
    assert ids == {p1.id, p2.id}


def test_get_request_details(db_session):
    p = _create_pending("Detail", lat=5.0, lon=6.0)
    details = get_request_details(p.id)
    assert details is not None
    assert details["name"] == "Detail"
    assert details["lat"] == 5.0
    assert details["lon"] == 6.0


def test_delete_request_with_photo_attached_to_address(db_session):
    # Адрес с такими же координатами
    addr = Address(name="Addr", lat=10.0, lon=20.0, notes="", status="open", link="", category="cat1")
    db.session.add(addr)
    db.session.commit()

    p = _create_pending("Addr", lat=10.0, lon=20.0, photo="pic.png")
    result = delete_request(p.id)
    assert result["status"] == "ok"
    assert result["deleted"] is True
    # Заявка должна быть удалена
    assert PendingMarker.query.get(p.id) is None

    # Фото должно быть привязано к адресу
    db.session.refresh(addr)
    assert addr.photo == "pic.png"
