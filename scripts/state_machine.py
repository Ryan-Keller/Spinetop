from __future__ import annotations

import re
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repo_paths import repo_root


ROOT = repo_root()
EXPEDITIONS_ACTIVE_DIR = ROOT / "expeditions" / "active"
MISSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
WORKING_MEMORY_FILENAME = "working_memory.json"

ALLOWED_TRANSITIONS = {
    "MISSION_DEFINED": ["CITADEL_ACTIVE"],
    "CITADEL_ACTIVE": ["CLARIFICATION_NEEDED", "RELEASE_REQUESTED", "PACKAGE_READY"],
    "CLARIFICATION_NEEDED": ["CITADEL_ACTIVE"],
    "RELEASE_REQUESTED": ["RELEASE_PREPARED"],
    "RELEASE_PREPARED": ["EXPEDITION_ACTIVE"],
    "EXPEDITION_ACTIVE": ["WAREHOUSE_INTAKE"],
    "WAREHOUSE_INTAKE": ["WAREHOUSE_PROCESSING"],
    "WAREHOUSE_PROCESSING": ["CITADEL_REVIEW_LOOP"],
    "CITADEL_REVIEW_LOOP": ["PACKAGE_READY", "RELEASE_REQUESTED", "CLARIFICATION_NEEDED"],
    "PACKAGE_READY": ["BRIDGE_CONSIDERATION", "MISSION_CLOSED"],
    "BRIDGE_CONSIDERATION": ["MISSION_CLOSED"],
    "MISSION_CLOSED": ["ARCHIVE_REVIEW"],
    "ARCHIVE_REVIEW": ["RECONSIDERATION_REQUESTED"],
    "RECONSIDERATION_REQUESTED": ["CITADEL_ACTIVE"],
}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_mission_id(mission_id: str) -> str:
    mission = str(mission_id).strip()
    if not mission:
        raise ValueError("mission_id must be a non-empty string")
    if not MISSION_ID_PATTERN.fullmatch(mission):
        raise ValueError("mission_id must contain only letters, numbers, dots, underscores, and hyphens")
    return mission


def validate_transition(current_state: str, next_state: str) -> bool:
    if next_state not in ALLOWED_TRANSITIONS.get(current_state, []):
        raise ValueError(f"Illegal transition: {current_state} -> {next_state}")
    return True


def mission_state_path(mission_id: str) -> Path:
    mission = normalize_mission_id(mission_id)
    return EXPEDITIONS_ACTIVE_DIR / mission / "state.json"


def mission_brief_path(mission_id: str) -> Path:
    mission = normalize_mission_id(mission_id)
    return EXPEDITIONS_ACTIVE_DIR / mission / "mission_brief.json"


def mission_manifest_path(mission_id: str) -> Path:
    mission = normalize_mission_id(mission_id)
    return EXPEDITIONS_ACTIVE_DIR / mission / "mission_manifest.json"


def working_memory_path(mission_id: str) -> Path:
    mission = normalize_mission_id(mission_id)
    return EXPEDITIONS_ACTIVE_DIR / mission / WORKING_MEMORY_FILENAME


def artifact_index_path(mission_id: str) -> Path:
    mission = normalize_mission_id(mission_id)
    return EXPEDITIONS_ACTIVE_DIR / mission / "artifact_index.json"


def read_state(mission_id: str) -> dict[str, Any]:
    path = mission_state_path(mission_id)
    if not path.exists():
        return {
            "mission_id": str(mission_id).strip(),
            "current_state": "MISSION_DEFINED",
            "updated_at": "",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "mission_id": str(mission_id).strip(),
            "current_state": "MISSION_DEFINED",
            "updated_at": "",
        }
    if not isinstance(payload, dict):
        return {
            "mission_id": str(mission_id).strip(),
            "current_state": "MISSION_DEFINED",
            "updated_at": "",
        }
    current_state = str(payload.get("current_state") or "MISSION_DEFINED").strip() or "MISSION_DEFINED"
    return {
        "mission_id": str(payload.get("mission_id") or mission_id).strip() or str(mission_id).strip(),
        "current_state": current_state,
        "updated_at": str(payload.get("updated_at") or ""),
    }


def write_state(mission_id: str, current_state: str) -> Path:
    mission = normalize_mission_id(mission_id)
    path = mission_state_path(mission)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mission_id": mission,
        "current_state": str(current_state).strip(),
        "updated_at": iso_now(),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    upsert_artifact_index_entry(mission, "state", path, created_at=payload["updated_at"])
    return path


def advance_state(mission_id: str, next_state: str, *, expected_current_state: str | None = None) -> tuple[str, str, Path]:
    mission = normalize_mission_id(mission_id)
    state = read_state(mission)
    current_state = str(expected_current_state or state.get("current_state") or "MISSION_DEFINED").strip() or "MISSION_DEFINED"
    next_state = str(next_state).strip()
    try:
        validate_transition(current_state, next_state)
    except ValueError:
        print("=== STATE GUARD BLOCKED ===")
        print(f"attempted_transition={current_state} -> {next_state}")
        print("reason=illegal_transition")
        raise

    path = write_state(mission, next_state)
    print("=== STATE TRANSITION ===")
    print(f"from={current_state}")
    print(f"to={next_state}")
    return current_state, next_state, path


