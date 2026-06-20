"""Password hashing and signed-cookie session helpers."""
from __future__ import annotations

import uuid

from itsdangerous import BadSignature, URLSafeTimedSerializer
from passlib.context import CryptContext

from app.config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_serializer = URLSafeTimedSerializer(settings.secret_key, salt="session")


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _pwd.verify(password, hashed)
    except ValueError:
        return False


def make_session_token(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session_token(token: str) -> int | None:
    try:
        data = _serializer.loads(token, max_age=settings.session_max_age)
    except (BadSignature, Exception):  # noqa: BLE001 - any decode failure = no session
        return None
    return data.get("uid")


def new_reset_code() -> str:
    return uuid.uuid4().hex
