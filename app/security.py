"""Password hashing and compact HMAC-signed bearer tokens.

Both are implemented on top of the standard library (``hashlib`` / ``hmac``)
so the practice project stays dependency-light while still never storing a
plain-text password and never trusting an unsigned identity claim.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from . import config

_PBKDF2_ROUNDS = 180_000


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def hash_password(password: str) -> str:
    """Return a self-describing ``pbkdf2$rounds$salt$hash`` string."""
    if not password:
        raise ValueError("password must not be empty")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return "pbkdf2${}${}${}".format(_PBKDF2_ROUNDS, _b64encode(salt), _b64encode(digest))


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt_b64, digest_b64 = stored.split("$")
        if scheme != "pbkdf2":
            return False
        expected = _b64decode(digest_b64)
        salt = _b64decode(salt_b64)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
    return hmac.compare_digest(actual, expected)


def create_token(user_id: int, role: str = "owner", ttl: int | None = None) -> tuple[str, int]:
    """Create a signed token; returns ``(token, expires_at_epoch)``."""
    ttl = ttl or config.TOKEN_TTL_SECONDS
    expires_at = int(time.time()) + ttl
    payload = {
        "sub": user_id,
        "role": role,
        "iss": config.TOKEN_ISSUER,
        "iat": int(time.time()),
        "exp": expires_at,
        "jti": _b64encode(os.urandom(6)),
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64encode(
        hmac.new(config.SECRET_KEY.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{body}.{signature}", expires_at


def decode_token(token: str) -> dict[str, Any] | None:
    """Validate signature + expiry and return the payload, or ``None``."""
    if not token or "." not in token:
        return None
    body, _, signature = token.partition(".")
    expected = _b64encode(
        hmac.new(config.SECRET_KEY.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        payload = json.loads(_b64decode(body))
    except (ValueError, TypeError):
        return None
    if payload.get("iss") != config.TOKEN_ISSUER:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


def initials(name: str) -> str:
    parts = [part for part in (name or "").strip().split() if part]
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()
