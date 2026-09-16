"""Pydantic request/response models."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

POST_STATES = ("published", "pending", "flagged", "scheduled")
POST_TYPES = ("text", "photo", "link", "video", "poll", "live", "event")
PRIVACIES = ("public", "private", "hidden")
MODERATION_MODES = ("post_approval", "keyword_filter", "open", "admin_only")
RULE_CONDITIONS = (
    "keyword",
    "domain",
    "age_days",
    "low_engagement",
    "reported",
    "repeat_poster",
    "banned_author",
    "duplicate",
)
RULE_ACTIONS = ("delete", "flag", "approve", "decline", "archive")
SEVERITIES = ("low", "medium", "high")
BULK_ACTIONS = ("delete", "restore", "purge", "approve", "decline", "flag", "unflag", "schedule")


class _Model(BaseModel):
    model_config = {"populate_by_name": True, "str_strip_whitespace": True}


# --------------------------------------------------------------------------- auth
class RegisterIn(_Model):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=2, max_length=80)

    @field_validator("password")
    @classmethod
    def _password_not_trivial(cls, value: str) -> str:
        if value.strip().lower() in {"password", "12345678", "password123", "qwerty123"}:
            raise ValueError("password is too easy to guess")
        return value


class LoginIn(_Model):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordIn(_Model):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(_Model):
    id: int
    email: str
    name: str
    role: str
    avatar_seed: str
    created_at: str


class SessionOut(_Model):
    token: str
    expires_at: int
    user: UserOut


class ProfileIn(_Model):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    email: EmailStr | None = None


# --------------------------------------------------------------------------- groups
class GroupIn(_Model):
    name: str = Field(min_length=2, max_length=120)
    handle: str | None = Field(default=None, max_length=120)
    description: str = Field(default="", max_length=400)
    url: str = Field(default="", max_length=300)
    category: str = Field(default="Community", max_length=60)
    privacy: Literal["public", "private", "hidden"] = "private"
    members: int = Field(default=0, ge=0)
    daily_posts: int = Field(default=0, ge=0)
    moderation: Literal["post_approval", "keyword_filter", "open", "admin_only"] = "post_approval"
    connected: bool = True


class GroupOut(_Model):
    id: int
    name: str
    handle: str
    description: str
    url: str
    category: str
    privacy: str
    members: int
    daily_posts: int
    moderation: str
    connected: bool
    last_synced_at: str | None
    created_at: str
    stats: dict[str, int] = Field(default_factory=dict)


# --------------------------------------------------------------------------- posts
class PostIn(_Model):
    group_id: int
    author_name: str = Field(min_length=2, max_length=120)
    message: str = Field(default="", max_length=4000)
    post_type: Literal["text", "photo", "link", "video", "poll", "live", "event"] = "text"
    state: Literal["published", "pending", "flagged", "scheduled"] = "published"
    reason: str = Field(default="", max_length=300)
    scheduled_for: str | None = None


class PostPatch(_Model):
    group_id: int | None = None
    author_name: str | None = Field(default=None, min_length=2, max_length=120)
    message: str | None = Field(default=None, max_length=4000)
    post_type: Literal["text", "photo", "link", "video", "poll", "live", "event"] | None = None
    state: Literal["published", "pending", "flagged", "scheduled"] | None = None
    reason: str | None = Field(default=None, max_length=300)
    scheduled_for: str | None = None


class PostOut(_Model):
    id: int
    group_id: int
    group_name: str = ""
    group_handle: str = ""
    author_id: int | None = None
    author_name: str
    avatar_seed: str = "??"
    message: str
    post_type: str
    state: str
    likes: int
    comments: int
    shares: int
    reports: int
    rule_id: int | None = None
    reason: str
    scheduled_for: str | None
    published_at: str | None
    created_at: str
    updated_at: str
    deleted_at: str | None


class BulkIn(_Model):
    ids: list[int] = Field(min_length=1, max_length=500)
    action: Literal[
        "delete", "restore", "purge", "approve", "decline", "flag", "unflag", "schedule"
    ]
    reason: str = Field(default="", max_length=300)
    scheduled_for: str | None = None


class PostFilters(_Model):
    """Shared by the bulk-by-filter endpoint and the rule engine."""

    group_ids: list[int] = Field(default_factory=list)
    states: list[Literal["published", "pending", "flagged", "scheduled"]] = Field(default_factory=list)
    post_types: list[str] = Field(default_factory=list)
    q: str = ""
    contains_link: bool | None = None
    author_id: int | None = None
    older_than_days: int | None = Field(default=None, ge=0, le=3650)
    min_reports: int | None = Field(default=None, ge=0)
    max_likes: int | None = Field(default=None, ge=0)
    include_trashed: bool = False


class BulkFilterIn(_Model):
    filters: PostFilters
    action: Literal["delete", "flag", "approve", "decline", "purge"] = "delete"
    name: str = Field(default="Manual sweep", max_length=120)
    dry_run: bool = False


class BulkResult(_Model):
    action: str
    matched: int
    processed: int
    ids: list[int] = Field(default_factory=list)
    dry_run: bool = False
    job_id: int | None = None


# --------------------------------------------------------------------------- rules
class RuleIn(_Model):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=400)
    group_id: int | None = None
    condition_type: Literal[
        "keyword", "domain", "age_days", "low_engagement", "reported",
        "repeat_poster", "banned_author", "duplicate",
    ] = "keyword"
    condition_value: str = Field(default="", max_length=400)
    threshold: int = Field(default=0, ge=0)
    action: Literal["delete", "flag", "approve", "decline", "archive"] = "delete"
    severity: Literal["low", "medium", "high"] = "medium"
    enabled: bool = True

    @field_validator("condition_value")
    @classmethod
    def _needs_value(cls, value: str, info: Any) -> str:
        kind = info.data.get("condition_type")
        if kind in {"keyword", "domain"} and not value.strip():
            raise ValueError(f"condition_value is required for the '{kind}' condition")
        return value


class RuleOut(_Model):
    id: int
    name: str
    description: str
    group_id: int | None
    group_name: str | None = None
    condition_type: str
    condition_value: str
    threshold: int
    action: str
    severity: str
    enabled: bool
    runs: int
    affected: int
    last_run_at: str | None
    created_at: str


class RuleRunIn(_Model):
    dry_run: bool = False


# --------------------------------------------------------------------------- authors
class AuthorIn(_Model):
    name: str = Field(min_length=2, max_length=120)
    handle: str | None = Field(default=None, max_length=120)
    group_id: int | None = None
    is_banned: bool = False
    risk_score: int = Field(default=0, ge=0, le=100)


class AuthorOut(_Model):
    id: int
    name: str
    handle: str
    avatar_seed: str
    group_id: int | None
    group_name: str | None = None
    joined_at: str
    is_banned: bool
    risk_score: int
    posts: int = 0
    removed: int = 0


# --------------------------------------------------------------------------- clean jobs
class JobOut(_Model):
    id: int
    name: str
    group_ids: list[int] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    action: str
    dry_run: bool
    status: str
    matched: int
    processed: int
    duration_ms: int
    created_at: str


# --------------------------------------------------------------------------- activity / stats
class ActivityOut(_Model):
    id: int
    actor: str
    action: str
    target_type: str
    target_id: int | None
    target_label: str
    group_id: int | None
    group_name: str | None = None
    detail: str
    created_at: str


class TimelinePoint(_Model):
    date: str
    deleted: int = 0
    pending: int = 0
    flagged: int = 0


class StatsOut(_Model):
    posts: dict[str, int]
    groups: dict[str, int]
    engagement: dict[str, int]
    cleanup: dict[str, int]
    top_groups: list[dict[str, Any]] = Field(default_factory=list)
    by_type: list[dict[str, Any]] = Field(default_factory=list)
    spam_patterns: list[dict[str, Any]] = Field(default_factory=list)
