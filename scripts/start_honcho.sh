#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../services/honcho/upstream"

echo "[1/3] activating venv"
source .venv/bin/activate

echo "[2/3] setting config for storage-only honcho mirror"
export HONCHO_CONFIG="$SCRIPT_DIR/../services/honcho/honcho-family.config.toml"

echo "[3/3] starting honcho storage layer"
uvicorn src.main:app --host 0.0.0.0 --port 8000
