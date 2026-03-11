#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"
python3 -m venv .venv
".venv/bin/pip" install -r requirements.txt
echo "Companion environment ready at ${ROOT_DIR}/.venv"
