#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
echo "[run] honcho bridge: collective -> mirrored/honcho"
python3 scripts/honcho_bridge.py
