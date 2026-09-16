"""Storage layer with two interchangeable back ends.

SQLite is the default, which keeps local development and the test-suite
dependency-free. Set ``DATABASE_URL`` (a ``postgres://``/``postgresql://`` DSN)
to run on Postgres instead — that is what serverless hosts such as Vercel need,
because they have no writable persistent disk.

The two back ends are deliberately kept behaviourally identical:

* SQL is written once with ``?`` placeholders and translated to ``%s`` for
  psycopg. The translation skips quoted literals so it can never corrupt a
  string containing a question mark.
* Timestamps are stored as ISO-8601 **text** in both back ends. The app only
  ever compares them lexicographically (always UTC, always the same offset
  format) or hands them to JavaScript, so text keeps the two dialects in exact
  parity and avoids a whole class of timezone surprises.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import config

# One source of truth for the schema; only the primary-key clause differs.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER {pk},
    email         TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'owner',
    avatar_seed   TEXT    NOT NULL DEFAULT 'AR',
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
    id            INTEGER {pk},
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
    id            INTEGER {pk},
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

CREATE TABLE IF NOT EXISTS rules (
    id             INTEGER {pk},
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

CREATE TABLE IF NOT EXISTS posts (
    id            INTEGER {pk},
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

CREATE TABLE IF NOT EXISTS clean_jobs (
    id           INTEGER {pk},
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
    id           INTEGER {pk},
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

DIALECTS = {
    "sqlite": {"pk": "PRIMARY KEY AUTOINCREMENT"},
    "postgres": {"pk": "GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"},
}

DRIVER = "postgres" if config.DATABASE_URL else "sqlite"

_local = threading.local()
_lock = threading.Lock()
_pool = None
# Every sqlite connection this process has opened, so `close_conn()` can drop
# them all. Without this, pooled worker threads keep a live handle on a database
# file that has already been swapped out (which is exactly what the tests do).
_all_conns: list[sqlite3.Connection] = []


def utcnow() -> str:
    """ISO-8601 timestamp in UTC, truncated to whole seconds."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def translate(sql: str) -> str:
    """Rewrite ``?`` placeholders to psycopg's ``%s``, skipping quoted text."""
    if DRIVER == "sqlite":
        return sql
    out: list[str] = []
    quote: str | None = None
    for char in sql:
        if quote:
            out.append(char)
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
            out.append(char)
            continue
        out.append("%s" if char == "?" else char)
    return "".join(out)


def date_expr(column: str) -> str:
    """Calendar-day bucket for the activity timeline, per dialect."""
    return f"date({column})" if DRIVER == "sqlite" else f"date({column}::timestamptz)"


def init_db() -> None:
    # Plain replace, not str.format: the schema contains a literal '{}' in
    # `DEFAULT '{}'`, which format() would try to interpret as a field.
    schema = _SCHEMA.replace("{pk}", DIALECTS[DRIVER]["pk"])
    if DRIVER == "sqlite":
        get_conn().executescript(schema)
        get_conn().commit()
    else:
        # Pool.connection() yields a connection from a context manager; it is
        # not a connection itself, so it must be entered before use.
        with get_conn() as conn, conn.cursor() as cursor:
            cursor.execute(schema)
            conn.commit()


def reset_db(path: Path | str | None = None) -> None:
    """Drop every table. Used by the test-suite and ``seed --fresh``."""
    global _pool
    if path is not None and DRIVER == "sqlite":
        config.DB_PATH = Path(path)
    close_conn()
    if DRIVER == "sqlite":
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(f"{config.DB_PATH}{suffix}")
            if candidate.exists():
                candidate.unlink()
    init_db()
    if DRIVER == "postgres":
        for table in ("activity", "clean_jobs", "posts", "rules", "authors", "groups", "users"):
            execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")


# --------------------------------------------------------------- connections
def _sqlite_conn() -> sqlite3.Connection:
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


def _pg_pool():
    """Lazily built connection pool (serverless cold starts must not hang)."""
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool
        from psycopg.rows import dict_row

        _pool = ConnectionPool(
            config.DATABASE_URL,
            min_size=0,
            max_size=int(config.PG_POOL_MAX),
            kwargs={
                "row_factory": dict_row,
                "autocommit": False,
                # Supabase's transaction pooler (port 6543) is PgBouncer in
                # transaction mode, which cannot carry prepared statements
                # across the transactions it multiplexes. psycopg3 promotes a
                # query to a prepared statement after 5 executions by default
                # (prepare_threshold=5), so a busy deployment would start
                # failing intermittently. None disables promotion entirely,
                # which works with the transaction *and* session poolers.
                "prepare_threshold": None,
                "connect_timeout": int(config.PG_CONNECT_TIMEOUT),
            },
            open=True,
            timeout=30,
        )
    return _pool


def get_conn():
    if DRIVER == "sqlite":
        return _sqlite_conn()
    return _pg_pool().connection()


def close_conn() -> None:
    """Close this thread's sqlite connection, every other open one, and the pool."""
    global _pool
    with _lock:
        for conn in _all_conns:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        _all_conns.clear()
    _local.conn = None
    if _pool is not None:
        try:
            _pool.close()
        except Exception:  # noqa: BLE001 - pool may already be shut down
            pass
        _pool = None


# ------------------------------------------------------------------- queries
def query(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    if DRIVER == "sqlite":
        cur = get_conn().execute(sql, tuple(params))
        rows = [dict(row) for row in cur.fetchall()]
        cur.close()
        return rows
    with get_conn() as conn, conn.cursor() as cursor:
        cursor.execute(translate(sql), tuple(params))
        return [dict(row) for row in cursor.fetchall()]


def query_one(sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    """Run a write statement and return the new (or affected) row id."""
    if DRIVER == "sqlite":
        conn = get_conn()
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        row_id = cur.lastrowid or cur.rowcount
        cur.close()
        return int(row_id)

    with get_conn() as conn, conn.cursor() as cursor:
        statement = translate(sql)
        if statement.lstrip().upper().startswith("INSERT"):
            statement = f"{statement} RETURNING id"
            cursor.execute(statement, tuple(params))
            row = cursor.fetchone()
            conn.commit()
            return int(row["id"]) if row else 0
        cursor.execute(statement, tuple(params))
        affected = cursor.rowcount
        conn.commit()
        return int(affected)


def execute_many(sql: str, seq: Iterable[Sequence[Any]]) -> int:
    rows = list(seq)
    if not rows:
        return 0
    if DRIVER == "sqlite":
        conn = get_conn()
        cur = conn.executemany(sql, [tuple(item) for item in rows])
        conn.commit()
        count = cur.rowcount
        cur.close()
        return count
    with get_conn() as conn, conn.cursor() as cursor:
        cursor.executemany(translate(sql), [tuple(item) for item in rows])
        affected = cursor.rowcount
        conn.commit()
        return affected


def scalar(sql: str, params: Sequence[Any] = ()) -> Any:
    if DRIVER == "sqlite":
        cur = get_conn().execute(sql, tuple(params))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    with get_conn() as conn, conn.cursor() as cursor:
        cursor.execute(translate(sql), tuple(params))
        row = cursor.fetchone()
        return next(iter(row.values())) if row else None


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


def dump_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def load_json(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback
