#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_DIR="${ROOT_DIR}/tools/keyfinder_cli"
BUILD_DIR="${SOURCE_DIR}/build"

cmake -S "${SOURCE_DIR}" -B "${BUILD_DIR}"
cmake --build "${BUILD_DIR}" -j

echo "Built: ${BUILD_DIR}/keyfinder_cli"
