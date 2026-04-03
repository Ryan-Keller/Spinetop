#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
echo "[start] dashboard api: read-only view over candidate promotion, dispatch/pending, collective, and honcho"
"$SCRIPT_DIR/../.venv_dashboard/bin/python" scripts/dashboard_api.py
