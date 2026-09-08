"""Member / spam-author watch-list CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import schemas, services
from ..deps import get_current_user

router = APIRouter(prefix="/api/authors", tags=["authors"])


@router.get("")
def list_authors(
    user: dict = Depends(get_current_user),
    q: str = Query("", max_length=120),
    group_id: int | None = Query(None),
) -> dict:
    return {"items": services.list_authors(user["id"], q=q, group_id=group_id)}


@router.post("", response_model=schemas.AuthorOut, status_code=status.HTTP_201_CREATED)
def create_author(payload: schemas.AuthorIn, user: dict = Depends(get_current_user)) -> dict:
    return services.create_author(user["id"], payload.model_dump(), actor=user["name"])


@router.get("/{author_id}", response_model=schemas.AuthorOut)
def get_author(author_id: int, user: dict = Depends(get_current_user)) -> dict:
    author = services.get_author(user["id"], author_id)
    if not author:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return author


@router.patch("/{author_id}", response_model=schemas.AuthorOut)
def update_author(
    author_id: int, payload: schemas.AuthorIn, user: dict = Depends(get_current_user)
) -> dict:
    author = services.update_author(
        user["id"], author_id, payload.model_dump(exclude_unset=True), actor=user["name"]
    )
    if not author:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return author


@router.delete("/{author_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_author(author_id: int, user: dict = Depends(get_current_user)) -> None:
    author = services.get_author(user["id"], author_id)
    if not author:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    services.delete_author(user["id"], author_id)
    services.log_activity(
        user["id"], user["name"], "author.removed", target_type="author", target_id=author_id,
        target_label=author["name"], detail="Removed from the watch-list",
    )


@router.post("/{author_id}/ban")
def ban_author(author_id: int, user: dict = Depends(get_current_user)) -> dict:
    """Ban a member and sweep every one of their live posts into the trash.

    No ``response_model`` here on purpose: the payload is an author record plus
    a ``swept`` count, and a response model would silently strip the count.
    """
    author = services.get_author(user["id"], author_id)
    if not author:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    updated = services.update_author(
        user["id"], author_id, {"is_banned": not author["is_banned"]}, actor=user["name"]
    )
    swept = 0
    if updated and updated["is_banned"]:
        swept, _ = services.bulk_by_filter(
            user["id"], {"author_id": author_id}, "delete",
            reason=f"Author {author['name']} banned from all groups", actor=user["name"],
        )
    return {**updated, "swept": swept}


@router.post("/{author_id}/purge-posts")
def purge_author_posts(author_id: int, user: dict = Depends(get_current_user)) -> dict:
    author = services.get_author(user["id"], author_id)
    if not author:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    changed, ids = services.bulk_by_filter(
        user["id"], {"author_id": author_id, "include_trashed": True}, "purge",
        reason=f"All posts by {author['name']} permanently deleted", actor=user["name"],
    )
    return {"purged": changed, "ids": ids[:50], "author": author}
