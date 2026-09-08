"""SQLite plumbing: schema, thread-local connections and small helpers.

The application deliberately uses the standard library ``sqlite3`` module so
there is nothing extra to install for a practice project, while still giving us
real persistent storage that survives restarts.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'owner',
    avatar_seed   TEXT    NOT NULL DEFAULT 'AR',
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          TEXT    NOT NULL,
    handle        TEXT    NOT NULL,
    description   TEXT    NOT NULL DEFAULT '',
    url           TEXT    NOT NULL DEFAULT '',
    category      TEXT    NOT NULL DEFAULT 'Community',
    privacy       TEXT    NOT NULL DEFAULT 'private',
    members       INTEGER NOT NULL DEFAULT 0,
    daily_posts   INTEGER NOT NULL DEFAULT 0,
    moderation    TEXT    NOT NULL DEFAULT 'post_approval',
    connected     INTEGER NOT NULL DEFAULT 1,
    last_synced_at TEXT,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS authors (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id      INTEGER REFERENCES groups(id) ON DELETE CASCADE,
    name          TEXT    NOT NULL,
    handle        TEXT    NOT NULL,
    avatar_seed   TEXT    NOT NULL DEFAULT '??',
    joined_at     TEXT    NOT NULL,
    is_banned     INTEGER NOT NULL DEFAULT 0,
    risk_score    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id      INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    author_id     INTEGER REFERENCES authors(id) ON DELETE SET NULL,
    author_name   TEXT    NOT NULL,
    message       TEXT    NOT NULL DEFAULT '',
    post_type     TEXT    NOT NULL DEFAULT 'text',
    state         TEXT    NOT NULL DEFAULT 'published',
    likes         INTEGER NOT NULL DEFAULT 0,
    comments      INTEGER NOT NULL DEFAULT 0,
    shares        INTEGER NOT NULL DEFAULT 0,
    reports       INTEGER NOT NULL DEFAULT 0,
    rule_id       INTEGER REFERENCES rules(id) ON DELETE SET NULL,
    reason        TEXT    NOT NULL DEFAULT '',
    prior_state   TEXT,
    scheduled_for TEXT,
    published_at  TEXT,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    deleted_at    TEXT
);

CREATE TABLE IF NOT EXISTS rules (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id       INTEGER REFERENCES groups(id) ON DELETE CASCADE,
    name           TEXT    NOT NULL,
    description    TEXT    NOT NULL DEFAULT '',
    condition_type TEXT    NOT NULL DEFAULT 'keyword',
    condition_value TEXT   NOT NULL DEFAULT '',
    threshold      INTEGER NOT NULL DEFAULT 0,
    action         TEXT    NOT NULL DEFAULT 'delete',
    severity       TEXT    NOT NULL DEFAULT 'medium',
    enabled        INTEGER NOT NULL DEFAULT 1,
    runs           INTEGER NOT NULL DEFAULT 0,
    affected       INTEGER NOT NULL DEFAULT 0,
    last_run_at    TEXT,
    created_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS clean_jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    group_ids    TEXT    NOT NULL DEFAULT '[]',
    filters      TEXT    NOT NULL DEFAULT '{}',
    action       TEXT    NOT NULL DEFAULT 'delete',
    dry_run      INTEGER NOT NULL DEFAULT 0,
    status       TEXT    NOT NULL DEFAULT 'completed',
    matched      INTEGER NOT NULL DEFAULT 0,
    processed    INTEGER NOT NULL DEFAULT 0,
    duration_ms  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS activity (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    actor        TEXT    NOT NULL,
    action       TEXT    NOT NULL,
    target_type  TEXT    NOT NULL DEFAULT 'post',
    target_id    INTEGER,
    target_label TEXT    NOT NULL DEFAULT '',
    group_id     INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    detail       TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_posts_owner_state ON posts(owner_id, state);
CREATE INDEX IF NOT EXISTS idx_posts_group ON posts(group_id);
CREATE INDEX IF NOT EXISTS idx_posts_deleted ON posts(deleted_at);
CREATE INDEX IF NOT EXISTS idx_activity_owner ON activity(owner_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_groups_owner ON groups(owner_id);
CREATE INDEX IF NOT EXISTS idx_rules_owner ON rules(owner_id);
CREATE INDEX IF NOT EXISTS idx_authors_owner ON authors(owner_id);
"""

_local = threading.local()
_lock = threading.Lock()
# Every connection this process has opened, so `close_conn()` can drop them all.
# Without this, pooled worker threads (e.g. FastAPI's TestClient portal) keep a
# live handle on a database file that has already been swapped out.
_all_conns: list[sqlite3.Connection] = []


def utcnow() -> str:
    """ISO-8601 timestamp in UTC, truncated to whole seconds."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_conn() -> sqlite3.Connection:
    """Return a per-thread connection, creating (and migrating) it if needed."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        _local.conn = conn
        with _lock:
            _all_conns.append(conn)
    return conn


def close_conn() -> None:
    """Close this thread's connection *and* every other open one.

    Callers that swap ``config.DB_PATH`` (tests, ``seed --fresh``) rely on this
    to make sure no thread keeps reading the old file.
    """
    with _lock:
        for conn in _all_conns:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        _all_conns.clear()
    _local.conn = None


def init_db() -> None:
    get_conn().executescript(SCHEMA)
    get_conn().commit()


def reset_db(path: Path | None = None) -> None:
    """Drop every table. Used by the test-suite and ``seed --fresh``."""
    if path is not None:
        config.DB_PATH = Path(path)
    close_conn()
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = Path(f"{config.DB_PATH}{suffix}")
        if candidate.exists():
            candidate.unlink()
    init_db()


def query(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    cur = get_conn().execute(sql, tuple(params))
    rows = cur.fetchall()
    cur.close()
    return [dict(row) for row in rows]


def query_one(sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    """Run a write statement and return the new/affected row id."""
    conn = get_conn()
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    row_id = cur.lastrowid or cur.rowcount
    cur.close()
    return int(row_id)


def execute_many(sql: str, seq: Iterable[Sequence[Any]]) -> int:
    conn = get_conn()
    cur = conn.executemany(sql, [tuple(item) for item in seq])
    conn.commit()
    count = cur.rowcount
    cur.close()
    return count


def scalar(sql: str, params: Sequence[Any] = ()) -> Any:
    cur = get_conn().execute(sql, tuple(params))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def dump_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def load_json(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def paginate(
    sql: str, params: Sequence[Any], page: int, per_page: int
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Run ``sql`` (it must contain a ``{limit}``/``{offset}`` placeholder).

    Returns the page of rows plus a small pagination envelope so every list
    endpoint can answer ``?page=2&per_page=25`` the same way.
    """
    per_page = max(1, min(per_page, 200))
    page = max(1, page)
    offset = (page - 1) * per_page
    # LIMIT/OFFSET are interpolated (they are ints we clamped above), so the
    # caller's ``params`` are the *only* bound values.
    rows = query(sql.format(limit=per_page, offset=offset), list(params))
    return rows, {"page": page, "per_page": per_page}
