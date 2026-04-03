#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
echo "[start] honcho bridge watcher: collective -> mirrored/honcho, governed admission only"
python3 scripts/honcho_bridge_watcher.py
