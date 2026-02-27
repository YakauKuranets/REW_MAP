from tests.conftest import login_admin


def _csrf(client):
    with client.session_transaction() as s:
        return s.get("csrf_token")


def test_chat_delete_requires_admin(client):
    # без логина — должно быть запрещено
    r = client.delete("/api/chat/u1")
    assert r.status_code in (401, 403)

    r2 = client.delete("/api/chat/u1/dialog")
    assert r2.status_code in (401, 403)


def test_chat_delete_requires_csrf(client):
    login_admin(client)
    token = _csrf(client)

    # создадим сообщение (с CSRF)
    r = client.post("/api/chat/u1", json={"text": "hi", "sender": "admin"}, headers={"X-CSRF-Token": token})
    assert r.status_code in (200, 201)

    # без CSRF — должно блокироваться
    r2 = client.delete("/api/chat/u1")
    assert r2.status_code == 403

    # с CSRF — должно работать
    r3 = client.delete("/api/chat/u1", headers={"X-CSRF-Token": token})
    assert r3.status_code == 200
    body = r3.get_json() or {}
    assert "deleted" in body

    # удаление диалога тоже должно требовать CSRF
    r4 = client.delete("/api/chat/u1/dialog")
    assert r4.status_code == 403

    r5 = client.delete("/api/chat/u1/dialog", headers={"X-CSRF-Token": token})
    assert r5.status_code == 200
