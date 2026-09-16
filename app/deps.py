"""FastAPI dependencies: bearer-token auth and the current user record."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import database as db, security

bearer = HTTPBearer(auto_error=False, description="Bearer token issued by /api/auth/login")

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _CREDENTIALS_ERROR
    payload = security.decode_token(credentials.credentials)
    if not payload:
        raise _CREDENTIALS_ERROR
    user = db.query_one("SELECT * FROM users WHERE id = ?", (payload["sub"],))
    if not user:
        raise _CREDENTIALS_ERROR
    user.pop("password_hash", None)
    return user


CurrentUser = Depends(get_current_user)
