"""Static verification of the Postgres dialect.

No Postgres server is required: we drive the real service functions with a
recording stub that captures the SQL they build (instead of executing it),
translate it the way the Postgres driver would, and parse it with sqlglot's
Postgres grammar.

This is a **syntax** check, not a semantic one — sqlglot is lenient enough that
``AUTOINCREMENT`` also parses. It will catch malformed SQL, bad casts and
leftover SQLite-only clauses, but the authoritative check is running the whole
suite against a real server::

    DATABASE_URL=postgresql://... python -m pytest
"""
from __future__ import annotations

import pytest

sqlglot = pytest.importorskip("sqlglot")


class _StopExecution(Exception):
    """Raised by the recording stub so no query ever reaches a database."""


@pytest.fixture()
def pg(monkeypatch):
    """Force the postgres driver and capture SQL instead of running it."""
    from app import database as db

    monkeypatch.setattr(db, "DRIVER", "postgres")
    captured: list[tuple[str, tuple]] = []

    def record(kind):
        def _recorder(sql, params=()):
            captured.append((kind, db.translate(sql)))
            raise _StopExecution
        return _recorder

    monkeypatch.setattr(db, "query", record("query"))
    monkeypatch.setattr(db, "query_one", record("query_one"))
    monkeypatch.setattr(db, "scalar", record("scalar"))
    monkeypatch.setattr(db, "execute", record("execute"))
    return db, captured


def _drain(captured):
    """Run service calls, swallowing the stub's stop signal, and return the SQL."""
    return [sql for _, sql in captured]


def test_placeholder_translation_skips_quoted_text(monkeypatch):
    from app import database as db

    monkeypatch.setattr(db, "DRIVER", "postgres")
    assert db.translate("SELECT * FROM t WHERE a = ? AND b = ?") == \
        "SELECT * FROM t WHERE a = %s AND b = %s"
    # A question mark inside a literal must survive untouched.
    assert db.translate("SELECT 'is it?' AS q WHERE a = ?") == \
        "SELECT 'is it?' AS q WHERE a = %s"
    assert db.translate("SELECT 1") == "SELECT 1"

    monkeypatch.setattr(db, "DRIVER", "sqlite")
    assert db.translate("SELECT * FROM t WHERE a = ?") == "SELECT * FROM t WHERE a = ?"


def test_date_expr_casts_on_postgres_only(monkeypatch):
    from app import database as db

    monkeypatch.setattr(db, "DRIVER", "postgres")
    assert db.date_expr("created_at") == "date(created_at::timestamptz)"
    monkeypatch.setattr(db, "DRIVER", "sqlite")
    assert db.date_expr("created_at") == "date(created_at)"


def test_postgres_ddl_parses(monkeypatch):
    from app import database as db

    monkeypatch.setattr(db, "DRIVER", "postgres")
    schema = db._SCHEMA.replace("{pk}", db.DIALECTS["postgres"]["pk"])
    statements = [s.strip() for s in schema.split(";") if s.strip()]
    assert len(statements) >= 14, "expected the full schema to be generated"
    for statement in statements:
        sqlglot.parse_one(statement, read="postgres")


def test_no_sqlite_only_syntax_remains(pg):
    db, captured = pg
    from app import services

    filters = dict(
        group_ids=[1, 2], states=["pending", "flagged"], post_types=["link"],
        q="crypto", contains_link=True, older_than_days=30, min_reports=2,
        max_likes=0,
    )
    calls = [
        lambda: services.list_groups(1, q="foo"),
        lambda: services.get_group(1, 2),
        lambda: services.list_authors(1, q="x", group_id=2),
        lambda: services.list_rules(1, group_id=2, enabled_only=True),
        lambda: services.list_activity(1, q="x", action="post."),
        lambda: services.list_jobs(1),
        lambda: services.timeline(1, days=7),
        lambda: services.overview(1),
        lambda: services.count_matching(1, filters),
        lambda: services.list_posts(1, sort="title", **filters),
        lambda: services.list_posts(1, sort="engagement", trashed_only=True, **filters),
    ]
    for call in calls:
        with pytest.raises(_StopExecution):
            call()

    statements = _drain(captured)
    assert statements, "no SQL was captured — the stub is not wired up"
    for statement in statements:
        lowered = statement.lower()
        assert "collate nocase" not in lowered, statement
        assert "autoincrement" not in lowered, statement
        assert "pragma" not in lowered, statement
        sqlglot.parse_one(statement, read="postgres")


def test_no_bare_percent_in_sql_literals(pg):
    """psycopg treats a bare % in the query string as a placeholder escape."""
    db, captured = pg
    from app import services

    with pytest.raises(_StopExecution):
        services.list_posts(1, contains_link=True)
    with pytest.raises(_StopExecution):
        services.list_posts(1, contains_link=False)

    assert captured
    for _, statement in captured:
        # every % must be part of a %s placeholder
        cleaned = statement.replace("%s", "")
        assert "%" not in cleaned, statement


# ---------------------------------------------------------------------------
# Context-manager contract
#
# psycopg_pool's `Pool.connection()` yields a connection from a context
# manager; it is not a connection. Treating it as one raises
# AttributeError('... object has no attribute cursor') at startup, so the
# fake pool below refuses to hand out a bare connection.
# ---------------------------------------------------------------------------
class _FakeCursor:
    def __init__(self):
        self.rows: list = []
        self.rowcount = 0

    def execute(self, sql, params=()):
        _FakeCursor.last = sql  # noqa: SLF001
        self.rows = [{"id": 7}]
        self.rowcount = 1

    def executemany(self, sql, seq):
        self.rowcount = len(list(seq))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return {"id": 7}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def cursor(self):
        return _FakeCursor()

    def commit(self):
        pass


class _FakePool:
    """Mimics psycopg_pool: `connection()` is a context manager, not a conn."""

    def connection(self):
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            yield _FakeConn()

        return _cm()

    def close(self):
        pass


@pytest.fixture()
def fake_pg(monkeypatch):
    from app import database as db

    monkeypatch.setattr(db, "DRIVER", "postgres")
    monkeypatch.setattr(db, "_pool", _FakePool())
    return db


def test_every_entry_point_honours_the_pool_contract(fake_pg):
    fake_pg.init_db()
    assert fake_pg.scalar("SELECT COUNT(*) FROM users WHERE id = ?", (1,)) == 7
    assert fake_pg.query("SELECT * FROM posts WHERE owner_id = ?", (1,)) == [{"id": 7}]
    assert fake_pg.query_one("SELECT * FROM posts WHERE id = ?", (1,)) == {"id": 7}
    assert fake_pg.execute("INSERT INTO posts (owner_id) VALUES (?)", (1,)) == 7
    assert fake_pg.execute("UPDATE posts SET state = ? WHERE id = ?", ("x", 1)) == 1
    assert fake_pg.execute_many("INSERT INTO t (a) VALUES (?)", [(1,), (2,)]) == 2
    rows, info = fake_pg.paginate(
        "SELECT * FROM posts WHERE owner_id = ? LIMIT {limit} OFFSET {offset}", (1,), 2, 10
    )
    assert info == {"page": 2, "per_page": 10}


def test_ddl_question_marks_are_not_treated_as_placeholders(fake_pg):
    """`avatar_seed TEXT DEFAULT '??'` must survive into the DDL untouched."""
    fake_pg.init_db()
    assert "DEFAULT '??'" in _FakeCursor.last
