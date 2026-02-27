from app.extensions import db
from app.models import PendingMarker, PendingHistory, Address
from app.services.pending_service import (
    get_pending_count,
    list_pending_markers,
    approve_pending,
    reject_pending,
    clear_all_pending,
)


def _create_pending(name="P1", lat=1.0, lon=2.0):
    p = PendingMarker(name=name, lat=lat, lon=lon, notes="note", status="new", link="", category="cat1")
    db.session.add(p)
    db.session.commit()
    return p


def test_pending_count_and_list(db_session):
    assert get_pending_count() == 0
    p1 = _create_pending("P1")
    p2 = _create_pending("P2")

    assert get_pending_count() == 2
    items = list_pending_markers()
    ids = {item["id"] for item in items}
    assert ids == {p1.id, p2.id}


def test_approve_pending_creates_address_and_history(db_session, monkeypatch):
    p = _create_pending("To approve", 10.0, 20.0)

    published = []

    class BrokerStub:
        def publish_event(self, channel, payload):
            published.append((channel, payload))
            return True

    import app.services.pending_service as pending_service
    monkeypatch.setattr(pending_service, "get_broker", lambda: BrokerStub())

    result = approve_pending(p.id)
    assert result["status"] == "ok"
    addr_id = result["id"]

    addr = Address.query.get(addr_id)
    assert addr is not None
    assert addr.name == "To approve"
    assert addr.lat == 10.0 and addr.lon == 20.0

    hist = PendingHistory.query.filter_by(status="approved").first()
    assert hist is not None

    assert published == [
        (
            "map_updates",
            {
                "event": "MARKER_APPROVED",
                "marker_id": p.id,
                "new_object": addr.to_dict(),
            },
        ),
    ]

    # Заявка должна быть удалена
    assert PendingMarker.query.get(p.id) is None


def test_reject_pending_creates_history_and_removes(db_session, monkeypatch):
    p = _create_pending("To reject")

    published = []

    class BrokerStub:
        def publish_event(self, channel, payload):
            published.append((channel, payload))
            return True

    import app.services.pending_service as pending_service
    monkeypatch.setattr(pending_service, "get_broker", lambda: BrokerStub())

    result = reject_pending(p.id)
    assert result["status"] == "ok"
    assert result["remaining"] == 0

    hist = PendingHistory.query.filter_by(status="rejected").first()
    assert hist is not None
    assert PendingMarker.query.get(p.id) is None
    assert published == [
        (
            "map_updates",
            {
                "event": "MARKER_REJECTED",
                "marker_id": p.id,
            },
        ),
    ]


def test_clear_all_pending_marks_cancelled(db_session):
    p1 = _create_pending("P1")
    p2 = _create_pending("P2")

    result = clear_all_pending()
    assert result["status"] == "ok"
    assert PendingMarker.query.count() == 0

    statuses = {h.status for h in PendingHistory.query.all()}
    assert "cancelled" in statuses
