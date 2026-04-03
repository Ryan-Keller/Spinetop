#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
echo "[start] memory watcher: inbox -> candidate promotion -> dispatch/pending"
python3 scripts/memory_watcher.py
