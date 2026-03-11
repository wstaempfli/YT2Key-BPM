#!/usr/bin/env bash
set -euo pipefail

HOST="${COMPANION_HOST:-127.0.0.1}"
PORT="${COMPANION_PORT:-8765}"

pids="$(lsof -tiTCP:"${PORT}" -sTCP:LISTEN || true)"
if [[ -z "${pids}" ]]; then
  echo "No companion process listening on ${HOST}:${PORT}"
  exit 0
fi

echo "Stopping companion on ${HOST}:${PORT} (PID(s): ${pids})"
kill ${pids}
sleep 0.4

still_up="$(lsof -tiTCP:"${PORT}" -sTCP:LISTEN || true)"
if [[ -n "${still_up}" ]]; then
  echo "Process still running, sending SIGKILL..."
  kill -9 ${still_up}
fi

echo "Companion stopped."
