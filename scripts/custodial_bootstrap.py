from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETURN_ALL_FILE = ROOT / "logs" / "governance" / "return_all.json"
NANNY_STATUS = ROOT / "logs" / "nanny" / "item_world_status.json"
EVENT_LOG = ROOT / "logs" / "topology" / "events.jsonl"
DISPATCH_DIR = ROOT / "memory" / "dispatch"
DECISION_PATH = ROOT / "logs" / "custodial" / "bootstrap_decision.json"

POLL_SECONDS = 30


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_return_all() -> bool:
    data = load_json(RETURN_ALL_FILE)
    if not data:
        return False
    return bool(data.get("enabled", False))


def read_nanny() -> tuple[str, int]:
    data = load_json(NANNY_STATUS) or {}
    temperature = str(data.get("temperature") or "cool")
    cooldown = int(data.get("global_cooldown_seconds") or 0)
    return temperature, cooldown


def recent_events(limit: int = 200) -> list[dict]:
    if not EVENT_LOG.exists():
        return []
    rows = []
    for line in EVENT_LOG.read_text(encoding="utf-8").splitlines()[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def find_bridge_issue(events: list[dict]) -> bool:
    for event in reversed(events):
        if event.get("event_type") == "honcho_bridge_watcher":
            status = str(event.get("status") or "")
            if status in {"error", "partial", "paused"}:
                return True
            break
    return False


def find_clear_maintenance_action() -> tuple[bool, str]:
    pending = DISPATCH_DIR / "pending"
    if not pending.exists():
        return False, "no pending dispatch folder"
    petitions = []
    for path in pending.glob("*.json"):
        payload = load_json(path)
        if not payload:
            continue
        entry_class = str(payload.get("entry_class") or "normal")
        if entry_class not in {"self_heal", "repair"}:
            continue
        petitions.append(path.name)
    if len(petitions) == 1:
        return True, petitions[0]
    if len(petitions) > 1:
        return False, "multiple maintenance petitions"
    return False, "no maintenance petitions"


def decide() -> dict:
    return_all = read_return_all()
    temperature, cooldown = read_nanny()
    events = recent_events()

    if return_all:
        return {
            "decision": "hold_due_to_recall",
            "reason": "return_all enabled",
            "inputs": {
                "return_all_enabled": True,
                "temperature": temperature,
                "global_cooldown_seconds": cooldown,
            },
        }

    if temperature == "hot" or cooldown > 0:
        return {
            "decision": "wait_for_cooldown",
            "reason": "nanny hot or cooldown active",
            "inputs": {
                "return_all_enabled": False,
                "temperature": temperature,
                "global_cooldown_seconds": cooldown,
            },
        }

    has_action, detail = find_clear_maintenance_action()
    if has_action:
        return {
            "decision": "resume_repair",
            "reason": f"single maintenance petition: {detail}",
            "inputs": {
                "return_all_enabled": False,
                "temperature": temperature,
                "global_cooldown_seconds": cooldown,
            },
        }

    if find_bridge_issue(events) and temperature == "cool":
        return {
            "decision": "resume_bridge_watch",
            "reason": "bridge paused or failing and system cool",
            "inputs": {
                "return_all_enabled": False,
                "temperature": temperature,
                "global_cooldown_seconds": cooldown,
            },
        }

    return {
        "decision": "request_operator_review",
        "reason": "ambiguous state or multiple competing actions",
        "inputs": {
            "return_all_enabled": False,
            "temperature": temperature,
            "global_cooldown_seconds": cooldown,
        },
    }


def write_decision(decision: dict) -> dict:
    payload = {
        "ok": True,
        "timestamp": iso_now(),
        **decision,
    }
    DECISION_PATH.parent.mkdir(parents=True, exist_ok=True)
    DECISION_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    decision = decide()
    payload = write_decision(decision)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
