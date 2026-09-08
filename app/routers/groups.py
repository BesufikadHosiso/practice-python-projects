"""Group CRUD (+ a simulated Facebook re-sync)."""
from __future__ import annotations

import random
import time

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import database as db, schemas, services
from ..deps import get_current_user

router = APIRouter(prefix="/api/groups", tags=["groups"])


@router.get("")
def list_groups(
    user: dict = Depends(get_current_user),
    q: str = Query("", max_length=120),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> dict:
    rows, page_info = services.list_groups(user["id"], q=q, page=page, per_page=per_page)
    return {"items": rows, "pagination": page_info}


@router.post("", response_model=schemas.GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(payload: schemas.GroupIn, user: dict = Depends(get_current_user)) -> dict:
    group = services.create_group(user["id"], payload.model_dump())
    services.log_activity(
        user["id"], user["name"], "group.connected", target_type="group",
        target_id=group["id"], target_label=group["name"],
        detail=f"Connected {group['name']} ({group['privacy']})",
    )
    return group


@router.get("/{group_id}", response_model=schemas.GroupOut)
def get_group(group_id: int, user: dict = Depends(get_current_user)) -> dict:
    group = services.get_group(user["id"], group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
    return group


@router.patch("/{group_id}", response_model=schemas.GroupOut)
def update_group(
    group_id: int, payload: schemas.GroupIn, user: dict = Depends(get_current_user)
) -> dict:
    group = services.update_group(user["id"], group_id, payload.model_dump(exclude_unset=True))
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
    services.log_activity(
        user["id"], user["name"], "group.updated", target_type="group", target_id=group_id,
        target_label=group["name"], detail="Group settings saved",
    )
    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: int, user: dict = Depends(get_current_user)) -> None:
    group = services.get_group(user["id"], group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
    services.delete_group(user["id"], group_id)
    services.log_activity(
        user["id"], user["name"], "group.disconnected", target_type="group", target_id=group_id,
        target_label=group["name"],
        detail=f"Disconnected {group['name']} and its {group['stats']['posts']} posts",
    )


@router.post("/{group_id}/sync")
def sync_group(group_id: int, user: dict = Depends(get_current_user)) -> dict:
    """Pretend to pull the latest posts down from Facebook.

    The Graph API needs a long-lived page token and app review, so this stands
    in for it: it fabricates a handful of fresh posts so the moderation queue
    has something new to work through.
    """
    group = services.get_group(user["id"], group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
    if not group["connected"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Group is disconnected — reconnect it first")

    from ..seed import make_random_post  # local import keeps seeding optional at runtime

    rng = random.Random()
    created = 0
    for _ in range(rng.randint(4, 9)):
        # `make_random_post` builds *and* persists the row, so there is nothing
        # left to insert here — doing both used to double every synced post.
        make_random_post(rng, user["id"], group)
        created += 1
    services.touch_group_sync(group_id)
    services.log_activity(
        user["id"], user["name"], "group.synced", target_type="group", target_id=group_id,
        target_label=group["name"], detail=f"Pulled {created} new post(s) from Facebook",
    )
    return {"created": created, "synced_at": db.utcnow(), "group": services.get_group(user["id"], group_id)}


@router.get("/{group_id}/health")
def group_health(group_id: int, user: dict = Depends(get_current_user)) -> dict:
    group = services.get_group(user["id"], group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
    by_type = db.query(
        """SELECT post_type, COUNT(*) AS n FROM posts
           WHERE owner_id = ? AND group_id = ? AND deleted_at IS NULL
           GROUP BY post_type ORDER BY n DESC""",
        (user["id"], group_id),
    )
    authors = db.query(
        """SELECT author_name, COUNT(*) AS n FROM posts
           WHERE owner_id = ? AND group_id = ? AND deleted_at IS NOT NULL
           GROUP BY author_name ORDER BY n DESC LIMIT 5""",
        (user["id"], group_id),
    )
    started = time.perf_counter()
    noise = db.scalar(
        """SELECT COUNT(*) FROM posts WHERE owner_id = ? AND group_id = ?
               AND deleted_at IS NULL AND (state IN ('pending','flagged') OR reports > 0)""",
        (user["id"], group_id),
    ) or 0
    return {
        "group": group,
        "by_type": [{"type": r["post_type"], "count": r["n"]} for r in by_type],
        "top_removed_authors": [{"name": r["author_name"], "count": r["n"]} for r in authors],
        "noise": noise,
        "score": max(5, 100 - round(noise / max(group["stats"]["posts"], 1) * 100)),
        "generated_in_ms": round((time.perf_counter() - started) * 1000, 2),
    }
