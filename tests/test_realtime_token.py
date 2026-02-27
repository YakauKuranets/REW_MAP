from tests.conftest import login_admin

def test_realtime_token_requires_admin(client):
    r = client.get("/api/realtime/token")
    assert r.status_code == 403

    login_admin(client)
    r2 = client.get("/api/realtime/token")
    assert r2.status_code == 200
    data = r2.get_json()
    assert "token" in data
