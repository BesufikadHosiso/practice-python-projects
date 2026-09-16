# Group Post Cleaner

A full-stack moderation console for **Facebook group owners and admins**: work the pending
queue, bulk-delete posted spam across every group you run, purge reported content, and let
cleanup rules handle the boring part automatically.

FastAPI + SQLite on the back end, a dependency-free ES-module single-page app on the front.
No build step, no `npm install` — clone it, seed it, run it.

```
admin@demo.com  /  demo1234
```

---

## Quick start

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or just `./run.sh`, which installs dependencies and starts the server.

Open <http://localhost:8000> and sign in with the credentials above. The API docs are at
<http://localhost:8000/api/docs>.

Everything the app writes lives in `data/cleaner.db` (git-ignored). **If the database is empty
the demo workspace seeds itself on startup**, so a fresh clone — or a wiped `data/` — serves a
fully populated app with no extra step. Use `python -m app.seed --fresh` to rebuild it on
demand.

## Tests

```bash
python -m pytest -q          # 55 tests, each against a throwaway database
```

---

## What it does

| Area | What you get |
| --- | --- |
| **Pending queue** | Every post awaiting approval, across all groups. Approve / decline / delete individually or in bulk. |
| **Flagged & reported** | Reported content sorted by report count, with dismiss-report and bulk delete. |
| **All posts** | The full firehose with filters for group, state, type, links, plus text search and sorting. |
| **Trash** | Every deletion lands here first, keeping its prior state. Restore one, restore all, or purge. |
| **Bulk cleaner** | Compose a filter (keyword, domain, age, reactions, reports, type, group), see the exact match count and a sample live, then sweep. A dry run always runs first. |
| **Cleanup rules** | Nine shipped rules covering crypto spam, DM solicitation, shortened URLs, reported posts, zero-engagement, age, repeat posters, banned authors and duplicates. Preview before running, toggle, edit, delete. |
| **Members** | Watch-list ranked by how much content you've removed. Ban a member to sweep every live post they made. |
| **Groups** | CRUD for the groups you administer, per-group health score, simulated Facebook sync. |
| **Run history / Activity log** | Every sweep and every moderation action, filterable and clearable. |

### The deletion model

Nothing is destroyed by accident. `delete`, `decline` and `archive` are **soft deletes**: the row
keeps its `prior_state`, so restoring puts a post back exactly as it was (a flagged post comes
back flagged, not published). `purge` is the only destructive path, and it is always behind a
confirmation.

Every bulk action shows an **Undo** toast that issues the matching restore.

---

## Architecture

```
app/
├── main.py              FastAPI factory + SPA hosting
├── config.py            paths, token TTL, demo credentials
├── database.py          SQLite schema, thread-local connections, helpers
├── security.py          PBKDF2 password hashing, HMAC-signed bearer tokens
├── schemas.py           Pydantic request/response models
├── services.py          domain logic: CRUD, bulk ops, rule engine, stats
├── deps.py              bearer-token auth dependency
├── seed.py              deterministic demo workspace
├── routers/             thin HTTP layer (auth, groups, posts, rules, authors, jobs, activity, stats)
└── static/              the SPA
    ├── index.html       shell + inline SVG icon sprite
    ├── css/app.css      design tokens, components, dark mode, responsive
    └── js/
        ├── app.js       auth gate, shell, sidebar, hash router
        ├── api.js       fetch wrapper + token handling
        ├── store.js     session/cache state with pub-sub
        ├── ui.js        toasts, modals, drawers, skeletons, empty states, formatting
        ├── components/  post detail drawer + create/edit modal
        └── pages/       one module per screen
```

**Multi-tenant by default.** Every row carries `owner_id` and every query filters on it, so one
account can never read or mutate another's data (covered by `TestIsolation`).

**Persistence** is a single SQLite file in WAL mode with foreign keys on. `deleted_at` implements
the trash; `prior_state` makes restores faithful.

