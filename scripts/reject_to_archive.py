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
        print("Usage: python scripts/reject_to_archive.py <inbox-or-candidate-json> [--reason REASON]", file=sys.stderr)
        return 1

    reason = None
    if "--reason" in sys.argv:
        idx = sys.argv.index("--reason")
        try:
            reason = sys.argv[idx + 1]
        except IndexError:
            print("ERROR: --reason requires a value", file=sys.stderr)
            return 1

    inbox = memory_dir("inbox")
    promotion = memory_dir("promotion")
    archive = memory_dir("archive")

    source = Path(sys.argv[1])
    if not source.is_absolute():
        inbox_candidate = (inbox / source).resolve()
        promotion_candidate = (promotion / source).resolve()
        if inbox_candidate.exists():
            source = inbox_candidate
        elif promotion_candidate.exists():
            source = promotion_candidate
        else:
            source = inbox_candidate

    if not source.exists():
        print(f"Missing file: {source}", file=sys.stderr)
        return 1

    try:
        if inbox in source.resolve().parents:
            ensure_in_dir(source, inbox)
        elif promotion in source.resolve().parents:
            ensure_in_dir(source, promotion)
        else:
            raise ValueError("File must be in memory/inbox or memory/promotion")
        data = validate_file(source)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    add_timestamp(data, "archive_timestamp")
    if reason:
        data["archive_reason"] = reason
    write_json(source, data)

    destination = safe_destination(source, archive)
    source.replace(destination)
    print(f"Archived: {source} -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
