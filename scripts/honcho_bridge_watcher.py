from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

ROOT = Path("/mnt/d/spine_desk/Spinetop")
COLLECTIVE = ROOT / "memory" / "collective"
STATE_DIR = ROOT / "logs" / "honcho_bridge"
STATE_DIR.mkdir(parents=True, exist_ok=True)
SEEN_FILE = STATE_DIR / "seen_collective_files.json"
EVENT_LOG = ROOT / "logs" / "topology" / "events.jsonl"

POLL_SECONDS = 5


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


def run_bridge() -> tuple[int, str]:
    proc = subprocess.run(
        ["python3", "scripts/honcho_bridge.py"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, output


def main() -> None:
    print(f"[honcho-bridge-watcher] watching {COLLECTIVE}")
    seen = load_seen()

    while True:
        current_files = sorted(COLLECTIVE.glob("*.json"))
        current_map = {}
        changed = False

        for path in current_files:
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                continue

            current_map[path.name] = mtime
            previous = seen.get(path.name)
            if previous is None or mtime > previous:
                changed = True

        if changed:
            code, out = run_bridge()
            if code == 0:
                log_event("honcho_bridge_watcher", "collective", "success", out[:500])
            else:
                log_event("honcho_bridge_watcher", "collective", "error", out[:500])

        seen = current_map
        save_seen(seen)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
