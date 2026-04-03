#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: inbox_show.sh <filename.json>"
  exit 1
fi

cd /mnt/d/spine_desk/Spinetop

name="$1"

for dir in memory/inbox memory/promotion memory/collective; do
  if [ -f "$dir/$name" ]; then
    echo "=== $dir/$name ==="
    sed -n '1,220p' "$dir/$name"
    exit 0
  fi
done

echo "File not found: $name"
exit 1
