"""Domain logic: persistence helpers, the cleanup rule engine and stats.

Routers stay thin (auth + validation) and everything that touches the database
or decides *what should be deleted* lives here, which also makes it the natural
place for the test-suite to point at.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

from . import database as db

URL_RE = re.compile(r"https?://([^\s/)\]]+)", re.IGNORECASE)
SPAM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("External links", r"https?://"),
    ("DM / inbox solicitation", r"\b(dm|inbox|pm)\s+me\b"),
    ("Crypto & trading scams", r"\b(crypto|bitcoin|forex|binance|usdt|nft)\b"),
    ("Get rich quick", r"\b(free|guaranteed|earn|profit|income)\b.{0,24}\b(daily|week|month|fast|now)\b"),
    ("Phone / WhatsApp harvesting", r"\b(whatsapp|wa\.me|call me|\+\d{9,})\b"),
    ("Engagement bait", r"\b(comment|share|tag)\b.{0,16}\b(to win|for a chance|below)\b"),
)


# --------------------------------------------------------------------- helpers
def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "group"


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _bool(value: Any) -> bool:
    return bool(value) if value is not None else False


# --------------------------------------------------------------------- authors
def author_map(owner_id: int, names: Iterable[str]) -> dict[str, int]:
    """Return ``{name: author_id}`` for the given owner, creating what's missing."""
    out: dict[str, int] = {}
    for name in {n.strip() for n in names if n and n.strip()}:
        row = db.query_one(
            "SELECT id FROM authors WHERE owner_id = ? AND lower(name) = lower(?)",
            (owner_id, name),
        )
        if row:
            out[name] = row["id"]
        else:
            out[name] = db.execute(
                """INSERT INTO authors (owner_id, name, handle, avatar_seed, joined_at,
                                       is_banned, risk_score, created_at)
                   VALUES (?, ?, ?, ?, ?, 0, 0, ?)""",
                (owner_id, name, f"@{slugify(name)}", db_initials(name), db.utcnow(), db.utcnow()),
            )
    return out


def db_initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


# --------------------------------------------------------------------- activity
def log_activity(
    owner_id: int,
    actor: str,
    action: str,
    *,
    target_type: str = "post",
    target_id: int | None = None,
    target_label: str = "",
    group_id: int | None = None,
    detail: str = "",
) -> int:
    return db.execute(
        """INSERT INTO activity (owner_id, actor, action, target_type, target_id,
                                 target_label, group_id, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (owner_id, actor, action, target_type, target_id, target_label, group_id, detail, db.utcnow()),
    )


# ---------------------------------------------------------------------- groups
def _group_row(row: dict[str, Any]) -> dict[str, Any]:
    group = {
        "id": row["id"],
        "name": row["name"],
        "handle": row["handle"],
        "description": row["description"],
        "url": row["url"],
        "category": row["category"],
        "privacy": row["privacy"],
        "members": row["members"],
        "daily_posts": row["daily_posts"],
        "moderation": row["moderation"],
        "connected": _bool(row["connected"]),
        "last_synced_at": row["last_synced_at"],
        "created_at": row["created_at"],
        "stats": {
            "posts": row.get("total_posts", 0) or 0,
            "published": row.get("published", 0) or 0,
            "pending": row.get("pending", 0) or 0,
            "flagged": row.get("flagged", 0) or 0,
            "trashed": row.get("trashed", 0) or 0,
        },
    }
    return group


GROUP_SELECT = """
    SELECT g.*,
           (SELECT COUNT(*) FROM posts p WHERE p.group_id = g.id AND p.deleted_at IS NULL) AS total_posts,
           (SELECT COUNT(*) FROM posts p WHERE p.group_id = g.id AND p.deleted_at IS NULL
               AND p.state = 'published') AS published,
           (SELECT COUNT(*) FROM posts p WHERE p.group_id = g.id AND p.deleted_at IS NULL
               AND p.state = 'pending')  AS pending,
           (SELECT COUNT(*) FROM posts p WHERE p.group_id = g.id AND p.deleted_at IS NULL
               AND p.state = 'flagged')  AS flagged,
           (SELECT COUNT(*) FROM posts p WHERE p.group_id = g.id AND p.deleted_at IS NOT NULL) AS trashed
    FROM groups g
"""


def list_groups(owner_id: int, q: str = "", page: int = 1, per_page: int = 50) -> tuple[list[dict], dict]:
    clauses = ["g.owner_id = ?"]
    params: list[Any] = [owner_id]
    if q:
        clauses.append("(lower(g.name) LIKE ? OR lower(g.handle) LIKE ? OR lower(g.category) LIKE ?)")
        like = f"%{q.lower()}%"
        params += [like, like, like]
    where = " AND ".join(clauses)
    total = db.scalar(f"SELECT COUNT(*) FROM groups g WHERE {where}", params) or 0
    rows, page_info = db.paginate(
        f"{GROUP_SELECT} WHERE {where} ORDER BY lower(g.name) LIMIT {{limit}} OFFSET {{offset}}",
        params,
        page,
        per_page,
    )
    return [_group_row(r) for r in rows], {**page_info, "total": total}


def get_group(owner_id: int, group_id: int) -> dict[str, Any] | None:
    row = db.query_one(f"{GROUP_SELECT} WHERE g.owner_id = ? AND g.id = ?", (owner_id, group_id))
    return _group_row(row) if row else None


def create_group(owner_id: int, data: dict[str, Any]) -> dict[str, Any]:
    handle = data.get("handle") or slugify(data["name"])
    group_id = db.execute(
        """INSERT INTO groups (owner_id, name, handle, description, url, category, privacy,
                               members, daily_posts, moderation, connected, last_synced_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            owner_id, data["name"], handle, data.get("description", ""), data.get("url", ""),
            data.get("category", "Community"), data.get("privacy", "private"),
            int(data.get("members", 0) or 0), int(data.get("daily_posts", 0) or 0),
            data.get("moderation", "post_approval"), int(_bool(data.get("connected", True))),
            db.utcnow(), db.utcnow(),
        ),
    )
    return get_group(owner_id, group_id)  # type: ignore[return-value]