def read_mission_brief(mission_id: str) -> dict[str, Any] | None:
    path = mission_brief_path(mission_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def read_working_memory(mission_id: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    path = working_memory_path(mission)
    if not path.exists():
        return {
            "mission_id": mission,
            "confirmed_facts": [],
            "active_assumptions": [],
            "open_questions": [],
            "deferred_questions": [],
            "latest_summary": "",
            "latest_confidence": 0.0,
            "confidence_reduction": 0.0,
            "last_operator_reply_at": "",
            "updated_at": "",
            "operating_status": "low_confidence_continue",
            "blocked_reason": "",
            "can_continue_without_input": True,
            "crew_status": "active",
            "crew_recalled": False,
            "expedition_activity": "running",
            "wake_hint": "",
            "parked_at": "",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("mission_id", mission)
    payload.setdefault("confirmed_facts", [])
    payload.setdefault("active_assumptions", [])
    payload.setdefault("open_questions", [])
    payload.setdefault("deferred_questions", [])
    payload.setdefault("latest_summary", "")
    payload.setdefault("latest_confidence", 0.0)
    payload.setdefault("confidence_reduction", 0.0)
    payload.setdefault("last_operator_reply_at", "")
    payload.setdefault("updated_at", "")
    payload.setdefault("operating_status", "low_confidence_continue")
    payload.setdefault("blocked_reason", "")
    payload.setdefault("can_continue_without_input", True)
    payload.setdefault("crew_status", "active")
    payload.setdefault("crew_recalled", False)
    payload.setdefault("expedition_activity", "running")
    payload.setdefault("wake_hint", "")
    payload.setdefault("parked_at", "")
    return payload


def write_working_memory(mission_id: str, payload: dict[str, Any]) -> Path:
    mission = normalize_mission_id(mission_id)
    path = working_memory_path(mission)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(payload)
    record["mission_id"] = mission
    if not str(record.get("updated_at") or "").strip():
        record["updated_at"] = iso_now()
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    upsert_artifact_index_entry(mission, "working_memory", path, created_at=str(record["updated_at"]))
    return path


def write_mission_brief(mission_id: str, task_text: str, mode: str, latest_run_id: str) -> Path:
    mission = normalize_mission_id(mission_id)
    path = mission_brief_path(mission)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_mission_brief(mission) or {}
    payload = {
        "mission_id": mission,
        "task_text": str(task_text).strip(),
        "mode": str(mode).strip(),
        "created_at": str(existing.get("created_at") or iso_now()),
        "latest_run_id": str(latest_run_id).strip(),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    upsert_artifact_index_entry(mission, "mission_brief", path, created_at=payload["created_at"])
    return path


def _artifact_index_item(kind: str, path: str, created_at: str) -> dict[str, str]:
    return {
        "kind": str(kind).strip(),
        "path": str(path).strip(),
        "created_at": str(created_at).strip(),
    }


def read_artifact_index(mission_id: str) -> dict[str, Any]:
    path = artifact_index_path(mission_id)
    if not path.exists():
        return {
            "mission_id": normalize_mission_id(mission_id),
            "items": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "mission_id": normalize_mission_id(mission_id),
            "items": [],
        }
    if not isinstance(payload, dict):
        return {
            "mission_id": normalize_mission_id(mission_id),
            "items": [],
        }
    items = payload.get("items")
    if not isinstance(items, list):
        items = []
    normalized_items: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        path_value = Path(str(item.get("path") or "").strip()).as_posix()
        created_at = str(item.get("created_at") or "").strip()
        if not kind or not path_value or not created_at:
            continue
        normalized_items.append(_artifact_index_item(kind, path_value, created_at))
    return {
        "mission_id": normalize_mission_id(str(payload.get("mission_id") or mission_id)),
        "items": normalized_items,
    }


def upsert_artifact_index_entry(mission_id: str, kind: str, artifact_path: Path | str, *, created_at: str | None = None) -> Path:
    mission = normalize_mission_id(mission_id)
    path = artifact_index_path(mission)
    path.parent.mkdir(parents=True, exist_ok=True)
    index = read_artifact_index(mission)
    item_path = Path(artifact_path)
    try:
        path_text = item_path.relative_to(ROOT).as_posix()
    except Exception:
        path_text = item_path.as_posix()
    item = _artifact_index_item(kind, path_text, created_at or iso_now())

    items = [
        existing
        for existing in index.get("items", [])
        if not (
            isinstance(existing, dict)
            and str(existing.get("kind") or "").strip() == item["kind"]
            and str(existing.get("path") or "").strip() == item["path"]
        )
    ]
    items.append(item)
    payload = {
        "mission_id": mission,
        "items": items,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
