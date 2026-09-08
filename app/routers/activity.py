"""Audit trail of every moderation action."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from .. import schemas, services
from ..deps import get_current_user

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("")
def list_activity(
    user: dict = Depends(get_current_user),
    q: str = Query("", max_length=120),
    action: str = Query("", max_length=40),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
) -> dict:
    rows, page_info = services.list_activity(user["id"], q=q, action=action, page=page, per_page=per_page)
    return {"items": rows, "pagination": page_info}


@router.delete("")
def clear_activity(user: dict = Depends(get_current_user)) -> dict:
    removed = services.clear_activity(user["id"])
    return {"removed": removed}
