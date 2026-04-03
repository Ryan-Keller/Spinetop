from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

from governance_utils import can_bridge_to_honcho, read_nanny_state, read_return_all_state
from repo_paths import repo_root


ROOT = repo_root()
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


def run_bridge_file(path: Path) -> tuple[int, str]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return 1, f"invalid json: {exc}"

    gate = can_bridge_to_honcho(
        record,
        return_all=read_return_all_state(),
        nanny=read_nanny_state(),
    )
    if not gate.allowed:
        return 1, f"preflight deferred: {gate.reason}"

    proc = subprocess.run(
        ["python3", "scripts/honcho_bridge.py", str(path)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, output


def main() -> None:
    print(f"[honcho-bridge-watcher] watching {COLLECTIVE}")
    seen = load_seen()
    paused_logged = False

    while True:
        return_all = read_return_all_state()
        nanny = read_nanny_state()
        paused_reason = ""
        if return_all.get("enabled"):
            paused_reason = "return_all active"
        elif nanny.get("temperature") in {"warm", "hot"} or int(nanny.get("global_cooldown_seconds") or 0) > 0:
            paused_reason = f"nanny {nanny.get('temperature', 'cool')} or cooldown {nanny.get('global_cooldown_seconds', 0)}s active"

        if paused_reason:
            if not paused_logged:
                log_event("honcho_bridge_watcher", "collective", "paused", paused_reason)
                paused_logged = True
            time.sleep(POLL_SECONDS)
            continue

        paused_logged = False
        current_files = sorted(COLLECTIVE.glob("*.json"))
        next_seen: dict[str, float] = {}
        changed_files: list[tuple[Path, float]] = []

        for path in current_files:
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                continue

            previous = seen.get(path.name)
            if previous is not None:
                next_seen[path.name] = previous
            if previous is None or mtime > previous:
                changed_files.append((path, mtime))

        if changed_files:
            processed_count = 0
            success_count = 0
            error_count = 0

            for path, mtime in changed_files:
                processed_count += 1
                started = time.monotonic()
                code, out = run_bridge_file(path)
                duration_ms = int((time.monotonic() - started) * 1000)
                if code == 0:
                    success_count += 1
                    next_seen[path.name] = mtime
                    detail = out[:500] if out else "mirrored to honcho"
                    detail = f"{detail} duration_ms={duration_ms}"
                    log_event("honcho_bridge_file", path.name, "success", detail)
                else:
                    error_count += 1
                    detail = out[:500] if out else "bridge error"
                    detail = f"{detail} duration_ms={duration_ms}"
                    log_event("honcho_bridge_file", path.name, "error", detail)

            if processed_count > 0:
                if error_count == 0:
                    summary_status = "success"
                elif success_count == 0:
                    summary_status = "error"
                else:
                    summary_status = "partial"
                summary_detail = (
                    f"processed={processed_count} success={success_count} error={error_count}"
                )
                log_event("honcho_bridge_watcher", "collective", summary_status, summary_detail)

        if not changed_files:
            for path in current_files:
                previous = seen.get(path.name)
                if previous is not None:
                    next_seen[path.name] = previous

        seen = next_seen
        save_seen(next_seen)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
