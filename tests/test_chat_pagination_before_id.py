import pytest
from app.models import ChatMessage, db

def _add(client, user_id, text, sender="user"):
    return client.post(f"/api/chat/{user_id}", json={"text": text, "sender": sender}, headers={"X-API-KEY": "bot"})


def test_chat_before_id_pagination(client, monkeypatch):
    # enable bot key for posting user messages
    monkeypatch.setenv("BOT_API_KEY", "bot")

    # create admin session
    r = client.post("/login", json={"username": "admin", "password": "secret"})
    assert r.status_code == 200

    # seed messages
    uid = "u100"
    # posts as bot/user
    client.set_cookie("localhost", "session", "")  # ensure no admin? not necessary
    # We'll insert directly to db for deterministic ids
    with client.application.app_context():
        for i in range(1, 11):
            db.session.add(ChatMessage(user_id=uid, sender="user", text=f"m{i}", is_read=False))
        db.session.commit()
        ids = [m.id for m in ChatMessage.query.filter_by(user_id=uid).order_by(ChatMessage.id.asc()).all()]
    assert len(ids) == 10

    # back to admin
    r = client.post("/login", json={"username": "admin", "password": "secret"})
    assert r.status_code == 200

    # initial: last 5 (tail)
    r = client.get(f"/api/chat/{uid}?limit=5&tail=1")
    assert r.status_code == 200
    msgs = r.get_json()
    assert [m["text"] for m in msgs] == ["m6","m7","m8","m9","m10"]
    oldest = msgs[0]["id"]

    # older page before oldest id should return m1..m5
    r = client.get(f"/api/chat/{uid}?before_id={oldest}&limit=10")
    assert r.status_code == 200
    older = r.get_json()
    assert [m["text"] for m in older] == ["m1","m2","m3","m4","m5"]
