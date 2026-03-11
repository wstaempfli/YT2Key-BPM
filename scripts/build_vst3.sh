#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /absolute/path/to/JUCE"
  exit 1
fi

JUCE_DIR="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${ROOT_DIR}/plugin/build"

cmake -S "${ROOT_DIR}/plugin" -B "${BUILD_DIR}" -DJUCE_DIR="${JUCE_DIR}"
cmake --build "${BUILD_DIR}" -j

echo "Built VST3 in ${BUILD_DIR}"
