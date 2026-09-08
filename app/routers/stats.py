"""Dashboard metrics."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from .. import services
from ..deps import get_current_user

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/overview")
def overview(user: dict = Depends(get_current_user)) -> dict:
    return services.overview(user["id"])


@router.get("/timeline")
def timeline(user: dict = Depends(get_current_user), days: int = Query(14, ge=1, le=90)) -> dict:
    return {"days": days, "items": services.timeline(user["id"], days=days)}
