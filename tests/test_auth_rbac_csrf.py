from tests.conftest import login_admin

def _csrf(client):
    with client.session_transaction() as s:
        return s.get("csrf_token")

def test_setrole_admin_forbidden(client):
    r = client.post("/setrole/admin")
    assert r.status_code in (401, 403)

def test_login_sets_admin_session(client):
    r = login_admin(client)
    assert r.status_code == 200
    me = client.get("/me")
    assert me.status_code == 200
    data = me.get_json()
    assert data["is_admin"] is True

def test_csrf_blocks_admin_mutations(client):
    login_admin(client)
    # без CSRF — должно блокироваться
    r = client.post("/api/offline/geocode:delete")
    assert r.status_code == 403

    token = _csrf(client)
    r2 = client.post("/api/offline/geocode:delete", headers={"X-CSRF-Token": token})
    assert r2.status_code != 403
