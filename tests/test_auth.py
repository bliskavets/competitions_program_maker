"""Tests for authentication and password reset."""
import logging

from tests.conftest import register


def test_signup_and_login(client):
    r = register(client, "ola", password="tajne123")
    assert r.status_code == 303
    assert r.headers["location"] == "/competitions"

    # wrong password
    r = client.post(
        "/login",
        data={"identifier": "ola", "password": "zle"},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "nie istnieje" in r.text

    # correct password
    r = client.post(
        "/login",
        data={"identifier": "ola", "password": "tajne123"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_signup_password_mismatch(client):
    r = client.post(
        "/signup",
        data={
            "login": "x",
            "email": "x@x.pl",
            "password": "aaaaaa",
            "repeat_password": "bbbbbb",
        },
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "identyczne" in r.text


def test_duplicate_user(client):
    register(client, "dup", email="dup@x.pl")
    r = register(client, "dup", email="dup@x.pl")
    assert "już istnieje" in r.text


def test_requires_login_redirect(client):
    r = client.get("/competitions", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_password_reset_flow(client, caplog):
    register(client, "reset", email="reset@x.pl", password="oldpass1")
    # request reset for unknown email
    r = client.post("/reset/request", data={"email": "nope@x.pl"})
    assert "Nie ma użytkownika" in r.text

    with caplog.at_level(logging.INFO, logger="sumo.email"):
        r = client.post("/reset/request", data={"email": "reset@x.pl"})
    assert "Wysłaliśmy" in r.text

    # pull the emitted code out of the console-backend log
    code = None
    for rec in caplog.records:
        if "Twój kod" in rec.getMessage():
            for token in rec.getMessage().split():
                if len(token) == 32:
                    code = token
    assert code, "reset code was not emitted"

    # wrong code
    r = client.post("/reset/verify", data={"email": "reset@x.pl", "code": "bad"})
    assert "nieprawidłowy" in r.text

    # correct code -> update password
    r = client.post("/reset/verify", data={"email": "reset@x.pl", "code": code})
    assert "Ustaw nowe hasło" in r.text
    r = client.post(
        "/reset/update",
        data={
            "email": "reset@x.pl",
            "code": code,
            "password": "newpass1",
            "repeat_password": "newpass1",
        },
    )
    assert "zmienione" in r.text

    # can log in with the new password
    r = client.post(
        "/login",
        data={"identifier": "reset@x.pl", "password": "newpass1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
