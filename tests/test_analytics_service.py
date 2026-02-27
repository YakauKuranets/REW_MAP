from datetime import datetime, timedelta

from app.extensions import db
from app.models import Address, PendingMarker, PendingHistory
from app.services.analytics_service import build_summary


def test_build_summary_empty(db_session):
    """При отсутствии данных сводка должна содержать нули и пустые словари."""
    summary = build_summary()
    assert summary["total"] == 0
    assert summary["by_category"] == {}
    assert summary["by_status"] == {}
    assert summary["pending"] == 0
    assert summary["approved"] == 0
    assert summary["rejected"] == 0
    assert summary["added_last_7d"] == 0


def test_build_summary_with_data(db_session):
    """Проверяем корректность подсчётов по адресам и заявкам."""
    now = datetime.utcnow()
    old = now - timedelta(days=30)

    a1 = Address(name="A1", lat=1.0, lon=1.0, category="cat1", status="open", created_at=now)
    a2 = Address(name="A2", lat=2.0, lon=2.0, category="cat1", status="closed", created_at=old)
    a3 = Address(name="A3", lat=3.0, lon=3.0, category="cat2", status="open", created_at=now)
    db.session.add_all([a1, a2, a3])

    p1 = PendingMarker(name="P1", lat=1.0, lon=1.0)
    p2 = PendingMarker(name="P2", lat=2.0, lon=2.0)
    db.session.add_all([p1, p2])

    h1 = PendingHistory(pending_id=1, status="approved")
    h2 = PendingHistory(pending_id=2, status="rejected")
    db.session.add_all([h1, h2])

    db.session.commit()

    summary = build_summary()

    assert summary["total"] == 3
    assert summary["by_category"].get("cat1") == 2
    assert summary["by_category"].get("cat2") == 1

    assert summary["by_status"].get("open") == 2
    assert summary["by_status"].get("closed") == 1

    assert summary["pending"] == 2
    assert summary["approved"] == 1
    assert summary["rejected"] == 1
    assert summary["added_last_7d"] >= 2
