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
        print("Usage: python scripts/promote_to_promotion.py <inbox-json>", file=sys.stderr)
        return 1

    inbox = memory_dir("inbox")
    promotion = memory_dir("promotion")
    source = resolve_in_dir(sys.argv[1], inbox)

    if not source.exists():
        print(f"Missing file: {source}", file=sys.stderr)
        return 1

    try:
        ensure_in_dir(source, inbox)
        data = validate_file(source)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if data.get("promotion_candidate") is not True:
        print(f"ERROR: promotion_candidate must be true to promote: {source}", file=sys.stderr)
        return 1

    add_timestamp(data, "promotion_timestamp")
    write_json(source, data)

    destination = safe_destination(source, promotion)
    source.replace(destination)
    print(f"Promoted: {source} -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
