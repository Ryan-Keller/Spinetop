#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "[hermes-write] candidate memory written to inbox; promotion may open dispatch/pending"
python3 "$SCRIPT_DIR/hermes_write.py" "$@"
