from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from governance_utils import read_nanny_state, read_return_all_state, should_require_operator_review
from repo_paths import repo_root


ROOT = repo_root()
RETURN_ALL_FILE = ROOT / "logs" / "governance" / "return_all.json"
NANNY_STATUS = ROOT / "logs" / "nanny" / "item_world_status.json"
EVENT_LOG = ROOT / "logs" / "topology" / "events.jsonl"
RESUME_QUEUE_PATH = ROOT / "logs" / "custodial" / "resume_queue.json"
LAST_KNOWN_ROLE_PATH = ROOT / "logs" / "custodial" / "last_known_role.json"
DECISION_PATH = ROOT / "logs" / "custodial" / "bootstrap_decision.json"

FRESHNESS_MINUTES = 15
MAINTENANCE_ENTRY_CLASSES = {"self_heal", "repair"}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def read_return_all() -> bool:
    return bool(read_return_all_state().get("enabled", False))


def read_nanny() -> tuple[str, int]:
    data = read_nanny_state()
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


def read_last_known_role() -> dict[str, Any]:
    return load_json(LAST_KNOWN_ROLE_PATH) or {}


def read_resume_queue() -> list[dict[str, Any]]:
    payload = load_json(RESUME_QUEUE_PATH)
    if not payload:
        return []
    actions = payload.get("actions")
    if isinstance(actions, list):
        return [item for item in actions if isinstance(item, dict)]
    if isinstance(payload.get("action"), dict):
        return [payload["action"]]
    return []


def queue_action_is_fresh(action: dict[str, Any], now: datetime) -> bool:
    timestamp = parse_iso(str(action.get("queued_at") or action.get("created_at") or ""))
    if not timestamp:
        return False
    return now - timestamp <= timedelta(minutes=FRESHNESS_MINUTES)


def is_custodial_lane_action(action: dict[str, Any], role_context: dict[str, Any]) -> bool:
    lane = str(action.get("lane") or role_context.get("lane") or "").strip()
    role = str(action.get("role") or role_context.get("role") or "").strip()
    entry_class = str(action.get("entry_class") or "").strip()
    return (
        lane == "custodial_maintenance"
        or role == "custodial"
        or entry_class in MAINTENANCE_ENTRY_CLASSES
    )


def find_bridge_issue(events: list[dict]) -> bool:
    for event in reversed(events):
        if event.get("event_type") == "honcho_bridge_watcher":
            status = str(event.get("status") or "")
            if status in {"error", "partial", "paused"}:
                return True
            break
    return False


def find_clear_maintenance_action(
    role_context: dict[str, Any],
    now: datetime,
) -> tuple[dict[str, Any] | None, str]:
    actions = read_resume_queue()
    if not actions:
        return None, "no queued maintenance action"

    fresh_actions = [action for action in actions if queue_action_is_fresh(action, now)]
    if len(fresh_actions) != len(actions):
        return None, "stale queued maintenance action"

    custodial_actions = [action for action in fresh_actions if is_custodial_lane_action(action, role_context)]
    if len(custodial_actions) == 1:
        return custodial_actions[0], str(custodial_actions[0].get("action_id") or custodial_actions[0].get("task") or "queued maintenance action")
    if len(custodial_actions) > 1:
        return None, "multiple queued maintenance actions"
    return None, "queued actions not in custodial lane"


def decide() -> dict:
    return_all_state = read_return_all_state()
    nanny_state = read_nanny_state()
    return_all = bool(return_all_state.get("enabled", False))
    temperature = str(nanny_state.get("temperature") or "cool")
    cooldown = int(nanny_state.get("global_cooldown_seconds") or 0)
    events = recent_events()
    role_context = read_last_known_role()
    now = datetime.now(timezone.utc)

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

    action, detail = find_clear_maintenance_action(role_context, now)
    if action:
        return {
            "decision": "resume_repair",
            "reason": f"single queued maintenance action: {detail}",
            "inputs": {
                "return_all_enabled": False,
                "temperature": temperature,
                "global_cooldown_seconds": cooldown,
                "queued_action": detail,
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
                "queued_action": detail,
            },
        }

    if should_require_operator_review(return_all=return_all_state, nanny=nanny_state):
        return {
            "decision": "request_operator_review",
            "reason": detail if detail != "no queued maintenance action" else "ambiguous state or multiple competing actions",
            "inputs": {
                "return_all_enabled": False,
                "temperature": temperature,
                "global_cooldown_seconds": cooldown,
                "queued_action": detail,
            },
        }

    return {
        "decision": "request_operator_review",
        "reason": detail if detail != "no queued maintenance action" else "ambiguous state or multiple competing actions",
        "inputs": {
            "return_all_enabled": False,
            "temperature": temperature,
            "global_cooldown_seconds": cooldown,
            "queued_action": detail,
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
