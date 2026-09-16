#!/usr/bin/env bash
# Seed the demo workspace (if it isn't there yet) and serve the app.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
  echo "Installing dependencies…"
  pip3 install --quiet --break-system-packages -r requirements.txt
fi

echo "Seeding the demo workspace (no-op if it already exists)…"
python3 -m app.seed

echo
echo "  Group Post Cleaner"
echo "  → http://localhost:${PORT}"
echo "  → API docs: http://localhost:${PORT}/api/docs"
echo "  → sign in:  admin@demo.com / demo1234"
echo
exec python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT"
