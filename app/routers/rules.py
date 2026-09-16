"""Cleanup-rule CRUD, dry runs and manual/automatic execution."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import database as db, schemas, services
from ..deps import get_current_user

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("")
def list_rules(
    user: dict = Depends(get_current_user),
    group_id: int | None = Query(None),
    enabled_only: bool = Query(False),
) -> dict:
    return {"items": services.list_rules(user["id"], group_id=group_id, enabled_only=enabled_only)}


@router.post("", response_model=schemas.RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(payload: schemas.RuleIn, user: dict = Depends(get_current_user)) -> dict:
    data = payload.model_dump()
    if data.get("group_id") and not services.get_group(user["id"], data["group_id"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That group does not belong to this workspace")
    return services.create_rule(user["id"], data, actor=user["name"])


@router.post("/dry-run", response_model=schemas.BulkResult)
def dry_run(payload: schemas.RuleIn, user: dict = Depends(get_current_user)) -> dict:
    """Preview a rule that hasn't been saved yet."""
    rule = {"id": None, **payload.model_dump()}
    if rule.get("group_id") and not services.get_group(user["id"], rule["group_id"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That group does not belong to this workspace")
    matched, ids = services.run_rule(user["id"], rule, dry_run=True, actor=user["name"])
    return {"action": rule["action"], "matched": matched, "processed": 0,
            "ids": ids[:50], "dry_run": True, "job_id": None}


@router.post("/run-all")
def run_all(user: dict = Depends(get_current_user)) -> dict:
    totals = services.run_all_rules(user["id"], actor=user["name"])
    return {**totals, "action": "run_all", "ran_at": db.utcnow()}


@router.get("/{rule_id}", response_model=schemas.RuleOut)
def get_rule(rule_id: int, user: dict = Depends(get_current_user)) -> dict:
    rule = services.get_rule(user["id"], rule_id)
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    return rule


@router.patch("/{rule_id}", response_model=schemas.RuleOut)
def update_rule(
    rule_id: int, payload: schemas.RuleIn, user: dict = Depends(get_current_user)
) -> dict:
    rule = services.update_rule(
        user["id"], rule_id, payload.model_dump(exclude_unset=True), actor=user["name"]
    )
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, user: dict = Depends(get_current_user)) -> None:
    rule = services.get_rule(user["id"], rule_id)
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    services.delete_rule(user["id"], rule_id)
    services.log_activity(
        user["id"], user["name"], "rule.deleted", target_type="rule", target_id=rule_id,
        target_label=rule["name"], detail="Rule removed",
    )


@router.post("/{rule_id}/toggle", response_model=schemas.RuleOut)
def toggle_rule(rule_id: int, user: dict = Depends(get_current_user)) -> dict:
    rule = services.get_rule(user["id"], rule_id)
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    return services.toggle_rule(user["id"], rule_id, not rule["enabled"], actor=user["name"])


@router.post("/{rule_id}/run", response_model=schemas.BulkResult)
def run_rule(
    rule_id: int, payload: schemas.RuleRunIn, user: dict = Depends(get_current_user)
) -> dict:
    rule = services.get_rule(user["id"], rule_id)
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    matched, ids = services.run_rule(
        user["id"], rule, dry_run=payload.dry_run, actor=user["name"]
    )
    return {
        "action": rule["action"], "matched": matched,
        "processed": 0 if payload.dry_run else matched,
        "ids": ids[:50], "dry_run": payload.dry_run, "job_id": None,
    }


@router.get("/{rule_id}/preview")
def preview_rule(rule_id: int, user: dict = Depends(get_current_user)) -> dict:
    rule = services.get_rule(user["id"], rule_id)
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    posts = services.posts_matching_rule(user["id"], rule)[:25]
    return {"rule": rule, "matched": len(posts), "items": posts}
