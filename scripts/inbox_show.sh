#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: inbox_show.sh <filename.json>"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

name="$1"

for dir in memory/inbox memory/promotion memory/collective; do
  if [ -f "$dir/$name" ]; then
    case "$dir" in
      memory/inbox) label="inbox" ;;
      memory/promotion) label="candidate promotion" ;;
      memory/collective) label="collective memory" ;;
      *) label="$dir" ;;
    esac
    echo "=== $label: $dir/$name ==="
    sed -n '1,220p' "$dir/$name"
    exit 0
  fi
done

echo "File not found: $name"
exit 1
