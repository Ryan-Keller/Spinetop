from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "memory" / "inbox"
QUARANTINE = ROOT / "memory" / "quarantine" / "malformed"
ARCHIVE = ROOT / "memory" / "archive" / "rejected"
EVENT_LOG = ROOT / "logs" / "topology" / "events.jsonl"

STALE_SECONDS = 15 * 60
POLL_SECONDS = 60


def log_event(status: str, record_name: str, detail: str) -> None:
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "machine": "Spinetop",
        "event_type": "hopper_clean",
        "record_name": record_name,
        "status": status,
        "detail": detail,
    }
    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def unique_target(dest_dir: Path, name: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / name
    if not target.exists():
        return target
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return dest_dir / f"{Path(name).stem}_{stamp}{Path(name).suffix}"


def move_file(path: Path, dest_dir: Path) -> Path:
    target = unique_target(dest_dir, path.name)
    path.replace(target)
    return target


def is_stale(path: Path, now_ts: float) -> bool:
    try:
        return (now_ts - path.stat().st_mtime) > STALE_SECONDS
    except FileNotFoundError:
        return False


def scan_once() -> int:
    if not INBOX.exists():
        return 0

    handled = 0
    now_ts = time.time()

    for path in sorted(INBOX.glob("*.json")):
        try:
            raw = path.read_text(encoding="utf-8")
            record = json.loads(raw)
        except Exception:
            move_file(path, QUARANTINE)
            log_event("quarantined", path.name, "malformed json")
            handled += 1
            continue

        promotion_candidate = record.get("promotion_candidate")
        if promotion_candidate is False and is_stale(path, now_ts):
            move_file(path, ARCHIVE)
            log_event("archived", path.name, "stale non-promotable inbox file")
            handled += 1

    return handled


def main() -> None:
    watch = "--watch" in __import__("sys").argv
    if watch:
        print(f"[hopper-clean] watching {INBOX}")
        while True:
            scan_once()
            time.sleep(POLL_SECONDS)
    else:
        scan_once()


if __name__ == "__main__":
    main()