def update_group(owner_id: int, group_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    existing = db.query_one("SELECT * FROM groups WHERE id = ? AND owner_id = ?", (group_id, owner_id))
    if not existing:
        return None
    merged = {**existing, **{k: v for k, v in data.items() if v is not None}}
    if "name" in data and data["name"] and not data.get("handle"):
        merged["handle"] = slugify(data["name"])
    db.execute(
        """UPDATE groups SET name = ?, handle = ?, description = ?, url = ?, category = ?,
               privacy = ?, members = ?, daily_posts = ?, moderation = ?, connected = ?
           WHERE id = ? AND owner_id = ?""",
        (
            merged["name"], merged["handle"], merged["description"], merged["url"], merged["category"],
            merged["privacy"], int(merged["members"]), int(merged["daily_posts"]),
            merged["moderation"], int(_bool(merged["connected"])), group_id, owner_id,
        ),
    )
    return get_group(owner_id, group_id)


def touch_group_sync(group_id: int) -> None:
    db.execute("UPDATE groups SET last_synced_at = ? WHERE id = ?", (db.utcnow(), group_id))


def delete_group(owner_id: int, group_id: int) -> bool:
    existing = db.query_one("SELECT id FROM groups WHERE id = ? AND owner_id = ?", (group_id, owner_id))
    if not existing:
        return False
    db.execute("DELETE FROM groups WHERE id = ? AND owner_id = ?", (group_id, owner_id))
    return True


# ----------------------------------------------------------------------- posts
POST_SELECT = """
    SELECT p.*, g.name AS group_name, g.handle AS group_handle,
           COALESCE(a.avatar_seed, '??') AS avatar_seed
    FROM posts p
    LEFT JOIN groups g ON g.id = p.group_id
    LEFT JOIN authors a ON a.id = p.author_id
"""

SORTS = {
    "newest": "p.created_at DESC, p.id DESC",
    "oldest": "p.created_at ASC, p.id ASC",
    "engagement": "(p.likes + p.comments * 2 + p.shares * 3) DESC, p.id DESC",
    "reports": "p.reports DESC, (p.likes + p.comments) ASC, p.id DESC",
    "title": "lower(p.message) ASC",
}


def _post_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "group_id": row["group_id"],
        "group_name": row.get("group_name") or "",
        "group_handle": row.get("group_handle") or "",
        "author_id": row["author_id"],
        "author_name": row["author_name"],
        "avatar_seed": row.get("avatar_seed") or db_initials(row["author_name"]),
        "message": row["message"],
        "post_type": row["post_type"],
        "state": row["state"],
        "likes": row["likes"],
        "comments": row["comments"],
        "shares": row["shares"],
        "reports": row["reports"],
        "rule_id": row["rule_id"],
        "reason": row["reason"],
        "scheduled_for": row["scheduled_for"],
        "published_at": row["published_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "deleted_at": row["deleted_at"],
    }


def build_filters(
    owner_id: int,
    *,
    group_ids: Sequence[int] | None = None,
    states: Sequence[str] | None = None,
    post_types: Sequence[str] | None = None,
    q: str = "",
    message_q: str = "",
    contains_link: bool | None = None,
    author_id: int | None = None,
    older_than_days: int | None = None,
    min_reports: int | None = None,
    max_likes: int | None = None,
    include_trashed: bool = False,
    trashed_only: bool = False,
) -> tuple[str, list[Any]]:
    clauses = ["p.owner_id = ?"]
    params: list[Any] = [owner_id]

    if trashed_only:
        clauses.append("p.deleted_at IS NOT NULL")
    elif include_trashed:
        pass
    else:
        clauses.append("p.deleted_at IS NULL")

    if group_ids:
        placeholders = ",".join("?" for _ in group_ids)
        clauses.append(f"p.group_id IN ({placeholders})")
        params += list(group_ids)
    if states:
        placeholders = ",".join("?" for _ in states)
        clauses.append(f"p.state IN ({placeholders})")
        params += list(states)
    if post_types:
        placeholders = ",".join("?" for _ in post_types)
        clauses.append(f"p.post_type IN ({placeholders})")
        params += list(post_types)
    if q:
        clauses.append(
            "(lower(p.message) LIKE ? OR lower(p.author_name) LIKE ? OR lower(COALESCE(g.name,'')) LIKE ?)"
        )
        like = f"%{q.lower()}%"
        params += [like, like, like]
    if message_q:
        # Keyword *rules* target the post text only — unlike the free-text
        # search box, which also matches author and group names.
        clauses.append("lower(p.message) LIKE ?")
        params.append(f"%{message_q.lower()}%")
    if contains_link is True:
        clauses.append("lower(p.message) LIKE ?")
        params.append("%http%")
    elif contains_link is False:
        clauses.append("lower(p.message) NOT LIKE ?")
        params.append("%http%")
    if author_id is not None:
        clauses.append("p.author_id = ?")
        params.append(author_id)
    if older_than_days is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).replace(
            microsecond=0
        ).isoformat()
        clauses.append("COALESCE(p.published_at, p.created_at) < ?")
        params.append(cutoff)
    if min_reports is not None:
        clauses.append("p.reports >= ?")
        params.append(min_reports)
    if max_likes is not None:
        clauses.append("p.likes <= ?")
        params.append(max_likes)
    return " AND ".join(clauses), params


