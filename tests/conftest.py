"""Shared pytest fixtures. Uses an isolated SQLite database per test session."""
from __future__ import annotations

import os
import tempfile

import pytest

# Configure the environment BEFORE importing the app so settings pick it up.
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".sqlite3")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["EMAIL_BACKEND"] = "console"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def register(client: TestClient, login="jan", email=None, password="haslo123"):
    email = email or f"{login}@example.pl"
    return client.post(
        "/signup",
        data={
            "login": login,
            "email": email,
            "password": password,
            "repeat_password": password,
        },
        follow_redirects=False,
    )
