"""Register / login / profile endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from .. import database as db, schemas, security, services
from ..deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: dict) -> schemas.UserOut:
    return schemas.UserOut(
        id=user["id"], email=user["email"], name=user["name"],
        role=user["role"], avatar_seed=user["avatar_seed"], created_at=user["created_at"],
    )


@router.post("/register", response_model=schemas.SessionOut, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.RegisterIn) -> schemas.SessionOut:
    email = payload.email.lower()
    if db.query_one("SELECT id FROM users WHERE lower(email) = ?", (email,)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists")
    user_id = db.execute(
        """INSERT INTO users (email, name, password_hash, role, avatar_seed, created_at)
           VALUES (?, ?, ?, 'owner', ?, ?)""",
        (email, payload.name, security.hash_password(payload.password),
         security.initials(payload.name), db.utcnow()),
    )
    services.log_activity(
        user_id, payload.name, "auth.registered", target_type="user", target_id=user_id,
        target_label=payload.name, detail="Workspace created",
    )
    user = db.query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    token, expires_at = security.create_token(user_id, user["role"])
    return schemas.SessionOut(token=token, expires_at=expires_at, user=_user_out(user))


@router.post("/login", response_model=schemas.SessionOut)
def login(payload: schemas.LoginIn) -> schemas.SessionOut:
    user = db.query_one("SELECT * FROM users WHERE lower(email) = ?", (payload.email.lower(),))
    if not user or not security.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    token, expires_at = security.create_token(user["id"], user["role"])
    services.log_activity(
        user["id"], user["name"], "auth.login", target_type="user", target_id=user["id"],
        target_label=user["name"], detail="Signed in",
    )
    return schemas.SessionOut(token=token, expires_at=expires_at, user=_user_out(user))


@router.get("/me", response_model=schemas.UserOut)
def me(user: dict = Depends(get_current_user)) -> schemas.UserOut:
    return _user_out(user)


@router.patch("/me", response_model=schemas.UserOut)
def update_profile(
    payload: schemas.ProfileIn, user: dict = Depends(get_current_user)
) -> schemas.UserOut:
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        return _user_out(user)
    if "email" in updates:
        updates["email"] = updates["email"].lower()
        clash = db.query_one(
            "SELECT id FROM users WHERE lower(email) = ? AND id != ?", (updates["email"], user["id"])
        )
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT, "That email is already in use")
    if "name" in updates:
        updates["avatar_seed"] = security.initials(updates["name"])
    assignments = ", ".join(f"{key} = ?" for key in updates)
    db.execute(f"UPDATE users SET {assignments} WHERE id = ?", [*updates.values(), user["id"]])
    services.log_activity(
        user["id"], updates.get("name", user["name"]), "auth.profile_updated",
        target_type="user", target_id=user["id"], target_label=updates.get("name", user["name"]),
        detail=f"Updated {', '.join(sorted(updates))}",
    )
    return _user_out(db.query_one("SELECT * FROM users WHERE id = ?", (user["id"],)))


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: schemas.ChangePasswordIn, user: dict = Depends(get_current_user)
) -> None:
    # `get_current_user` deliberately strips the hash, so read it back here.
    stored = db.scalar("SELECT password_hash FROM users WHERE id = ?", (user["id"],))
    if not stored or not security.verify_password(payload.current_password, stored):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (security.hash_password(payload.new_password), user["id"]),
    )
    services.log_activity(
        user["id"], user["name"], "auth.password_changed", target_type="user",
        target_id=user["id"], target_label=user["name"], detail="Password updated",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: dict = Depends(get_current_user)) -> None:
    """Tokens are stateless, so the client drops it; we just record the event."""
    services.log_activity(
        user["id"], user["name"], "auth.logout", target_type="user", target_id=user["id"],
        target_label=user["name"], detail="Signed out",
    )