def list_posts(
    owner_id: int,
    *,
    page: int = 1,
    per_page: int = 25,
    sort: str = "newest",
    trashed_only: bool = False,
    **filters: Any,
) -> tuple[list[dict], dict]:
    where, params = build_filters(owner_id, trashed_only=trashed_only, **filters)
    total = db.scalar(f"SELECT COUNT(*) FROM posts p LEFT JOIN groups g ON g.id = p.group_id WHERE {where}", params) or 0
    order = SORTS.get(sort, SORTS["newest"])
    rows, page_info = db.paginate(
        f"{POST_SELECT} WHERE {where} ORDER BY {order} LIMIT {{limit}} OFFSET {{offset}}",
        params,
        page,
        per_page,
    )
    return [_post_row(r) for r in rows], {**page_info, "total": total}


def get_post(owner_id: int, post_id: int) -> dict[str, Any] | None:
    row = db.query_one(f"{POST_SELECT} WHERE p.id = ? AND p.owner_id = ?", (post_id, owner_id))
    return _post_row(row) if row else None


def create_post(owner_id: int, data: dict[str, Any], actor: str = "System") -> dict[str, Any]:
    now = db.utcnow()
    published = data.get("state") == "published"
    author_ids = author_map(owner_id, [data.get("author_name", "Unknown member")])
    author_id = author_ids.get(data.get("author_name", "").strip())
    post_id = db.execute(
        """INSERT INTO posts (owner_id, group_id, author_id, author_name, message, post_type,
                              state, likes, comments, shares, reports, reason, prior_state,
                              scheduled_for, published_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, ?, NULL, ?, ?, ?, ?)""",
        (
            owner_id, data["group_id"], author_id, data["author_name"], data.get("message", ""),
            data.get("post_type", "text"), data.get("state", "published"), data.get("reason", ""),
            data.get("scheduled_for"), now if published else None, now, now,
        ),
    )
    log_activity(
        owner_id, actor, "post.created", target_id=post_id,
        target_label=data["message"][:60] or "New post", group_id=data["group_id"],
        detail=f"Added a {data.get('post_type', 'text')} post",
    )
    return get_post(owner_id, post_id)  # type: ignore[return-value]


def update_post(
    owner_id: int, post_id: int, data: dict[str, Any], actor: str = "System"
) -> dict[str, Any] | None:
    existing = db.query_one("SELECT * FROM posts WHERE id = ? AND owner_id = ?", (post_id, owner_id))
    if not existing:
        return None
    merged = {**existing, **{k: v for k, v in data.items() if v is not None}}
    if "author_name" in data and data["author_name"]:
        merged["author_id"] = author_map(owner_id, [data["author_name"]]).get(data["author_name"].strip())
    if data.get("state") == "published" and not merged["published_at"]:
        merged["published_at"] = db.utcnow()
    db.execute(
        """UPDATE posts SET group_id = ?, author_id = ?, author_name = ?, message = ?,
               post_type = ?, state = ?, reason = ?, scheduled_for = ?, published_at = ?, updated_at = ?
           WHERE id = ? AND owner_id = ?""",
        (
            merged["group_id"], merged["author_id"], merged["author_name"], merged["message"],
            merged["post_type"], merged["state"], merged["reason"], merged["scheduled_for"],
            merged["published_at"], db.utcnow(), post_id, owner_id,
        ),
    )
    log_activity(
        owner_id, actor, "post.updated", target_id=post_id,
        target_label=merged["message"][:60], group_id=merged["group_id"],
        detail=f"Edited {', '.join(sorted(data))}",
    )
    return get_post(owner_id, post_id)


# ------------------------------------------------------- state transitions
_TRANSITIONS: dict[str, str] = {
    "delete": "post.deleted",
    "restore": "post.restored",
    "purge": "post.purged",
    "approve": "post.approved",
    "decline": "post.declined",
    "flag": "post.flagged",
    "unflag": "post.unflagged",
    "archive": "post.archived",
    "schedule": "post.scheduled",
}


