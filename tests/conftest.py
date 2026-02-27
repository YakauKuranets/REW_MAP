import os
import pytest

from app import create_app
from app.config import TestingConfig

@pytest.fixture()
def app(tmp_path, monkeypatch):
    # Изолируем БД и офлайн-файлы в tmp
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URI", f"sqlite:///{db_path}")

    a = create_app(TestingConfig)

    # Изоляция offline путей
    a.config["OFFLINE_GEOCODE_FILE"] = str(tmp_path / "geocode.json")
    a.config["TILES_SETS_DIR"] = str(tmp_path / "tiles_sets")
    a.config["ACTIVE_TILES_FILE"] = str(tmp_path / "tiles_active_set.txt")
    os.makedirs(a.config["TILES_SETS_DIR"], exist_ok=True)

    # Подготовим файл геокода для delete тестов
    with open(a.config["OFFLINE_GEOCODE_FILE"], "w", encoding="utf-8") as f:
        f.write("{\"ok\": 1}")

    yield a

@pytest.fixture()
def client(app):
    return app.test_client()

def login_admin(client, username="admin", password="secret"):
    return client.post("/login", json={"username": username, "password": password})
