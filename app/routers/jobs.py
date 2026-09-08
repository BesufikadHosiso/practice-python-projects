"""Cleanup job history (every bulk sweep the workspace has run)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import schemas, services
from ..deps import get_current_user

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=dict)
def list_jobs(user: dict = Depends(get_current_user), limit: int = Query(50, ge=1, le=200)) -> dict:
    return {"items": services.list_jobs(user["id"], limit=limit)}


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, user: dict = Depends(get_current_user)) -> None:
    if not services.delete_job(user["id"], job_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")


@router.delete("")
def clear_jobs(user: dict = Depends(get_current_user)) -> dict:
    removed = 0
    for job in services.list_jobs(user["id"], limit=200):
        if services.delete_job(user["id"], job["id"]):
            removed += 1
    return {"removed": removed}
