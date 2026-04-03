from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

from repo_paths import repo_root


ROOT = repo_root()
INBOX = ROOT / "memory" / "inbox"
STATE_DIR = ROOT / "logs" / "watcher"
STATE_DIR.mkdir(parents=True, exist_ok=True)
SEEN_FILE = STATE_DIR / "seen_files.json"
EVENT_LOG = ROOT / "logs" / "topology" / "events.jsonl"

POLL_SECONDS = 3


def load_seen() -> dict[str, float]:
    if not SEEN_FILE.exists():
        return {}
    try:
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_seen(seen: dict[str, float]) -> None:
    SEEN_FILE.write_text(json.dumps(seen, indent=2), encoding="utf-8")


def log_event(event_type: str, record_name: str, status: str, detail: str = "") -> None:
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "machine": "Spinetop",
        "event_type": event_type,
        "record_name": record_name,
        "status": status,
        "detail": detail,
    }
    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def is_promotable(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("promotion_candidate") is True


def run_cmd(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(ROOT))
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def process_file(path: Path) -> None:
    name = path.name

    try:
        if not is_promotable(path):
            log_event("watcher_scan", name, "skipped", "promotion_candidate!=true")
            return

        log_event("watcher_scan", name, "promotable", "starting candidate promotion flow")

        code, out = run_cmd(["python3", "scripts/promote_to_promotion.py", name])
        if code != 0:
            log_event("promote", name, "error", out[:500])
            return
        log_event("promote", name, "success", out[:500])

    except Exception as exc:
        log_event("watcher_scan", name, "error", str(exc)[:500])


def main() -> None:
    print(f"[watcher] watching {INBOX}")
    seen = load_seen()

    while True:
        current_files = sorted(INBOX.glob("*.json"))
        current_map = {}

        for path in current_files:
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                continue

            current_map[path.name] = mtime
            previous = seen.get(path.name)

            if previous is None or mtime > previous:
                process_file(path)

        seen = current_map
        save_seen(seen)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