**The rule engine** translates a rule into a shared filter vocabulary (`keyword`, `domain`,
`age_days`, `low_engagement`, `reported`) and falls back to dedicated sub-queries for the three
conditions a flat filter can't express (`repeat_poster`, `duplicate`, `banned_author`). The same
code path powers dry runs, previews and real runs, so what you preview is what you get.

> Note on Facebook: the Graph API requires app review and a long-lived token, so "sync" is
> simulated — it fabricates believable new posts so the queue has something to work through.
> Everything downstream of the sync is real.

## Deploying

### Vercel (Postgres required)

Vercel is serverless: the deployment directory is **read-only** and there is no
persistent disk, so the bundled SQLite file cannot be used. Set `DATABASE_URL`
to a managed Postgres (Neon and Supabase both have free tiers):

1. Create a database and copy its connection string.
2. In the Vercel project, add these environment variables:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | `postgresql://user:pass@host/db?sslmode=require` |
   | `PGPC_SECRET_KEY` | a long random string — see below |
   | `PGPC_DEMO_PASSWORD` | optional, changes the demo login |

   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # a good SECRET_KEY
   ```

3. Import the repo and deploy. `vercel.json` and `api/index.py` are already in
   place — the latter bridges FastAPI (ASGI) to the WSGI runtime Vercel's Python
   builder provides.

The schema is created and the demo workspace seeded automatically on first
request.

> `PGPC_SECRET_KEY` is not optional in production. It signs every auth token,
> and the checked-in default is public — without your own, anyone could mint a
> valid token for any user.
>
> If you deploy without `DATABASE_URL`, startup fails immediately with a message
> saying so, rather than dying later with a confusing `PermissionError`.

### Anywhere with a real disk (no config needed)

Render, Railway, Fly.io or a plain VPS can run the SQLite build unchanged:

```bash
pip install -r requirements.txt
./run.sh
```

`run.sh` installs dependencies and serves on port 8000. For a container, point
the start command at
`uvicorn app.main:app --host 0.0.0.0 --port $PORT` and mount a volume at
`/app/data` so the database survives restarts.

### Storage back ends

| | SQLite (default) | Postgres (`DATABASE_URL` set) |
| --- | --- | --- |
| Setup | none | a connection string |
| Persistence | `data/cleaner.db` | the managed database |
| Good for | local dev, tests, single-host deploys | serverless, multiple instances |

Both are exercised by the test-suite: the SQLite path runs on every
`pytest`, and `tests/test_postgres_dialect.py` verifies the Postgres dialect
statically (SQL parses as Postgres, no SQLite-only clauses, correct placeholder
translation, correct connection-pool usage). To run the **whole** suite against
a live server:

```bash
DATABASE_URL=postgresql://... python -m pytest
```

## Frontend notes

No framework and no bundler: 18 ES modules served straight from disk, lazily imported per route.

- **Optimistic updates** — deleting removes the card immediately, fires the request, and rolls
  back to a server refetch if it fails.
- **Loading states** — skeleton posts, cards, stats and tables matched to each layout.
- **Empty states** — every list has a purpose-built one, with a next action where it makes sense.
- **Responsive** — the sidebar becomes an off-canvas drawer under 860px, tables collapse to
  labelled rows under 560px.
- **Dark mode** — a pure CSS-token swap, defaulting to your system preference.
- **Accessible** — real focus rings, `aria-current`/`aria-pressed`/`aria-modal`, Escape closes
  overlays, `/` focuses search, and untrusted text is escaped before it ever reaches `innerHTML`.

## Scripts

| Command | What it does |
| --- | --- |
| `./run.sh` | Seed (if needed) and serve on port 8000 |
| `./scripts/smoke.sh` | Curl-driven smoke test against a running server |
| `python -m app.seed --fresh` | Rebuild the demo workspace from scratch |
| `python -m pytest -q` | Run the test suite (55 tests) |