def apply_action(
    owner_id: int,
    posts: Sequence[dict[str, Any]],
    action: str,
    *,
    reason: str = "",
    scheduled_for: str | None = None,
    rule_id: int | None = None,
    actor: str = "System",
    log: bool = True,
) -> int:
    """Mutate already-fetched post rows. Returns how many rows changed.

    ``delete`` / ``decline`` / ``archive`` are soft deletes: the row keeps its
    history (``prior_state``) so the trash view can restore it exactly as it
    was.  ``purge`` is the only destructive path.
    """
    now = db.utcnow()
    changed = 0
    label = _TRANSITIONS.get(action, f"post.{action}")
    soft_delete_reasons = {
        "delete": "Moved to trash",
        "decline": "Declined by moderator",
        "archive": "Archived by cleanup rule",
    }

    for post in posts:
        if action == "purge":
            db.execute("DELETE FROM posts WHERE id = ? AND owner_id = ?", (post["id"], owner_id))
            changed += 1
            continue

        if action in soft_delete_reasons:
            if post["deleted_at"]:
                continue
            db.execute(
                """UPDATE posts SET deleted_at = ?, prior_state = ?, reason = ?,
                       rule_id = COALESCE(?, rule_id), updated_at = ?
                   WHERE id = ? AND owner_id = ?""",
                (now, post["state"], reason or soft_delete_reasons[action], rule_id, now,
                 post["id"], owner_id),
            )
            changed += 1
            continue

        if action == "restore":
            if not post["deleted_at"]:
                continue
            db.execute(
                """UPDATE posts SET deleted_at = NULL, state = COALESCE(prior_state, 'published'),
                       prior_state = NULL, reason = '', updated_at = ?
                   WHERE id = ? AND owner_id = ?""",
                (now, post["id"], owner_id),
            )
            changed += 1
            continue

        if action == "approve" or action == "unflag":
            new_state, new_reason, published_at = "published", "", (post["published_at"] or now)
        elif action == "flag":
            new_state, new_reason = "flagged", (reason or "Flagged for review")
            published_at = post["published_at"]
        elif action == "schedule":
            new_state, new_reason, published_at = "scheduled", (reason or post["reason"]), None
        else:
            continue

        db.execute(
            """UPDATE posts SET state = ?, reason = ?, published_at = ?,
                   scheduled_for = ?, rule_id = COALESCE(?, rule_id), updated_at = ?
               WHERE id = ? AND owner_id = ?""",
            (
                new_state, new_reason, published_at,
                scheduled_for if action == "schedule" else post["scheduled_for"],
                rule_id, now, post["id"], owner_id,
            ),
        )
        changed += 1

    if changed and log:
        log_activity(
            owner_id, actor, label,
            target_type="post",
            target_id=posts[0]["id"] if len(posts) == 1 else None,
            target_label=(posts[0]["message"][:60] if len(posts) == 1 else f"{changed} posts"),
            group_id=posts[0]["group_id"] if len(posts) == 1 else None,
            detail=reason or f"Applied '{action}' to {changed} post(s)",
        )
    return changed


def bulk_by_ids(
    owner_id: int,
    ids: Sequence[int],
    action: str,
    *,
    reason: str = "",
    scheduled_for: str | None = None,
    actor: str = "System",
) -> tuple[int, list[int], list[dict]]:
    placeholders = ",".join("?" for _ in ids)
    rows = db.query(
        f"{POST_SELECT} WHERE p.owner_id = ? AND p.id IN ({placeholders})",
        [owner_id, *ids],
    )
    posts = [_post_row(r) for r in rows]
    changed = apply_action(owner_id, posts, action, reason=reason, scheduled_for=scheduled_for, actor=actor)
    return changed, [p["id"] for p in posts], posts


def count_matching(owner_id: int, filters: dict[str, Any]) -> tuple[int, list[int]]:
    """Count (and sample the ids of) the posts a filter would match. Read-only."""
    where, params = build_filters(owner_id, **filters)
    rows = db.query(f"SELECT p.id FROM posts p LEFT JOIN groups g ON g.id = p.group_id WHERE {where} ORDER BY p.created_at DESC LIMIT 2000", params)
    ids = [row["id"] for row in rows]
    return len(ids), ids


def bulk_by_filter(
    owner_id: int,
    filters: dict[str, Any],
    action: str,
    *,
    reason: str = "",
    actor: str = "System",
    log: bool = True,
    rule_id: int | None = None,
) -> tuple[int, list[int]]:
    where, params = build_filters(owner_id, **filters)
    rows = db.query(f"{POST_SELECT} WHERE {where} ORDER BY p.created_at DESC LIMIT 2000", params)
    posts = [_post_row(r) for r in rows]
    changed = apply_action(
        owner_id, posts, action, reason=reason, rule_id=rule_id, actor=actor, log=log
    )
    return changed, [p["id"] for p in posts]


# ----------------------------------------------------------------------- rules
def _rule_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "group_id": row["group_id"],
        "group_name": row.get("group_name"),
        "condition_type": row["condition_type"],
        "condition_value": row["condition_value"],
        "threshold": row["threshold"],
        "action": row["action"],
        "severity": row["severity"],
        "enabled": _bool(row["enabled"]),
        "runs": row["runs"],
        "affected": row["affected"],
        "last_run_at": row["last_run_at"],
        "created_at": row["created_at"],
    }


RULE_SELECT = """
    SELECT r.*, g.name AS group_name FROM rules r
    LEFT JOIN groups g ON g.id = r.group_id
"""


def list_rules(owner_id: int, *, group_id: int | None = None, enabled_only: bool = False) -> list[dict]:
    clauses = ["r.owner_id = ?"]
    params: list[Any] = [owner_id]
    if group_id is not None:
        clauses.append("r.group_id = ?")
        params.append(group_id)
    if enabled_only:
        clauses.append("r.enabled = 1")
    rows = db.query(
        f"{RULE_SELECT} WHERE {' AND '.join(clauses)} ORDER BY r.id ASC", params
    )
    return [_rule_row(r) for r in rows]


def get_rule(owner_id: int, rule_id: int) -> dict[str, Any] | None:
    row = db.query_one(f"{RULE_SELECT} WHERE r.id = ? AND r.owner_id = ?", (rule_id, owner_id))
    return _rule_row(row) if row else None


