from __future__ import annotations

import sys
from pathlib import Path

from memory_flow_utils import memory_dir, validate_file


def iter_json_files(target: Path):
    if target.is_dir():
        for path in sorted(target.glob("*.json")):
            yield path
    else:
        yield target


def main() -> int:
    inbox = memory_dir("inbox")
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else inbox

    if not target.exists():
        print(f"Missing file or directory: {target}", file=sys.stderr)
        return 1

    errors = 0
    checked = 0

    for path in iter_json_files(target):
        checked += 1
        try:
            validate_file(path)
            print(f"OK: {path}")
        except Exception as exc:
            errors += 1
            print(f"ERROR: {exc}", file=sys.stderr)

    if checked == 0:
        print(f"No JSON files found in {target}", file=sys.stderr)
        return 1

    if errors:
        print(f"Validation failed: {errors} error(s)", file=sys.stderr)
        return 1

    print(f"Validation passed: {checked} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
