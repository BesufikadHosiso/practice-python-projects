#!/usr/bin/env bash
# Manual smoke test against a running server (default http://localhost:8000).
set -euo pipefail
BASE="${BASE:-http://localhost:8000}"
EMAIL="${EMAIL:-admin@demo.com}"
PASS="${PASS:-demo1234}"

jqr() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }

TOKEN=$(curl -sf -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" | jqr "d['token']")
AUTH="Authorization: Bearer $TOKEN"
echo "logged in (token ${#TOKEN} chars)"

say() { printf '\n\033[1m%s\033[0m\n' "$1"; }

say "GET /api/health"
curl -sf "$BASE/api/health" | python3 -m json.tool

say "GET /api/groups"
curl -sf "$BASE/api/groups" -H "$AUTH" | jqr "(d['pagination'], [g['name'] for g in d['items']])"

say "GET /api/posts?per_page=4"
curl -sf "$BASE/api/posts?per_page=4" -H "$AUTH" | \
  jqr "(d['pagination'], [(p['id'],p['state'],p['post_type'],p['message'][:50]) for p in d['items']])"

say "GET /api/posts?state=pending"
curl -sf "$BASE/api/posts?state=pending&per_page=3" -H "$AUTH" | jqr "(d['pagination'], [p['id'] for p in d['items']])"

say "GET /api/posts/trash"
curl -sf "$BASE/api/posts/trash?per_page=3" -H "$AUTH" | jqr "(d['pagination'], [(p['id'],p.get('prior_state')) for p in d['items']])"

say "GET /api/stats/overview"
curl -sf "$BASE/api/stats/overview" -H "$AUTH" | jqr "(d['posts'], d['cleanup'])"

say "GET /api/stats/timeline?days=7"
curl -sf "$BASE/api/stats/timeline?days=7" -H "$AUTH" | jqr "d['items'][:3]"

say "GET /api/rules"
curl -sf "$BASE/api/rules" -H "$AUTH" | jqr "[(r['id'],r['name'],r['action'],r['enabled']) for r in d['items']]"

say "GET /api/authors"
curl -sf "$BASE/api/authors" -H "$AUTH" | jqr "[(a['name'],a['posts'],a['removed'],a['is_banned']) for a in d['items'][:5]]"

say "GET /api/jobs"
curl -sf "$BASE/api/jobs" -H "$AUTH" | jqr "[(j['id'],j['name'],j['action'],j['processed']) for j in d['items']]"

say "GET /api/activity?per_page=5"
curl -sf "$BASE/api/activity?per_page=5" -H "$AUTH" | jqr "[(a['action'],a['target_label'][:30]) for a in d['items']]"

say "SPA root"
curl -sf -o /dev/null -w "index.html -> %{http_code} (%{size_download} bytes)\n" "$BASE/"
curl -sf -o /dev/null -w "unknown route -> %{http_code}\n" "$BASE/posts/123"
curl -s -o /dev/null -w "unknown api -> %{http_code}\n" "$BASE/api/nope"

echo; echo "smoke test OK"
