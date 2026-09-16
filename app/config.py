"""Configuration for the Group Post Cleaner application."""
from __future__ import annotations

import os
from pathlib import Path

# Repository root (the folder that contains ``app/``).
BASE_DIR = Path(__file__).resolve().parent.parent

# Everything the app writes at runtime lives under ``data/`` so the checkout
# stays clean.  Both locations can be overridden through the environment which
# is what the test-suite uses to run against a throwaway database.
DATA_DIR = Path(os.environ.get("PGPC_DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.environ.get("PGPC_DB_PATH", DATA_DIR / "cleaner.db"))

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Leave DATABASE_URL unset to use the bundled SQLite file. Point it at a
# postgres:// DSN (Neon, Supabase, RDS, …) to run on Postgres, which is what a
# serverless host such as Vercel requires — those have no writable disk.
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("PGPC_DATABASE_URL") or ""
PG_POOL_MAX = os.environ.get("PGPC_PG_POOL_MAX", "5")

SECRET_KEY = os.environ.get("PGPC_SECRET_KEY", "dev-secret-please-change-in-production")
TOKEN_TTL_SECONDS = int(os.environ.get("PGPC_TOKEN_TTL", 60 * 60 * 12))
TOKEN_ISSUER = "group-post-cleaner"

# Credentials for the account created by ``python -m app.seed``.
DEMO_EMAIL = os.environ.get("PGPC_DEMO_EMAIL", "admin@demo.com")
DEMO_PASSWORD = os.environ.get("PGPC_DEMO_PASSWORD", "demo1234")

APP_NAME = "Group Post Cleaner"
