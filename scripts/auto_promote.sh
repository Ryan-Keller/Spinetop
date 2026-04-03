#!/usr/bin/env bash
set -euo pipefail

cd /mnt/d/spine_desk/Spinetop

shopt -s nullglob
files=(memory/inbox/*.json)

if [ ${#files[@]} -eq 0 ]; then
  echo "[auto-promote] no inbox files"
  exit 0
fi

for path in "${files[@]}"; do
  name="$(basename "$path")"

  if python3 - <<PY
import json, sys
from pathlib import Path
p = Path(r"$path")
data = json.loads(p.read_text(encoding="utf-8"))
sys.exit(0 if data.get("promotion_candidate") is True else 1)
PY
  then
    echo "[auto-promote] promoting $name"
    python3 scripts/promote_to_promotion.py "$name"
    python3 scripts/log_topology_event.py promote "$name" success

    echo "[auto-promote] approving $name"
    python3 scripts/approve_to_collective.py "$name"
    python3 scripts/log_topology_event.py approve "$name" success
  else
    echo "[auto-promote] skipping $name (promotion_candidate != true)"
    python3 scripts/log_topology_event.py promote "$name" skipped "promotion_candidate!=true"
  fi
done
