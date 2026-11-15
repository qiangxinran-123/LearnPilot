#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
BACKEND_PORT="${DEMO_BACKEND_PORT:-18080}"
FRONTEND_PORT="${DEMO_FRONTEND_PORT:-15173}"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
for command in node npm curl mktemp; do
  if ! command -v "$command" >/dev/null 2>&1; then
    printf 'Missing %s. Install Node >=22.12 <25, npm >=10 and curl.\n' "$command" >&2; exit 1
  fi
done
if [[ ! -x "$PYTHON" ]] || ! "$PYTHON" -c 'import sys,fastapi,uvicorn,sqlalchemy; assert sys.version_info >= (3,14)' >/dev/null 2>&1; then
  printf 'Python 3.14+ / dependencies missing. Run: python3.14 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt\n' >&2; exit 1
fi
if ! node -e 'const [a,b]=process.versions.node.split(".").map(Number); if(a<22 || a>=25 || (a===22 && b<12))process.exit(1)' || ! npm --version | awk -F. '{exit !($1>=10)}'; then
  printf 'Node >=22.12 <25 and npm >=10 required.\n' >&2; exit 1
fi
if [[ ! -x frontend/node_modules/.bin/vite ]]; then
  printf 'Frontend dependencies missing. Run: cd frontend && npm ci\n' >&2; exit 1
fi
if ! "$PYTHON" - "$BACKEND_PORT" "$FRONTEND_PORT" <<'PY'
import socket
import sys

ports = [int(value) for value in sys.argv[1:]]
if len(set(ports)) != 2 or any(port < 1024 or port > 65535 for port in ports):
    raise SystemExit("Demo ports must be different and in the range 1024-65535.")
sockets = []
try:
    for port in ports:
        probe = socket.socket()
        sockets.append(probe)
        probe.bind(("127.0.0.1", port))
except OSError:
    raise SystemExit("A requested demo port is already in use.")
finally:
    for probe in sockets:
        probe.close()
PY
then
  exit 1
fi
RUN_PARENT="$(mktemp -d /tmp/learnpilot-demo.XXXXXXXX)"
DEMO_DIR="$RUN_PARENT/session"
"$PYTHON" scripts/init_demo.py --destination "$DEMO_DIR"
export DATABASE_URL="sqlite+pysqlite:///$DEMO_DIR/demo.sqlite3"
export UPLOAD_ROOT="$DEMO_DIR/uploads" LEGACY_BOOTSTRAP_USER=legacy-bootstrap@learnpilot.local APP_ENV=development
export LLM_MODE=mock LLM_API_KEY='' LLM_BASE_URL='' LLM_MODEL=''
export VITE_BACKEND_ORIGIN="http://127.0.0.1:$BACKEND_PORT"
BACK_PID=''
FRONT_PID=''
cleanup() {
  trap - EXIT INT TERM
  for pid in "$FRONT_PID" "$BACK_PID"; do
    if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; fi
  done
  for pid in "$FRONT_PID" "$BACK_PID"; do
    if [[ -n "$pid" ]]; then wait "$pid" 2>/dev/null || true; fi
  done
  printf '\nDemo stopped. Isolated data preserved at %s\n' "$DEMO_DIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$PYTHON" -m uvicorn backend.main:app --host 127.0.0.1 --port "$BACKEND_PORT" &
BACK_PID=$!
for _ in {1..80}; do
  if curl -fsS "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1 &&
     curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/courses" | "$PYTHON" -c 'import json,sys; assert json.load(sys.stdin)["count"] >= 1' 2>/dev/null; then
    break
  fi
  if ! kill -0 "$BACK_PID" 2>/dev/null; then printf 'Backend failed to start.\n' >&2; exit 1; fi
  sleep 0.25
done
if ! curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/diagnostics/courses/1/readiness" |
  "$PYTHON" -c 'import json,sys; assert json.load(sys.stdin)["can_start"]' 2>/dev/null; then
  printf 'Demo database is not ready for initial diagnosis.\n' >&2; exit 1
fi
(cd frontend; exec ./node_modules/.bin/vite --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort) &
FRONT_PID=$!
for _ in {1..80}; do
  if curl -fsS "http://127.0.0.1:$FRONTEND_PORT/api/courses" |
    "$PYTHON" -c 'import json,sys; assert json.load(sys.stdin)["count"] >= 1' 2>/dev/null; then
    printf '\nLearnPilot demo: http://127.0.0.1:%s\n' "$FRONTEND_PORT"
    printf 'Mock AI; isolated data: %s\nPress Ctrl+C to stop both services.\n' "$DEMO_DIR"
    wait -n "$BACK_PID" "$FRONT_PID"
    exit 1
  fi
  if ! kill -0 "$FRONT_PID" 2>/dev/null; then printf 'Frontend failed to start.\n' >&2; exit 1; fi
  sleep 0.25
done
printf 'Frontend proxy did not become ready.\n' >&2
exit 1