def create_rule(owner_id: int, data: dict[str, Any], actor: str = "System") -> dict[str, Any]:
    rule_id = db.execute(
        """INSERT INTO rules (owner_id, group_id, name, description, condition_type,
                              condition_value, threshold, action, severity, enabled, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            owner_id, data.get("group_id"), data["name"], data.get("description", ""),
            data.get("condition_type", "keyword"), data.get("condition_value", ""),
            int(data.get("threshold", 0) or 0), data.get("action", "delete"),
            data.get("severity", "medium"), int(_bool(data.get("enabled", True))), db.utcnow(),
        ),
    )
    log_activity(owner_id, actor, "rule.created", target_type="rule", target_id=rule_id,
                 target_label=data["name"], detail=f"Trigger: {data.get('condition_type')}")
    return get_rule(owner_id, rule_id)  # type: ignore[return-value]


def update_rule(owner_id: int, rule_id: int, data: dict[str, Any], actor: str = "System") -> dict | None:
    existing = db.query_one("SELECT * FROM rules WHERE id = ? AND owner_id = ?", (rule_id, owner_id))
    if not existing:
        return None
    merged = {**existing, **{k: v for k, v in data.items() if v is not None}}
    db.execute(
        """UPDATE rules SET group_id = ?, name = ?, description = ?, condition_type = ?,
               condition_value = ?, threshold = ?, action = ?, severity = ?, enabled = ?
           WHERE id = ? AND owner_id = ?""",
        (
            merged["group_id"], merged["name"], merged["description"], merged["condition_type"],
            merged["condition_value"], int(merged["threshold"]), merged["action"],
            merged["severity"], int(_bool(merged["enabled"])), rule_id, owner_id,
        ),
    )
    log_activity(owner_id, actor, "rule.updated", target_type="rule", target_id=rule_id,
                 target_label=merged["name"], detail="Rule settings changed")
    return get_rule(owner_id, rule_id)


def toggle_rule(owner_id: int, rule_id: int, enabled: bool, actor: str = "System") -> dict | None:
    rule = get_rule(owner_id, rule_id)
    if not rule:
        return None
    db.execute("UPDATE rules SET enabled = ? WHERE id = ? AND owner_id = ?",
               (int(enabled), rule_id, owner_id))
    log_activity(owner_id, actor, "rule.toggled", target_type="rule", target_id=rule_id,
                 target_label=rule["name"], detail="Enabled" if enabled else "Paused")
    return get_rule(owner_id, rule_id)


def delete_rule(owner_id: int, rule_id: int) -> bool:
    rule = get_rule(owner_id, rule_id)
    if not rule:
        return False
    db.execute("DELETE FROM rules WHERE id = ? AND owner_id = ?", (rule_id, owner_id))
    return True


def rule_filter(rule: dict[str, Any]) -> dict[str, Any]:
    """Translate a rule into the shared filter vocabulary (where possible)."""
    filters: dict[str, Any] = {"include_trashed": False}
    if rule.get("group_id"):
        filters["group_ids"] = [rule["group_id"]]
    kind = rule["condition_type"]
    value = (rule.get("condition_value") or "").strip()
    threshold = int(rule.get("threshold") or 0)

    if kind == "keyword":
        filters["message_q"] = value.split(",")[0].strip()
    elif kind == "domain":
        filters["contains_link"] = True
        filters["message_q"] = value.split(",")[0].strip()
    elif kind == "age_days":
        filters["older_than_days"] = threshold or 30
    elif kind == "low_engagement":
        filters["max_likes"] = threshold if threshold else 0
    elif kind == "reported":
        filters["min_reports"] = threshold or 1
    return filters


def posts_matching_rule(owner_id: int, rule: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the live posts a rule would act on (also powers the dry-run UI)."""
    kind = rule["condition_type"]
    filters = rule_filter(rule)

    if kind in {"repeat_poster", "duplicate", "banned_author"}:
        # These need a sub-query that the flat filter builder can't express.
        if kind == "repeat_poster":
            threshold = max(1, int(rule.get("threshold") or 3))
            group_clause = "AND group_id = ?" if rule.get("group_id") else ""
            params: list[Any] = [owner_id, threshold] + ([rule["group_id"]] if rule.get("group_id") else [])
            heavy = db.query(
                f"""SELECT author_id FROM posts WHERE owner_id = ? AND deleted_at IS NULL
                       AND author_id IS NOT NULL {group_clause}
                    GROUP BY author_id HAVING COUNT(*) >= ?""",
                params,
            )
            filters["author_id"] = None
            author_ids = [r["author_id"] for r in heavy]
            if not author_ids:
                return []
            placeholders = ",".join("?" for _ in author_ids)
            where, params2 = build_filters(owner_id, **{k: v for k, v in filters.items() if k != "author_id"})
            rows = db.query(
                f"{POST_SELECT} WHERE {where} AND p.author_id IN ({placeholders})", params2 + author_ids
            )
            return [_post_row(r) for r in rows]
        if kind == "duplicate":
            where, params = build_filters(owner_id, **filters)
            rows = db.query(f"{POST_SELECT} WHERE {where}", params)
            posts = [_post_row(r) for r in rows]
            # Two members posting the same question is not spam; one member
            # reposting the identical message is. Key on author + text and
            # keep the earliest copy of each pair.
            seen: set[tuple[int, str]] = set()
            duplicates: list[dict[str, Any]] = []
            for post in sorted(posts, key=lambda p: p["created_at"]):
                text = re.sub(r"\s+", " ", post["message"].lower().strip())[:120]
                if not text:
                    continue
                key = (post["author_id"] or 0, text)
                if key in seen:
                    duplicates.append(post)
                else:
                    seen.add(key)
            return duplicates
        # banned_author
        where, params = build_filters(owner_id, **filters)
        rows = db.query(
            f"{POST_SELECT} JOIN authors ba ON ba.id = p.author_id "
            f"WHERE {where} AND ba.is_banned = 1",
            params,
        )
        return [_post_row(r) for r in rows]

    where, params = build_filters(owner_id, **filters)
    rows = db.query(f"{POST_SELECT} WHERE {where} ORDER BY p.created_at DESC", params)
    return [_post_row(r) for r in rows]


RULE_ACTION_MAP = {
    "delete": "delete",
    "flag": "flag",
    "approve": "approve",
    "decline": "decline",
    "archive": "delete",
}


def run_rule(
    owner_id: int,
    rule: dict[str, Any],
    *,
    dry_run: bool = False,
    actor: str = "System",
) -> tuple[int, list[int]]:
    posts = posts_matching_rule(owner_id, rule)
    if dry_run:
        return len(posts), [p["id"] for p in posts]
    action = RULE_ACTION_MAP.get(rule["action"], "delete")
    reason = f"{rule['name']}"
    changed = apply_action(owner_id, posts, action, reason=reason, rule_id=rule["id"], actor=actor)
    db.execute(
        "UPDATE rules SET runs = runs + 1, affected = affected + ?, last_run_at = ? WHERE id = ?",
        (changed, db.utcnow(), rule["id"]),
    )
    if changed:
        log_activity(
            owner_id, actor, "rule.ran", target_type="rule", target_id=rule["id"],
            target_label=rule["name"], group_id=rule.get("group_id"),
            detail=f"{changed} post(s) {action}ed by rule",
        )
    return changed, [p["id"] for p in posts]


def run_all_rules(owner_id: int, actor: str = "Automation") -> dict[str, int]:
    totals = {"rules": 0, "affected": 0}
    for rule in list_rules(owner_id, enabled_only=True):
        changed, _ = run_rule(owner_id, rule, actor=actor)
        totals["rules"] += 1
        totals["affected"] += changed
    return totals


# --------------------------------------------------------------------- authors
def list_authors(owner_id: int, *, q: str = "", group_id: int | None = None) -> list[dict]:
    clauses = ["a.owner_id = ?"]
    params: list[Any] = [owner_id]
    if q:
        clauses.append("(lower(a.name) LIKE ? OR lower(a.handle) LIKE ?)")
        like = f"%{q.lower()}%"
        params += [like, like]
    if group_id is not None:
        clauses.append("a.group_id = ?")
        params.append(group_id)
    rows = db.query(
        f"""SELECT a.*, g.name AS group_name,
                   (SELECT COUNT(*) FROM posts p WHERE p.author_id = a.id) AS posts,
                   (SELECT COUNT(*) FROM posts p WHERE p.author_id = a.id
                      AND p.deleted_at IS NOT NULL) AS removed
            FROM authors a LEFT JOIN groups g ON g.id = a.group_id
            WHERE {' AND '.join(clauses)}
            ORDER BY removed DESC, lower(a.name) LIMIT 200""",
        params,
    )
    return [
        {
            "id": r["id"], "name": r["name"], "handle": r["handle"], "avatar_seed": r["avatar_seed"],
            "group_id": r["group_id"], "group_name": r["group_name"], "joined_at": r["joined_at"],
            "is_banned": _bool(r["is_banned"]), "risk_score": r["risk_score"],
            "posts": r["posts"], "removed": r["removed"],
        }
        for r in rows
    ]


def get_author(owner_id: int, author_id: int) -> dict[str, Any] | None:
    for author in list_authors(owner_id):
        if author["id"] == author_id:
            return author
    return None


def create_author(owner_id: int, data: dict[str, Any], actor: str = "System") -> dict[str, Any]:
    author_id = db.execute(
        """INSERT INTO authors (owner_id, group_id, name, handle, avatar_seed, joined_at,
                                is_banned, risk_score, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            owner_id, data.get("group_id"), data["name"],
            data.get("handle") or f"@{slugify(data['name'])}", db_initials(data["name"]),
            db.utcnow(), int(_bool(data.get("is_banned"))), int(data.get("risk_score", 0) or 0),
            db.utcnow(),
        ),
    )
    log_activity(owner_id, actor, "author.added", target_type="author", target_id=author_id,
                 target_label=data["name"], group_id=data.get("group_id"),
                 detail="Added to the watch-list")
    return get_author(owner_id, author_id)  # type: ignore[return-value]


def update_author(owner_id: int, author_id: int, data: dict[str, Any], actor: str = "System") -> dict | None:
    existing = db.query_one("SELECT * FROM authors WHERE id = ? AND owner_id = ?", (author_id, owner_id))
    if not existing:
        return None
    merged = {**existing, **{k: v for k, v in data.items() if v is not None}}
    db.execute(
        """UPDATE authors SET group_id = ?, name = ?, handle = ?, is_banned = ?, risk_score = ?
           WHERE id = ? AND owner_id = ?""",
        (
            merged["group_id"], merged["name"], merged["handle"],
            int(_bool(merged["is_banned"])), int(merged["risk_score"]), author_id, owner_id,
        ),
    )
    log_activity(owner_id, actor, "author.updated", target_type="author", target_id=author_id,
                 target_label=merged["name"], group_id=merged["group_id"],
                 detail="Banned from all groups" if _bool(merged["is_banned"]) else "Watch-list updated")
    return get_author(owner_id, author_id)


def delete_author(owner_id: int, author_id: int) -> bool:
    existing = db.query_one("SELECT id FROM authors WHERE id = ? AND owner_id = ?", (author_id, owner_id))
    if not existing:
        return False
    db.execute("DELETE FROM authors WHERE id = ? AND owner_id = ?", (author_id, owner_id))
    return True


# ------------------------------------------------------------------- clean jobs
def create_job(owner_id: int, data: dict[str, Any]) -> dict[str, Any]:
    job_id = db.execute(
        """INSERT INTO clean_jobs (owner_id, name, group_ids, filters, action, dry_run, status,
                                   matched, processed, duration_ms, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            owner_id, data["name"], db.dump_json(data.get("group_ids", [])),
            db.dump_json(data.get("filters", {})), data.get("action", "delete"),
            int(bool(data.get("dry_run"))), data.get("status", "completed"),
            int(data.get("matched", 0)), int(data.get("processed", 0)),
            int(data.get("duration_ms", 0)), db.utcnow(),
        ),
    )
    row = db.query_one("SELECT * FROM clean_jobs WHERE id = ?", (job_id,))
    return _job_row(row)  # type: ignore[arg-type]


def _job_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"], "name": row["name"], "group_ids": db.load_json(row["group_ids"], []),
        "filters": db.load_json(row["filters"], {}), "action": row["action"],
        "dry_run": _bool(row["dry_run"]), "status": row["status"], "matched": row["matched"],
        "processed": row["processed"], "duration_ms": row["duration_ms"], "created_at": row["created_at"],
    }


