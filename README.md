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

python -m app.seed --fresh            # create the demo workspace (idempotent)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or just `./run.sh`, which does both.

Open <http://localhost:8000> and sign in with the credentials above. The API docs are at
<http://localhost:8000/api/docs>.

Everything the app writes lives in `data/cleaner.db` (git-ignored). `python -m app.seed --fresh`
wipes and rebuilds it.

## Tests

```bash
python -m pytest -q          # 47 tests, each against a throwaway database
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
| `python -m pytest -q` | Run the test suite |
