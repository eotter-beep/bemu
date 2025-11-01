#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "launch.sh: unable to find interpreter '$PYTHON_BIN'" >&2
  exit 127
fi

exec "$PYTHON_BIN" "$REPO_ROOT/tools/gui_vm_manager.py" "$@"
