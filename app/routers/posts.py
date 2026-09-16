"""Post CRUD plus the bulk / cleanup endpoints that drive the whole product.

Route order matters: every literal path (``/trash``, ``/bulk``, ...) is declared
before the ``/{post_id}`` routes so FastAPI doesn't try to parse ``bulk`` as an
integer id.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import database as db, schemas, services
from ..deps import get_current_user

router = APIRouter(prefix="/api/posts", tags=["posts"])


def _filters_from_query(
    group_id: int | None,
    state: str,
    post_type: str,
    q: str,
    contains_link: str,
    author_id: int | None,
    older_than_days: int | None,
    min_reports: int | None,
    max_likes: int | None,
) -> dict:
    def _split(value: str) -> list[str]:
        return [part.strip() for part in value.split(",") if part.strip()]

    return {
        "group_ids": [group_id] if group_id else [],
        "states": _split(state),
        "post_types": _split(post_type),
        "q": q,
        "contains_link": {"true": True, "false": False}.get(contains_link.lower()) if contains_link else None,
        "author_id": author_id,
        "older_than_days": older_than_days,
        "min_reports": min_reports,
        "max_likes": max_likes,
    }


# ------------------------------------------------------------- collection reads
@router.get("")
def list_posts(
    user: dict = Depends(get_current_user),
    group_id: int | None = Query(None),
    state: str = Query("", description="comma separated: published,pending,flagged,scheduled"),
    post_type: str = Query(""),
    q: str = Query("", max_length=160),
    contains_link: str = Query("", pattern="^(true|false)?$"),
    author_id: int | None = Query(None),
    older_than_days: int | None = Query(None, ge=0, le=3650),
    min_reports: int | None = Query(None, ge=0),
    max_likes: int | None = Query(None, ge=0),
    sort: str = Query("newest", pattern="^(newest|oldest|engagement|reports|title)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
) -> dict:
    filters = _filters_from_query(
        group_id, state, post_type, q, contains_link, author_id, older_than_days,
        min_reports, max_likes,
    )
    rows, page_info = services.list_posts(
        user["id"], page=page, per_page=per_page, sort=sort, **filters
    )
    return {"items": rows, "pagination": page_info}


@router.get("/trash")
def list_trash(
    user: dict = Depends(get_current_user),
    group_id: int | None = Query(None),
    q: str = Query("", max_length=160),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
) -> dict:
    rows, page_info = services.list_posts(
        user["id"], page=page, per_page=per_page, sort="newest", trashed_only=True,
        group_ids=[group_id] if group_id else [], q=q,
    )
    prior = {
        r["id"]: (r["prior_state"] or "published")
        for r in db.query(
            "SELECT id, prior_state FROM posts WHERE owner_id = ? AND deleted_at IS NOT NULL",
            (user["id"],),
        )
    }
    for row in rows:
        row["prior_state"] = prior.get(row["id"], "published")
    return {"items": rows, "pagination": page_info}


@router.post("", response_model=schemas.PostOut, status_code=status.HTTP_201_CREATED)
def create_post(payload: schemas.PostIn, user: dict = Depends(get_current_user)) -> dict:
    if not services.get_group(user["id"], payload.group_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That group does not belong to this workspace")
    return services.create_post(user["id"], payload.model_dump(), actor=user["name"])


# ------------------------------------------------------- bulk / cleanup actions
@router.post("/bulk", response_model=schemas.BulkResult)
def bulk_action(payload: schemas.BulkIn, user: dict = Depends(get_current_user)) -> dict:
    changed, ids, posts = services.bulk_by_ids(
        user["id"], payload.ids, payload.action,
        reason=payload.reason, scheduled_for=payload.scheduled_for, actor=user["name"],
    )
    if not posts:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "None of those posts exist in this workspace")
    if payload.action in {"delete", "purge"} and changed:
        services.create_job(user["id"], {
            "name": f"{payload.action.title()} selection",
            "group_ids": sorted({p["group_id"] for p in posts}),
            "filters": {"ids": payload.ids}, "action": payload.action,
            "matched": len(posts), "processed": changed,
        })
    return {
        "action": payload.action, "matched": len(posts), "processed": changed,
        "ids": ids, "dry_run": False, "job_id": None,
    }


@router.post("/bulk-filter", response_model=schemas.BulkResult)
def bulk_filter(payload: schemas.BulkFilterIn, user: dict = Depends(get_current_user)) -> dict:
    """Delete (or flag/approve) every post matching a filter set.

    ``dry_run`` returns the count that *would* be affected without touching
    anything — this powers the confirmation preview in the UI.
    """
    started = time.perf_counter()
    filters = payload.filters.model_dump()
    if payload.dry_run:
        matched, ids = services.count_matching(user["id"], filters)
        return {"action": payload.action, "matched": matched, "processed": 0,
                "ids": ids[:50], "dry_run": True, "job_id": None}

    reason = f"Bulk sweep: {payload.name}"
    changed, ids = services.bulk_by_filter(
        user["id"], filters, payload.action, reason=reason, actor=user["name"]
    )
    job = services.create_job(user["id"], {
        "name": payload.name, "group_ids": filters.get("group_ids", []), "filters": filters,
        "action": payload.action, "matched": len(ids), "processed": changed,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    })
    services.log_activity(
        user["id"], user["name"], "clean.job", target_type="job", target_id=job["id"],
        target_label=payload.name,
        detail=f"{changed} post(s) {payload.action}ed across "
               f"{len(filters.get('group_ids') or []) or 'all'} group(s)",
    )
    return {"action": payload.action, "matched": len(ids), "processed": changed,
            "ids": ids[:50], "dry_run": False, "job_id": job["id"]}


@router.post("/auto-clean")
def auto_clean(user: dict = Depends(get_current_user)) -> dict:
    totals = services.run_all_rules(user["id"], actor=user["name"])
    return {**totals, "ran_at": db.utcnow()}


@router.delete("/trash")
def empty_trash(
    user: dict = Depends(get_current_user),
    group_id: int | None = Query(None),
) -> dict:
    sql = "SELECT id FROM posts WHERE owner_id = ? AND deleted_at IS NOT NULL"
    params: list = [user["id"]]
    if group_id:
        sql += " AND group_id = ?"
        params.append(group_id)
    ids = [r["id"] for r in db.query(sql, params)]
    if ids:
        posts = [p for p in (services.get_post(user["id"], pid) for pid in ids) if p]
        services.apply_action(
            user["id"], posts, "purge", reason="Trash emptied", actor=user["name"], log=False
        )
        services.log_activity(
            user["id"], user["name"], "post.purged", target_type="post",
            target_label=f"{len(ids)} posts",
            detail=f"Permanently deleted {len(ids)} post(s) from the trash",
        )
    return {"purged": len(ids), "ids": ids[:50]}


# ---------------------------------------------------------------- single record
@router.get("/{post_id}", response_model=schemas.PostOut)
def get_post(post_id: int, user: dict = Depends(get_current_user)) -> dict:
    post = services.get_post(user["id"], post_id)
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return post


@router.patch("/{post_id}", response_model=schemas.PostOut)
def update_post(
    post_id: int, payload: schemas.PostPatch, user: dict = Depends(get_current_user)
) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    if "group_id" in changes and not services.get_group(user["id"], changes["group_id"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That group does not belong to this workspace")
    post = services.update_post(user["id"], post_id, changes, actor=user["name"])
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, user: dict = Depends(get_current_user)) -> None:
    post = services.get_post(user["id"], post_id)
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    services.apply_action(user["id"], [post], "delete", actor=user["name"])


@router.post("/{post_id}/restore", response_model=schemas.PostOut)
def restore_post(post_id: int, user: dict = Depends(get_current_user)) -> dict:
    post = services.get_post(user["id"], post_id)
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    services.apply_action(user["id"], [post], "restore", actor=user["name"])
    return services.get_post(user["id"], post_id)  # type: ignore[return-value]


@router.post("/{post_id}/purge", status_code=status.HTTP_204_NO_CONTENT)
def purge_post(post_id: int, user: dict = Depends(get_current_user)) -> None:
    post = services.get_post(user["id"], post_id)
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    services.apply_action(user["id"], [post], "purge", actor=user["name"])
