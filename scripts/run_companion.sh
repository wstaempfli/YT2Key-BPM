#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOST="${COMPANION_HOST:-127.0.0.1}"
PORT="${COMPANION_PORT:-8765}"

if [[ ! -d "${ROOT_DIR}/.venv" ]]; then
  echo "Missing .venv. Run ./scripts/setup_companion.sh first."
  exit 1
fi

cd "${ROOT_DIR}"
status="$(
  ".venv/bin/python" - <<'PY' "${HOST}" "${PORT}"
import socket
import sys
host = sys.argv[1]
port = int(sys.argv[2])
s = socket.socket()
s.settimeout(0.75)
try:
    s.connect((host, port))
    print("already_running")
except OSError:
    print("not_running")
finally:
    s.close()
PY
)"
if [[ "${status}" == "already_running" ]]; then
  echo "Companion already running on ${HOST}:${PORT}"
  exit 0
fi
exec ".venv/bin/python" -m uvicorn service.app:app --host "${HOST}" --port "${PORT}"
