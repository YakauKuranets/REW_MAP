from tests.conftest import login_admin

def test_chat_conversations_requires_admin(client, app):
    r = client.get("/api/chat/conversations")
    assert r.status_code == 403

    login_admin(client)
    r2 = client.get("/api/chat/conversations")
    assert r2.status_code == 200

def test_bot_api_key_enforced_for_non_admin(client, app):
    # включим BOT_API_KEY
    app.config["BOT_API_KEY"] = "k1"
    user_id = "12345"
    # без ключа должно быть 403
    r = client.post(f"/api/chat/{user_id}", json={"text": "hi", "sender": "user"})
    assert r.status_code == 403

    # с ключом — должно пройти (201)
    r2 = client.post(
        f"/api/chat/{user_id}",
        json={"text": "hi", "sender": "user"},
        headers={"X-API-KEY": "k1"},
    )
    assert r2.status_code in (201, 200)
