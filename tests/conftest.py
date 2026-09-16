"""Test fixtures: every test runs against a throwaway SQLite database."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """A fresh application + database for each test."""
    monkeypatch.setenv("PGPC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PGPC_DB_PATH", str(tmp_path / "test.db"))

    # Imported after the env vars so config picks up the temp paths.
    for module in list(sys.modules):
        if module == "app" or module.startswith("app."):
            del sys.modules[module]

    from app import config, database as db

    config.DATA_DIR = tmp_path
    config.DB_PATH = tmp_path / "test.db"
    db.close_conn()
    db.init_db()

    from app.main import create_app

    application = create_app()
    yield application
    db.close_conn()


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def seeded_client(client):
    """Client + an authenticated demo workspace full of realistic data."""
    from app.seed import seed

    seed(fresh=False, verbose=False)
    session = client.post(
        "/api/auth/login", json={"email": "admin@demo.com", "password": "demo1234"}
    ).json()
    client.headers["Authorization"] = f"Bearer {session['token']}"
    client.user = session["user"]
    return client


@pytest.fixture()
def auth_client(client):
    """Client with a hand-made (empty) workspace."""
    session = client.post(
        "/api/auth/register",
        json={"email": "owner@example.com", "password": "supersecret1", "name": "Test Owner"},
    ).json()
    client.headers["Authorization"] = f"Bearer {session['token']}"
    client.user = session["user"]
    return client
