from __future__ import annotations

import sys
from pathlib import Path

from memory_flow_utils import (
    add_timestamp,
    ensure_in_dir,
    memory_dir,
    resolve_in_dir,
    safe_destination,
    validate_file,
    write_json,
)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/approve_to_collective.py <promotion-json>", file=sys.stderr)
        return 1

    promotion = memory_dir("promotion")
    collective = memory_dir("collective")
    source = resolve_in_dir(sys.argv[1], promotion)

    if not source.exists():
        print(f"Missing file: {source}", file=sys.stderr)
        return 1

    try:
        ensure_in_dir(source, promotion)
        data = validate_file(source)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    add_timestamp(data, "approval_timestamp")
    write_json(source, data)

    destination = safe_destination(source, collective)
    source.replace(destination)
    print(f"Approved: {source} -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
