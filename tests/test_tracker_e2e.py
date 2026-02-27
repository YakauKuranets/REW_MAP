import os
import pytest
from app import create_app
from app.extensions import db

@pytest.fixture()
def app():
    os.environ["DATABASE_URI"] = "sqlite:///:memory:"
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
    yield app

@pytest.fixture()
def client(app):
    return app.test_client()

def _login_admin(client):
    with client.session_transaction() as sess:
        sess["role"] = "admin"
        sess["username"] = "test-admin"

def test_pair_start_points_stop_flow(client):
    _login_admin(client)
    r = client.post("/api/tracker/admin/pair-code", json={"label":"test"})
    assert r.status_code == 200
    code = r.get_json()["code"]

    r = client.post("/api/tracker/pair", json={"code": code, "user_id":"u1"})
    assert r.status_code == 200
    token = r.get_json()["device_token"]

    r = client.post("/api/tracker/start", headers={"X-DEVICE-TOKEN": token}, json={})
    assert r.status_code == 200
    session_id = r.get_json()["session_id"]

    pts = [{"ts":"2025-12-24T00:00:01Z","lat":53.9,"lon":27.56,"accuracy_m":10}]
    r = client.post("/api/tracker/points", headers={"X-DEVICE-TOKEN": token}, json={"session_id": session_id, "points": pts})
    assert r.status_code == 200
    body = r.get_json()
    assert "accepted" in body and "dedup" in body and "rejected" in body

    r = client.post("/api/tracker/stop", headers={"X-DEVICE-TOKEN": token}, json={"session_id": session_id})
    assert r.status_code == 200

def test_metrics_requires_admin(client):
    r = client.get("/api/tracker/admin/metrics")
    assert r.status_code in (401,403)