def list_jobs(owner_id: int, limit: int = 50) -> list[dict]:
    rows = db.query(
        "SELECT * FROM clean_jobs WHERE owner_id = ? ORDER BY id DESC LIMIT ?", (owner_id, limit)
    )
    return [_job_row(r) for r in rows]


def delete_job(owner_id: int, job_id: int) -> bool:
    row = db.query_one("SELECT id FROM clean_jobs WHERE id = ? AND owner_id = ?", (job_id, owner_id))
    if not row:
        return False
    db.execute("DELETE FROM clean_jobs WHERE id = ? AND owner_id = ?", (job_id, owner_id))
    return True


# --------------------------------------------------------------------- activity
def list_activity(
    owner_id: int, *, q: str = "", action: str = "", page: int = 1, per_page: int = 30
) -> tuple[list[dict], dict]:
    clauses = ["ac.owner_id = ?"]
    params: list[Any] = [owner_id]
    if q:
        clauses.append("(lower(ac.target_label) LIKE ? OR lower(ac.detail) LIKE ? OR lower(ac.action) LIKE ?)")
        like = f"%{q.lower()}%"
        params += [like, like, like]
    if action:
        clauses.append("ac.action LIKE ?")
        params.append(f"{action}%")
    where = " AND ".join(clauses)
    total = db.scalar(f"SELECT COUNT(*) FROM activity ac WHERE {where}", params) or 0
    rows, page_info = db.paginate(
        f"""SELECT ac.*, g.name AS group_name FROM activity ac
            LEFT JOIN groups g ON g.id = ac.group_id
            WHERE {where} ORDER BY ac.id DESC LIMIT {{limit}} OFFSET {{offset}}""",
        params, page, per_page,
    )
    return [
        {
            "id": r["id"], "actor": r["actor"], "action": r["action"], "target_type": r["target_type"],
            "target_id": r["target_id"], "target_label": r["target_label"], "group_id": r["group_id"],
            "group_name": r["group_name"], "detail": r["detail"], "created_at": r["created_at"],
        }
        for r in rows
    ], {**page_info, "total": total}


