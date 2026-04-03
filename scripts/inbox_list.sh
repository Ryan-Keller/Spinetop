#!/usr/bin/env bash
set -euo pipefail

cd /mnt/d/spine_desk/Spinetop

echo "=== inbox ==="
ls -lt memory/inbox/*.json 2>/dev/null || echo "(no inbox json files)"

echo
echo "=== promotion ==="
ls -lt memory/promotion/*.json 2>/dev/null || echo "(no promotion json files)"

echo
echo "=== collective ==="
ls -lt memory/collective/*.json 2>/dev/null || echo "(no collective json files)"
