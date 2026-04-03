#!/usr/bin/env bash
set -euo pipefail

cd /mnt/d/spine_desk/Spinetop/services/honcho/upstream

echo "[1/3] activating venv"
source .venv/bin/activate

echo "[2/3] setting config"
export HONCHO_CONFIG="/mnt/d/spine_desk/Spinetop/services/honcho/honcho-family.config.toml"

echo "[3/3] starting honcho"
uvicorn src.main:app --host 0.0.0.0 --port 8000