def clear_activity(owner_id: int) -> int:
    count = db.scalar("SELECT COUNT(*) FROM activity WHERE owner_id = ?", (owner_id,)) or 0
    db.execute("DELETE FROM activity WHERE owner_id = ?", (owner_id,))
    return int(count)


# ------------------------------------------------------------------------ stats
def overview(owner_id: int) -> dict[str, Any]:
    counts = {
        row["state"]: row["n"]
        for row in db.query(
            "SELECT state, COUNT(*) AS n FROM posts WHERE owner_id = ? AND deleted_at IS NULL GROUP BY state",
            (owner_id,),
        )
    }
    live = sum(counts.values())
    trashed = db.scalar(
        "SELECT COUNT(*) FROM posts WHERE owner_id = ? AND deleted_at IS NOT NULL", (owner_id,)
    ) or 0
    purged = db.scalar(
        "SELECT COUNT(*) FROM clean_jobs WHERE owner_id = ? AND action = 'delete'", (owner_id,)
    ) or 0
    engagement = db.query_one(
        """SELECT COALESCE(SUM(likes),0) AS likes, COALESCE(SUM(comments),0) AS comments,
                  COALESCE(SUM(shares),0) AS shares, COALESCE(SUM(reports),0) AS reports
           FROM posts WHERE owner_id = ? AND deleted_at IS NULL""",
        (owner_id,),
    ) or {}
    groups = db.query_one(
        """SELECT COUNT(*) AS total,
                  COALESCE(SUM(connected),0) AS connected,
                  COALESCE(SUM(members),0) AS members
           FROM groups WHERE owner_id = ?""",
        (owner_id,),
    ) or {}
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    cleaned_today = db.scalar(
        "SELECT COUNT(*) FROM posts WHERE owner_id = ? AND deleted_at >= ?", (owner_id, today)
    ) or 0
    rule_affected = db.scalar(
        "SELECT COALESCE(SUM(affected),0) FROM rules WHERE owner_id = ?", (owner_id,)
    ) or 0

    top_groups = db.query(
        """SELECT g.id, g.name, g.handle,
                  COUNT(p.id) AS posts,
                  SUM(CASE WHEN p.state = 'pending' THEN 1 ELSE 0 END) AS pending,
                  SUM(CASE WHEN p.state = 'flagged' THEN 1 ELSE 0 END) AS flagged
           FROM groups g LEFT JOIN posts p ON p.group_id = g.id AND p.deleted_at IS NULL
           WHERE g.owner_id = ?
           GROUP BY g.id ORDER BY posts DESC LIMIT 5""",
        (owner_id,),
    )
    by_type = db.query(
        """SELECT post_type, COUNT(*) AS n FROM posts
           WHERE owner_id = ? AND deleted_at IS NULL GROUP BY post_type ORDER BY n DESC""",
        (owner_id,),
    )
    spam_rows = db.query(
        "SELECT message FROM posts WHERE owner_id = ? AND deleted_at IS NULL", (owner_id,)
    )
    patterns: list[dict[str, Any]] = []
    for label, pattern in SPAM_PATTERNS:
        regex = re.compile(pattern, re.IGNORECASE)
        hits = sum(1 for row in spam_rows if regex.search(row["message"] or ""))
        patterns.append({"label": label, "count": hits})
    patterns.sort(key=lambda item: item["count"], reverse=True)

    return {
        "posts": {
            "live": live,
            "published": counts.get("published", 0),
            "pending": counts.get("pending", 0),
            "flagged": counts.get("flagged", 0),
            "scheduled": counts.get("scheduled", 0),
            "trashed": trashed,
            "purged": purged,
            "cleaned_today": cleaned_today,
        },
        "groups": {
            "total": groups.get("total", 0),
            "connected": groups.get("connected", 0),
            "members": groups.get("members", 0),
        },
        "engagement": {
            "likes": engagement.get("likes", 0),
            "comments": engagement.get("comments", 0),
            "shares": engagement.get("shares", 0),
            "reports": engagement.get("reports", 0),
        },
        "cleanup": {
            "rules_enabled": db.scalar(
                "SELECT COUNT(*) FROM rules WHERE owner_id = ? AND enabled = 1", (owner_id,)
            ) or 0,
            "rules_total": db.scalar("SELECT COUNT(*) FROM rules WHERE owner_id = ?", (owner_id,)) or 0,
            "auto_removed": int(rule_affected),
            "jobs": db.scalar("SELECT COUNT(*) FROM clean_jobs WHERE owner_id = ?", (owner_id,)) or 0,
            "health": _health_score(live, counts.get("pending", 0), counts.get("flagged", 0), int(trashed)),
        },
        "top_groups": [
            {
                "id": r["id"], "name": r["name"], "handle": r["handle"], "posts": r["posts"],
                "pending": r["pending"] or 0, "flagged": r["flagged"] or 0,
            }
            for r in top_groups
        ],
        "by_type": [{"type": r["post_type"], "count": r["n"]} for r in by_type],
        "spam_patterns": patterns[:5],
    }


