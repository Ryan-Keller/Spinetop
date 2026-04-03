from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG = ROOT / "logs" / "topology" / "events.jsonl"
DISPATCH_DIR = ROOT / "memory" / "dispatch"
STATUS_PATH = ROOT / "logs" / "nanny" / "item_world_status.json"

WINDOW_SECONDS = 300
ERROR_WINDOW_SECONDS = 600
BRIDGE_WINDOW_SECONDS = 600
DISPATCH_WINDOW_SECONDS = 900
POLL_SECONDS = 30

WARM_BURST = 20
HOT_BURST = 40
WARM_ERRORS = 4
HOT_ERRORS = 8
WARM_BRIDGE_RETRIES = 3
HOT_BRIDGE_RETRIES = 6
AGENT_DISPATCH_WARN = 3

COOLDOWN_COOL = 0
COOLDOWN_WARM = 15
COOLDOWN_HOT = 30


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def read_events() -> list[dict]:
    if not EVENT_LOG.exists():
        return []
    rows: list[dict] = []
    for line in EVENT_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def read_dispatch_records() -> list[dict]:
    records: list[dict] = []
    for folder in ("pending", "approved", "deferred", "rejected"):
        path = DISPATCH_DIR / folder
        if not path.exists():
            continue
        for file in path.glob("*.json"):
            try:
                payload = json.loads(file.read_text(encoding="utf-8"))
            except Exception:
                continue
            payload["petition_status"] = folder
            records.append(payload)
    return records


def log_nanny_event(status: str, detail: str) -> None:
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": iso_now(),
        "machine": "Spinetop",
        "event_type": "item_world_nanny",
        "record_name": "global",
        "status": status,
        "detail": detail,
    }
    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def compute_status() -> dict:
    now = datetime.now()
    events = read_events()
    dispatch_records = read_dispatch_records()

    honcho_events = [
        e for e in events
        if str(e.get("event_type", "")).startswith("honcho_")
        or e.get("event_type") in {"dispatch_petition", "item_world_nanny"}
    ]

    recent_events = [
        e for e in honcho_events
        if (parse_time(str(e.get("timestamp"))) or now) > now - timedelta(seconds=WINDOW_SECONDS)
    ]
    recent_errors = [
        e for e in honcho_events
        if (parse_time(str(e.get("timestamp"))) or now) > now - timedelta(seconds=ERROR_WINDOW_SECONDS)
        and str(e.get("status")) in {"error", "skipped", "timeout"}
    ]
    recent_bridge_errors = [
        e for e in honcho_events
        if str(e.get("event_type")) in {"honcho_bridge", "honcho_bridge_file", "honcho_bridge_watcher"}
        and (parse_time(str(e.get("timestamp"))) or now) > now - timedelta(seconds=BRIDGE_WINDOW_SECONDS)
        and str(e.get("status")) in {"error", "skipped"}
    ]

    dispatch_recent = [
        r for r in dispatch_records
        if (parse_time(str(r.get("timestamp_created"))) or now) > now - timedelta(seconds=DISPATCH_WINDOW_SECONDS)
    ]
    agent_counts: dict[str, int] = {}
    for record in dispatch_recent:
        agent = str(record.get("agent_id") or "unknown")
        agent_counts[agent] = agent_counts.get(agent, 0) + 1

    warnings = []
    for agent_id, count in agent_counts.items():
        if count >= AGENT_DISPATCH_WARN:
            warnings.append({
                "agent_id": agent_id,
                "reason": "too many requests",
            })

    burst_score = len(recent_events)
    error_score = len(recent_errors)
    bridge_retries = len(recent_bridge_errors)

    temperature = "cool"
    if burst_score >= HOT_BURST or error_score >= HOT_ERRORS or bridge_retries >= HOT_BRIDGE_RETRIES:
        temperature = "hot"
    elif burst_score >= WARM_BURST or error_score >= WARM_ERRORS or bridge_retries >= WARM_BRIDGE_RETRIES:
        temperature = "warm"
    elif warnings:
        temperature = "warm"

    recommended_actions: list[str] = []
    if temperature in {"warm", "hot"}:
        recommended_actions.append("slow dispatch intake")
        recommended_actions.append("prefer deferred review")
    if bridge_retries >= WARM_BRIDGE_RETRIES:
        recommended_actions.append("pause bridge retries")

    if temperature == "hot":
        global_cooldown = COOLDOWN_HOT
    elif temperature == "warm":
        global_cooldown = COOLDOWN_WARM
    else:
        global_cooldown = COOLDOWN_COOL

    return {
        "ok": True,
        "temperature": temperature,
        "burst_score": burst_score,
        "error_score": error_score,
        "active_agent_warnings": warnings,
        "recommended_actions": sorted(set(recommended_actions)),
        "global_cooldown_seconds": global_cooldown,
    }


def maybe_log_event(status: dict) -> None:
    previous = None
    if STATUS_PATH.exists():
        try:
            previous = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            previous = None

    changed = True
    if previous:
        changed = (
            previous.get("temperature") != status.get("temperature")
            or previous.get("active_agent_warnings") != status.get("active_agent_warnings")
            or previous.get("recommended_actions") != status.get("recommended_actions")
        )

    if changed:
        detail = (
            f"burst={status['burst_score']} error={status['error_score']} "
            f"cooldown={status['global_cooldown_seconds']}s"
        )
        if status["recommended_actions"]:
            detail += f"; actions={','.join(status['recommended_actions'])}"
        log_nanny_event(status["temperature"], detail)


def write_status(status: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


def run_once() -> None:
    status = compute_status()
    maybe_log_event(status)
    write_status(status)


def main() -> None:
    watch = "--watch" in __import__("sys").argv
    if watch:
        while True:
            run_once()
            time.sleep(POLL_SECONDS)
    else:
        run_once()


if __name__ == "__main__":
    main()
