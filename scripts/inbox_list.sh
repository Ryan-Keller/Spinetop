#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "=== inbox ==="
ls -lt memory/inbox/*.json 2>/dev/null || echo "(no inbox json files)"

echo
echo "=== candidate promotion ==="
ls -lt memory/promotion/*.json 2>/dev/null || echo "(no candidate json files)"

echo
echo "=== collective memory ==="
ls -lt memory/collective/*.json 2>/dev/null || echo "(no collective json files)"