def _health_score(live: int, pending: int, flagged: int, trashed: int) -> int:
    if live <= 0:
        return 100
    noisy = pending + flagged
    score = 100 - round((noisy / max(live, 1)) * 100)
    bonus = 5 if trashed else 0
    return max(5, min(100, score + bonus))


def timeline(owner_id: int, days: int = 14) -> list[dict[str, Any]]:
    days = max(1, min(days, 90))
    start = datetime.now(timezone.utc) - timedelta(days=days - 1)
    buckets: dict[str, dict[str, int]] = {}
    for offset in range(days):
        key = (start + timedelta(days=offset)).date().isoformat()
        buckets[key] = {"date": key, "deleted": 0, "pending": 0, "flagged": 0}
    rows = db.query(
        f"""SELECT {db.date_expr("COALESCE(deleted_at, published_at, created_at)")} AS day,
                  SUM(CASE WHEN deleted_at IS NOT NULL THEN 1 ELSE 0 END) AS deleted,
                  SUM(CASE WHEN deleted_at IS NULL AND state = 'pending' THEN 1 ELSE 0 END) AS pending,
                  SUM(CASE WHEN deleted_at IS NULL AND state = 'flagged' THEN 1 ELSE 0 END) AS flagged
           FROM posts WHERE owner_id = ?
           GROUP BY day ORDER BY day""",
        (owner_id,),
    )
    for row in rows:
        bucket = buckets.get(row["day"])
        if bucket:
            bucket["deleted"] = row["deleted"] or 0
            bucket["pending"] = row["pending"] or 0
            bucket["flagged"] = row["flagged"] or 0
    return list(buckets.values())


def detect_spam_patterns(texts: Iterable[str]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for text in texts:
        for label, pattern in SPAM_PATTERNS:
            if re.search(pattern, text or "", re.IGNORECASE):
                counter[label] += 1
    return counter
