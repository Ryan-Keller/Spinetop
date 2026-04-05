from __future__ import annotations

import hashlib
import json
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from flask import Flask, jsonify, request

from validate_clarification_packet import validate_clarification_packet
from state_machine import (
    mission_brief_path,
    mission_manifest_path,
    normalize_mission_id,
    read_artifact_index,
    read_mission_brief,
    read_state,
    upsert_artifact_index_entry,
    write_state,
)
from governance_utils import can_bridge_to_honcho, read_nanny_state
from review_and_submit_petition import build_review_payload, validate_draft_petition
from run_hermes_v1 import validate_response_object

ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG = ROOT / "logs" / "topology" / "events.jsonl"
HERMES_RUNS_DIR = ROOT / "logs" / "hermes" / "runs"
CLARIFICATION_PACKETS_DIR = ROOT / "logs" / "citadel" / "clarification_packets"
EXPEDITIONS_ACTIVE_DIR = ROOT / "expeditions" / "active"
WORKBENCH_MISSIONS_DIR = ROOT / "workbench" / "missions"
MISSION_CHAT_FILENAME = "chat.jsonl"
MEMORY_DIR = ROOT / "memory"
DISPATCH_DIR = MEMORY_DIR / "dispatch"
GOVERNANCE_DIR = ROOT / "logs" / "governance"
SUPPORT_ORCHESTRATION_DIR = ROOT / "logs" / "support" / "orchestration"
SUPPORT_RETRIEVAL_DIR = ROOT / "logs" / "support" / "retrieval"
SUPPORT_ORCHESTRATION_INSTANCES_DIR = SUPPORT_ORCHESTRATION_DIR / "instances"
SUPPORT_RETRIEVAL_INSTANCES_DIR = SUPPORT_RETRIEVAL_DIR / "instances"
COMPACTOR_LOG_DIR = ROOT / "logs" / "compactor"
ARCHIVE_DIR = MEMORY_DIR / "archive"
COMPACTED_DIR = MEMORY_DIR / "compacted"
PROMOTION_DIR = MEMORY_DIR / "promotion"
INBOX_DIR = MEMORY_DIR / "inbox"
HONCHO_BASE = "http://127.0.0.1:8000"
WORKSPACE_ID = "shared-coordination"
IN_MEMORY_EVENTS: list[dict[str, Any]] = []
IN_MEMORY_EVENTS_MAX = 200
MIRROR_DOOR_CACHE: dict[str, Any] = {"signature": "", "value": None}

KNOWN_PEERS = [
    {"id": "desktop", "metadata": {"created_by": "system"}},
    {"id": "laptop", "metadata": {"created_by": "system"}},
]

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    allowed_origins = {
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    }
    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_event(raw: dict[str, Any]) -> dict[str, Any]:
    allowed_types = {
        "hermes_write",
        "watcher_scan",
        "promote",
        "approve",
        "honcho_bridge",
        "hopper_clean",
        "honcho_bridge_file",
        "honcho_bridge_watcher",
        "dispatch_petition",
        "item_world_nanny",
    }
    allowed_statuses = {
        "created",
        "promotable",
        "success",
        "error",
        "skipped",
        "partial",
        "archived",
        "quarantined",
        "pending",
        "approved",
        "deferred",
        "rejected",
        "cool",
        "warm",
        "hot",
        "paused",
    }
    raw_type = raw.get("event_type") or "watcher_scan"
    raw_status = raw.get("status") or "created"
    return {
        "timestamp": str(raw.get("timestamp") or iso_now()),
        "event_type": raw_type if raw_type in allowed_types else "watcher_scan",
        "record_name": str(raw.get("record_name") or "unknown"),
        "status": raw_status if raw_status in allowed_statuses else "created",
        "detail": str(raw.get("detail") or ""),
        "machine": str(raw.get("machine") or "local"),
    }


def read_recent_events(limit: int = 50) -> list[dict]:
    rows: list[dict] = []
    if EVENT_LOG.exists():
        lines = EVENT_LOG.read_text(encoding="utf-8").splitlines()
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    if IN_MEMORY_EVENTS:
        rows.extend(IN_MEMORY_EVENTS[-limit:])
    if not rows and MEMORY_DIR.exists():
        # Minimal fallback: surface memory directory presence as a scan event
        rows.append({
            "timestamp": iso_now(),
            "event_type": "watcher_scan",
            "record_name": "memory_dir",
            "status": "success",
            "detail": f"memory files: {len(list(MEMORY_DIR.glob('*')))}",
            "machine": "local",
        })
    normalized = [normalize_event(row) for row in rows]
    return normalized[-limit:]


def honcho_post(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        HONCHO_BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def safe_honcho_post(path: str, payload: dict) -> dict:
    try:
        return honcho_post(path, payload)
    except Exception as e:
        return {"error": str(e)}


def normalize_session(raw: dict[str, Any]) -> dict[str, Any]:
    meta = raw.get("metadata") or {}
    return {
        "id": str(raw.get("id") or "unknown"),
        "is_active": bool(raw.get("is_active", False)),
        "metadata": {
            "agent_id": str(meta.get("agent_id") or "unknown"),
            "workspace": str(meta.get("workspace") or WORKSPACE_ID),
        },
        "created_at": str(raw.get("created_at") or iso_now()),
    }


def normalize_peer(raw: dict[str, Any]) -> dict[str, Any]:
    meta = raw.get("metadata") or {}
    return {
        "id": str(raw.get("id") or "unknown"),
        "metadata": {
            "created_by": str(meta.get("created_by") or "system"),
        },
    }


def get_sessions(limit: int = 10) -> tuple[int, list[dict]]:
    sessions = safe_honcho_post(f"/v3/workspaces/{WORKSPACE_ID}/sessions/list", {})
    items = sessions.get("items") if isinstance(sessions, dict) else None
    if isinstance(items, list) and items:
        normalized = [normalize_session(row) for row in items[:limit]]
        total = sessions.get("total", len(items))
        return int(total or 0), normalized
    return 0, []


def get_peers(limit: int = 10) -> tuple[int, list[dict]]:
    peers = safe_honcho_post(f"/v3/workspaces/{WORKSPACE_ID}/peers/list", {})
    items = peers.get("items") if isinstance(peers, dict) else None
    if isinstance(items, list) and items:
        normalized = [normalize_peer(row) for row in items[:limit]]
        total = peers.get("total", len(items))
        return int(total or 0), normalized
    normalized = [normalize_peer(row) for row in KNOWN_PEERS[:limit]]
    return len(normalized), normalized


def get_events(limit: int = 50) -> list[dict]:
    return read_recent_events(limit)


def log_topology_event(event_type: str, record_name: str, status: str, detail: str) -> None:
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": iso_now(),
        "machine": "Spinetop",
        "event_type": event_type,
        "record_name": record_name,
        "status": status,
        "detail": detail,
    }
    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _short_digest(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _mission_root(mission_id: str) -> Path:
    return EXPEDITIONS_ACTIVE_DIR / normalize_mission_id(mission_id)


def _workbench_root(mission_id: str) -> Path:
    return WORKBENCH_MISSIONS_DIR / normalize_mission_id(mission_id)


def _ensure_workbench_structure(mission_id: str) -> Path:
    root = _workbench_root(mission_id)
    for folder in ["intake", "scratch", "code", "test_runs", "notes", "outputs"]:
        (root / folder).mkdir(parents=True, exist_ok=True)
    return root


def _mission_chat_path(mission_id: str) -> Path:
    return _ensure_workbench_structure(mission_id) / "notes" / MISSION_CHAT_FILENAME


def _mission_manifest_payload(mission_id: str) -> dict[str, Any] | None:
    path = mission_manifest_path(mission_id)
    if not path.exists():
        return None
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else None


def _latest_mtime(paths: list[Path]) -> str:
    latest: float | None = None
    for path in paths:
        if not path.exists():
            continue
        try:
            mtime = path.stat().st_mtime
        except Exception:
            continue
        if latest is None or mtime > latest:
            latest = mtime
    if latest is None:
        return ""
    return datetime.fromtimestamp(latest, tz=timezone.utc).isoformat()


def _latest_index_item(index_items: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    for item in reversed(index_items):
        if str(item.get("kind") or "").strip() == kind:
            return item
    return None


def _relative_or_absolute(path: Path | str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return (ROOT / candidate).resolve()


def _load_index_artifact(mission_id: str, kind: str) -> dict[str, Any] | None:
    index = read_artifact_index(mission_id)
    item = _latest_index_item(list(index.get("items") or []), kind)
    if not item:
        return None
    path_text = str(item.get("path") or "").strip()
    if not path_text:
        return None
    path = _relative_or_absolute(path_text)
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else None


def _workbench_files(mission_id: str) -> list[dict[str, Any]]:
    root = _workbench_root(mission_id)
    if not root.exists():
        return []
    files: list[dict[str, Any]] = []
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            stat = path.stat()
        except Exception:
            continue
        rel = path.relative_to(root)
        folder = rel.parts[0] if rel.parts else "root"
        files.append({
            "path": path.relative_to(ROOT).as_posix(),
            "folder": folder,
            "name": path.name,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "bytes": stat.st_size,
            "bytes_label": _format_bytes(stat.st_size),
        })
    return files[:200]


def _mission_inputs(mission_id: str) -> list[dict[str, Any]]:
    intake_dir = _workbench_root(mission_id) / "intake"
    if not intake_dir.exists():
        return []
    inputs: list[dict[str, Any]] = []
    for path in sorted((p for p in intake_dir.glob("*.json") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True):
        payload = _load_json(path)
        if not isinstance(payload, dict):
            continue
        inputs.append({
            "input_id": str(payload.get("input_id") or path.stem),
            "mission_id": str(payload.get("mission_id") or mission_id),
            "source_type": str(payload.get("source_type") or "user_provided"),
            "status": str(payload.get("status") or "unreviewed"),
            "content": str(payload.get("content") or ""),
            "created_at": str(payload.get("created_at") or ""),
            "path": path.relative_to(ROOT).as_posix(),
        })
    return inputs[:200]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _mission_chat_messages(mission_id: str) -> list[dict[str, Any]]:
    path = _mission_chat_path(mission_id)
    rows = _read_jsonl(path)
    messages: list[dict[str, Any]] = []
    for row in rows[-200:]:
        messages.append({
            "message_id": str(row.get("message_id") or ""),
            "mission_id": str(row.get("mission_id") or mission_id),
            "sender": str(row.get("sender") or "user"),
            "role": str(row.get("role") or "user"),
            "message": str(row.get("message") or ""),
            "tone": str(row.get("tone") or "info"),
            "created_at": str(row.get("created_at") or ""),
            "kind": str(row.get("kind") or "message"),
        })
    return messages


def _chat_reply(message: str, quick_reply: str | None, state: str, mission_summary: str) -> dict[str, str]:
    quick = str(quick_reply or "").strip().lower()
    if quick in {"yes", "affirmative"}:
        return {
            "role": "assistant",
            "tone": "good",
            "message": "Acknowledged. I'll keep the mission moving and wait for the next instruction.",
        }
    if quick in {"no", "negative"}:
        return {
            "role": "assistant",
            "tone": "watch",
            "message": "Understood. I'll hold this mission steady and avoid making assumptions.",
        }
    if quick in {"write more information", "more info", "more information"}:
        return {
            "role": "assistant",
            "tone": "watch",
            "message": "Please add the missing context. Helpful details are objective, scope, constraints, links, and desired outcome.",
        }
    if "?" in message or state in {"CLARIFICATION_NEEDED", "RECONSIDERATION_REQUESTED"}:
        return {
            "role": "assistant",
            "tone": "watch",
            "message": mission_summary or "I need a bit more detail before I can move this mission forward.",
        }
    return {
        "role": "assistant",
        "tone": "good",
        "message": "Received. I've recorded this in the mission chat and intake lanes for review.",
    }


def _append_chat_exchange(mission_id: str, message: str, *, quick_reply: str | None = None) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    detail = _build_expedition_detail(mission)
    path = _mission_chat_path(mission)
    user_item = {
        "message_id": f"chat_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{_short_digest(f'{mission}|user|{message}')}",
        "mission_id": mission,
        "sender": "user",
        "role": "user",
        "message": message,
        "tone": "info",
        "created_at": iso_now(),
        "kind": "message",
    }
    assistant = _chat_reply(message, quick_reply, str(detail.get("current_state") or ""), str(detail.get("summary") or ""))
    assistant_digest_seed = f"{mission}|assistant|{assistant['message']}"
    assistant_item = {
        "message_id": f"chat_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{_short_digest(assistant_digest_seed)}",
        "mission_id": mission,
        "sender": assistant["role"],
        "role": assistant["role"],
        "message": assistant["message"],
        "tone": assistant["tone"],
        "created_at": iso_now(),
        "kind": "reply",
    }
    _append_jsonl(path, user_item)
    _append_jsonl(path, assistant_item)
    return {
        "messages": [user_item, assistant_item],
        "path": path.relative_to(ROOT).as_posix(),
        "summary": detail.get("summary") or "",
    }


def _mission_status_badge(current_state: str, manifest_status: str, latest_run_id: str, input_count: int) -> str:
    if current_state in {"MISSION_CLOSED", "ARCHIVE_REVIEW"}:
        return "idle"
    if current_state in {"PACKAGE_READY", "BRIDGE_CONSIDERATION"} or manifest_status in {"ready_for_review"}:
        return "ready_for_review"
    if current_state in {
        "CITADEL_ACTIVE",
        "RELEASE_REQUESTED",
        "RELEASE_PREPARED",
        "EXPEDITION_ACTIVE",
        "WAREHOUSE_INTAKE",
        "WAREHOUSE_PROCESSING",
        "CITADEL_REVIEW_LOOP",
    }:
        return "researching"
    if current_state in {"CLARIFICATION_NEEDED", "MISSION_DEFINED", "RECONSIDERATION_REQUESTED"}:
        return "waiting_for_user"
    if not latest_run_id and input_count == 0:
        return "waiting_for_user"
    return "researching"


def _latest_run_summary(mission_id: str) -> dict[str, Any] | None:
    payload = _load_index_artifact(mission_id, "hermes_run")
    if not isinstance(payload, dict):
        return None
    return payload


def _latest_draft_summary(mission_id: str) -> dict[str, Any] | None:
    payload = _load_index_artifact(mission_id, "draft")
    if not isinstance(payload, dict):
        return None
    return payload


def _latest_clarification_summary(mission_id: str) -> dict[str, Any] | None:
    payload = _load_index_artifact(mission_id, "clarification_packet")
    if not isinstance(payload, dict):
        return None
    return payload


def _build_expedition_detail(mission_id: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    mission_dir = _mission_root(mission)
    brief = read_mission_brief(mission) or {}
    state = read_state(mission)
    manifest = _mission_manifest_payload(mission)
    artifact_index = read_artifact_index(mission)
    artifact_items = list(artifact_index.get("items") or [])
    latest_run_id = str(brief.get("latest_run_id") or (manifest or {}).get("run_id") or "").strip()
    current_state = str(state.get("current_state") or "MISSION_DEFINED").strip() or "MISSION_DEFINED"
    objective = str(brief.get("objective") or brief.get("task_text") or "").strip()
    mission_inputs = _mission_inputs(mission)
    mission_chat = _mission_chat_messages(mission)
    workbench_files = _workbench_files(mission)
    workbench_folders = []
    for folder_name in ["intake", "scratch", "code", "test_runs", "notes", "outputs"]:
        folder_path = _workbench_root(mission) / folder_name
        folder_files = [item for item in workbench_files if item.get("folder") == folder_name]
        newest_modified_at = ""
        if folder_files:
            newest_modified_at = max(str(item.get("modified_at") or "") for item in folder_files)
        workbench_folders.append({
            "name": folder_name,
            "path": folder_path.relative_to(ROOT).as_posix(),
            "available": folder_path.exists(),
            "file_count": len(folder_files),
            "newest_modified_at": newest_modified_at,
        })
    manifest_status = str((manifest or {}).get("status") or "").strip()
    status_badge = _mission_status_badge(current_state, manifest_status, latest_run_id, len(mission_inputs))
    last_updated = _latest_mtime([
        mission_dir / "state.json",
        mission_dir / "mission_brief.json",
        mission_dir / "artifact_index.json",
        mission_dir / "mission_manifest.json",
        *[ROOT / str(item.get("path") or "") for item in workbench_files if str(item.get("path") or "").strip()],
    ])

    return {
        "mission_id": mission,
        "objective": objective,
        "current_state": current_state,
        "status_badge": status_badge,
        "latest_run_id": latest_run_id,
        "last_updated": last_updated,
        "created_at": str(brief.get("created_at") or (manifest or {}).get("created_at") or ""),
        "mission_brief": brief,
        "state": state,
        "manifest": manifest,
        "artifact_index": artifact_index,
        "artifact_refs": (manifest or {}).get("artifact_refs") if isinstance(manifest, dict) else [],
        "latest_hermes_run": _latest_run_summary(mission),
        "latest_draft": _latest_draft_summary(mission),
        "latest_clarification_packet": _latest_clarification_summary(mission),
        "mission_inputs": mission_inputs,
        "mission_chat": mission_chat,
        "workbench": {
            "root": _workbench_root(mission).relative_to(ROOT).as_posix(),
            "folders": workbench_folders,
            "files": workbench_files,
        },
        "artifact_count": len(artifact_items),
        "input_count": len(mission_inputs),
        "chat_count": len(mission_chat),
    }


def _write_mission_input(mission: str, content: str) -> dict[str, Any]:
    created_at = iso_now()
    input_id = f"input_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{_short_digest(f'{mission}|{content}|{created_at}')}"
    intake_dir = _ensure_workbench_structure(mission) / "intake"
    intake_dir.mkdir(parents=True, exist_ok=True)
    input_path = intake_dir / f"{input_id}.json"
    record = {
        "input_id": input_id,
        "mission_id": mission,
        "source_type": "user_provided",
        "status": "unreviewed",
        "content": content,
        "created_at": created_at,
    }
    _write_json(input_path, record)
    return {
        **record,
        "path": input_path.relative_to(ROOT).as_posix(),
    }


def _mission_exists(mission_id: str) -> bool:
    mission = normalize_mission_id(mission_id)
    return _mission_root(mission).exists() or _workbench_root(mission).exists()


def _list_expeditions() -> list[dict[str, Any]]:
    if not EXPEDITIONS_ACTIVE_DIR.exists():
        return []
    missions: list[dict[str, Any]] = []
    for mission_dir in sorted((path for path in EXPEDITIONS_ACTIVE_DIR.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime, reverse=True):
        mission_id = mission_dir.name
        try:
            detail = _build_expedition_detail(mission_id)
        except Exception:
            continue
        missions.append({
            "mission_id": detail["mission_id"],
            "objective": detail["objective"],
            "current_state": detail["current_state"],
            "status_badge": detail["status_badge"],
            "latest_run_id": detail["latest_run_id"],
            "last_updated": detail["last_updated"],
            "created_at": detail["created_at"],
            "artifact_count": detail["artifact_count"],
            "input_count": detail["input_count"],
            "summary": str((detail.get("manifest") or {}).get("summary") or ""),
            "manifest_status": str((detail.get("manifest") or {}).get("status") or ""),
            "path": mission_dir.relative_to(ROOT).as_posix(),
        })
    return missions


def _generate_mission_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    seed = f"{stamp}|{ROOT.as_posix()}|expedition"
    return normalize_mission_id(f"mission_{stamp}_{_short_digest(seed)}")


def _create_mission_brief(mission_id: str, objective: str) -> Path:
    mission = normalize_mission_id(mission_id)
    brief_path = mission_brief_path(mission)
    created_at = iso_now()
    payload = {
        "mission_id": mission,
        "objective": objective,
        "task_text": objective,
        "created_at": created_at,
        "status": "active",
        "latest_run_id": "",
    }
    _write_json(brief_path, payload)
    upsert_artifact_index_entry(mission, "mission_brief", brief_path, created_at=created_at)
    return brief_path


def read_return_all_state() -> dict[str, Any]:
    path = GOVERNANCE_DIR / "return_all.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "ok": True,
                "enabled": bool(data.get("enabled", False)),
                "issued_by": str(data.get("issued_by") or "operator"),
                "issued_at": str(data.get("issued_at") or ""),
                "reason": str(data.get("reason") or ""),
                "allow_custodial_bypass": bool(data.get("allow_custodial_bypass", False)),
            }
        except Exception:
            pass
    return {
        "ok": True,
        "enabled": False,
        "issued_by": "operator",
        "issued_at": "",
        "reason": "",
        "allow_custodial_bypass": False,
    }


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def is_bypass_allowed(petition: dict[str, Any], return_all: dict[str, Any]) -> bool:
    if not return_all.get("allow_custodial_bypass"):
        return False
    spawn_authority = str(petition.get("spawn_authority") or "")
    dispatch_mode = str(petition.get("dispatch_mode") or "")
    entry_class = str(petition.get("entry_class") or "")
    return (
        spawn_authority == "custodial"
        and dispatch_mode == "rapid"
        and entry_class in {"self_heal", "repair"}
    )


def normalize_petition(raw: dict[str, Any], status: str, filename: str, return_all: dict[str, Any]) -> dict[str, Any]:
    petition_id = str(raw.get("petition_id") or "").strip()
    if not petition_id:
        petition_id = f"legacy:{filename}"
        log_topology_event("dispatch_petition", filename, "error", "missing petition_id")

    ask_count = raw.get("ask_count")
    if ask_count is None:
        asks = raw.get("asks")
        if isinstance(asks, list):
            ask_count = len(asks)
        else:
            ask_count = 1
    ask_count = int(ask_count)

    requires_operator_approval = raw.get("requires_operator_approval")
    if requires_operator_approval is None:
        requires_operator_approval = ask_count > 1

    spawn_authority = str(raw.get("spawn_authority") or "emissary")
    dispatch_mode = str(raw.get("dispatch_mode") or "normal")
    operator_id = str(raw.get("operator_id") or "")
    entry_class = str(raw.get("entry_class") or "normal")
    created_at = str(raw.get("created_at") or raw.get("timestamp_created") or iso_now())
    created_by = str(raw.get("created_by") or raw.get("agent_id") or "unknown")
    petition_kind = str(raw.get("petition_kind") or "").strip()
    if not petition_kind:
        petition_kind = "repair_request" if entry_class == "repair" else "self_heal_request" if entry_class == "self_heal" else "anomaly_review" if entry_class == "anomaly_review" else "memory_admission"
    requested_action = str(raw.get("requested_action") or "").strip()
    if not requested_action:
        requested_action = "repair" if petition_kind in {"repair_request", "self_heal_request"} else "operator_review" if petition_kind == "anomaly_review" else "admit_to_collective"
    risk_level = str(raw.get("risk_level") or ("high" if petition_kind in {"anomaly_review", "repair_request"} else "medium"))
    reason = str(raw.get("reason") or raw.get("task") or raw.get("summary") or "")
    evidence_refs = raw.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    related_record_id = str(raw.get("related_record_id") or "")
    related_petition_id = str(raw.get("related_petition_id") or "")
    cooldown_observed = raw.get("cooldown_observed")
    governance_notes = str(raw.get("governance_notes") or "")
    status_updated_at = str(raw.get("status_updated_at") or created_at or iso_now())
    source_host = str(raw.get("source_host") or "unknown")

    petition_status = status
    if return_all.get("enabled") and status == "pending" and not is_bypass_allowed(raw, return_all):
        issued_at = parse_iso(str(return_all.get("issued_at") or ""))
        updated_at = parse_iso(status_updated_at) or datetime.now(timezone.utc)
        if not issued_at or updated_at >= issued_at:
            petition_status = "deferred"
            requires_operator_approval = True

    return {
        "record_type": str(raw.get("record_type") or "dispatch_petition"),
        "petition_id": petition_id,
        "record_name": str(raw.get("record_name") or filename),
        "agent_id": str(raw.get("agent_id") or "unknown"),
        "created_by": created_by,
        "workspace": str(raw.get("workspace") or "unknown"),
        "source": str(raw.get("source") or "dispatch"),
        "timestamp_created": str(raw.get("timestamp_created") or created_at),
        "created_at": created_at,
        "summary": str(raw.get("summary") or ""),
        "task": str(raw.get("task") or ""),
        "confidence": float(raw.get("confidence") or 0.0),
        "promotion_candidate": bool(raw.get("promotion_candidate", False)),
        "payload_type": str(raw.get("payload_type") or "pattern"),
        "urgency": str(raw.get("urgency") or "normal"),
        "requires_emissary": bool(raw.get("requires_emissary", True)),
        "petition_status": petition_status,
        "status": petition_status,
        "ask_count": ask_count,
        "requires_operator_approval": bool(requires_operator_approval),
        "spawn_authority": spawn_authority,
        "dispatch_mode": dispatch_mode,
        "operator_id": operator_id,
        "status_updated_at": status_updated_at,
        "source_host": source_host,
        "entry_class": entry_class,
        "petition_kind": petition_kind,
        "reason": reason,
        "evidence_refs": evidence_refs,
        "requested_action": requested_action,
        "risk_level": risk_level,
        "related_record_id": related_record_id,
        "related_petition_id": related_petition_id,
        "cooldown_observed": cooldown_observed,
        "governance_notes": governance_notes,
    }


def read_dispatch_petitions() -> list[dict]:
    folders = [
        ("pending", DISPATCH_DIR / "pending"),
        ("approved", DISPATCH_DIR / "approved"),
        ("deferred", DISPATCH_DIR / "deferred"),
        ("rejected", DISPATCH_DIR / "rejected"),
    ]
    petitions: list[dict] = []
    seen_ids: dict[str, int] = {}
    logged_duplicates: set[str] = set()
    return_all = read_return_all_state()
    for status, folder in folders:
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                log_topology_event(
                    "dispatch_petition",
                    path.name,
                    "error",
                    "malformed json",
                )
                continue
            petition = normalize_petition(raw, status, path.name, return_all)
            pid = petition["petition_id"]
            if pid in seen_ids:
                seen_ids[pid] += 1
                if pid not in logged_duplicates:
                    log_topology_event(
                        "dispatch_petition",
                        path.name,
                        "error",
                        "duplicate petition_id across dispatch folders",
                    )
                    logged_duplicates.add(pid)
            else:
                seen_ids[pid] = 1
            petitions.append(petition)
    return petitions


def read_item_world_status() -> dict[str, Any]:
    status_path = ROOT / "logs" / "nanny" / "item_world_status.json"
    if status_path.exists():
        try:
            return json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "ok": True,
        "temperature": "cool",
        "burst_score": 0,
        "error_score": 0,
        "active_agent_warnings": [],
        "recommended_actions": [],
        "global_cooldown_seconds": 0,
    }


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def read_support_helper_activity(limit: int = 24) -> dict[str, Any]:
    lane_specs = [
        ("orchestration", SUPPORT_ORCHESTRATION_DIR / "instances"),
        ("retrieval", SUPPORT_RETRIEVAL_DIR / "instances"),
    ]
    items: list[tuple[int, dict[str, Any]]] = []
    lane_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()

    for lane, instance_dir in lane_specs:
        if not instance_dir.exists():
            continue
        for path in sorted(instance_dir.glob("*.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True):
            raw = _load_json_object(path)
            if not raw:
                continue
            item = {
                "lane": lane,
                "helper_id": str(raw.get("helper_id") or path.stem),
                "helper_type": str(raw.get("helper_type") or "unknown"),
                "mandate_id": str(raw.get("mandate_id") or ""),
                "task_scope": str(raw.get("task_scope") or ""),
                "status": str(raw.get("status") or "unknown"),
                "created_at": str(raw.get("created_at") or raw.get("updated_at") or ""),
                "expires_at": str(raw.get("expires_at") or ""),
                "source_file": _safe_relative_path(path),
            }
            lane_counts[lane] += 1
            status_counts[item["status"]] += 1
            items.append((path.stat().st_mtime_ns, item))

    items.sort(key=lambda pair: pair[0], reverse=True)
    return {
        "available": bool(items),
        "total": len(items),
        "lane_counts": dict(lane_counts),
        "status_counts": dict(status_counts),
        "items": [item for _, item in items[:limit]],
        "source_dirs": {
            "orchestration": _safe_relative_path(SUPPORT_ORCHESTRATION_DIR),
            "retrieval": _safe_relative_path(SUPPORT_RETRIEVAL_DIR),
        },
    }


def _mirror_door_signature(script_path: Path, fixture_root: Path) -> str:
    fixture_mtimes: list[int] = []
    if fixture_root.exists():
        for path in fixture_root.rglob("*.json"):
            if path.is_file():
                fixture_mtimes.append(path.stat().st_mtime_ns)
    return "|".join(
        [
            str(script_path.stat().st_mtime_ns if script_path.exists() else 0),
            str(fixture_root.stat().st_mtime_ns if fixture_root.exists() else 0),
            str(len(fixture_mtimes)),
            str(sum(fixture_mtimes)),
        ]
    )


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def _latest_json_files(directory: Path, limit: int) -> list[Path]:
    if not directory.exists():
        return []
    files = [path for path in directory.glob("*.json") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files[:limit]


def _latest_mission_manifest_files(limit: int) -> list[Path]:
    if not EXPEDITIONS_ACTIVE_DIR.exists():
        return []
    files = [path for path in EXPEDITIONS_ACTIVE_DIR.glob("*/mission_manifest.json") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files[:limit]


def _safe_relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _format_bytes(value: int) -> str:
    value = max(0, int(value or 0))
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(value)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{value} B"


def _iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files = [path for path in root.rglob("*") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    return files


def _storage_area_summary(
    name: str,
    root: Path,
    *,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    files = _iter_files(root)
    total_bytes = 0
    json_count = 0
    oldest_path: Path | None = None
    oldest_mtime_ns: int | None = None
    newest_path: Path | None = None
    newest_mtime_ns: int | None = None
    largest_path: Path | None = None
    largest_size = 0

    for path in files:
        try:
            stat = path.stat()
        except Exception:
            continue
        total_bytes += stat.st_size
        if path.suffix.lower() == ".json":
            json_count += 1
        if oldest_mtime_ns is None or stat.st_mtime_ns < oldest_mtime_ns:
            oldest_path = path
            oldest_mtime_ns = stat.st_mtime_ns
        if newest_mtime_ns is None or stat.st_mtime_ns > newest_mtime_ns:
            newest_path = path
            newest_mtime_ns = stat.st_mtime_ns
        if stat.st_size > largest_size:
            largest_size = stat.st_size
            largest_path = path

    newest_age_minutes: float | None = None
    if newest_path is not None:
        newest_age_minutes = max(0.0, (datetime.now(timezone.utc) - datetime.fromtimestamp(newest_path.stat().st_mtime, tz=timezone.utc)).total_seconds() / 60.0)

    pressure_score = 0
    if total_bytes >= 50 * 1024 * 1024:
        pressure_score += 60
    elif total_bytes >= 10 * 1024 * 1024:
        pressure_score += 40
    elif total_bytes >= 1 * 1024 * 1024:
        pressure_score += 20
    elif total_bytes >= 250 * 1024:
        pressure_score += 10

    if len(files) >= 500:
        pressure_score += 25
    elif len(files) >= 100:
        pressure_score += 15
    elif len(files) >= 25:
        pressure_score += 5

    if newest_age_minutes is not None and newest_age_minutes <= 30:
        pressure_score += 5
    if "collective" in name:
        pressure_score += 5

    if pressure_score >= 70:
        pressure_label = "high"
    elif pressure_score >= 35:
        pressure_label = "elevated"
    elif pressure_score >= 15:
        pressure_label = "watch"
    else:
        pressure_label = "low"

    return {
        "name": name,
        "path": _safe_relative_path(root),
        "available": root.exists(),
        "file_count": len(files),
        "json_file_count": json_count,
        "total_bytes": total_bytes,
        "total_bytes_label": _format_bytes(total_bytes),
        "oldest_modified_at": _mtime_iso(oldest_path) if oldest_path else "",
        "newest_modified_at": _mtime_iso(newest_path) if newest_path else "",
        "newest_age_minutes": round(newest_age_minutes, 1) if newest_age_minutes is not None else None,
        "largest_file": {
            "name": _safe_relative_path(largest_path) if largest_path else "",
            "bytes": largest_size,
            "bytes_label": _format_bytes(largest_size),
        } if largest_path else None,
        "pressure_score": pressure_score,
        "pressure_label": pressure_label,
        "notes": notes or [],
    }


def _collective_door_footprint() -> dict[str, Any]:
    root = MEMORY_DIR / "collective"
    files = _iter_files(root)
    total_bytes = 0
    admitted_count = 0
    admitted_bytes = 0
    blocked_count = 0
    blocked_bytes = 0
    malformed_count = 0
    legacy_count = 0
    door_reasons: Counter[str] = Counter()

    for path in files:
        try:
            stat = path.stat()
        except Exception:
            continue
        total_bytes += stat.st_size

        payload = _load_json_object(path)
        if not payload:
            malformed_count += 1
            door_reasons["malformed json"] += 1
            continue

        if bool(payload.get("legacy_compatibility")):
            legacy_count += 1

        gate = can_bridge_to_honcho(payload)
        if gate.allowed:
            admitted_count += 1
            admitted_bytes += stat.st_size
        else:
            blocked_count += 1
            blocked_bytes += stat.st_size
            door_reasons[str(gate.reason or gate.status or "blocked")] += 1

    admitted_ratio = round(admitted_count / total_files, 3) if (total_files := admitted_count + blocked_count + malformed_count) else 0.0

    return {
        "path": _safe_relative_path(root),
        "total_files": total_files,
        "total_bytes": total_bytes,
        "total_bytes_label": _format_bytes(total_bytes),
        "admitted_count": admitted_count,
        "admitted_bytes": admitted_bytes,
        "admitted_bytes_label": _format_bytes(admitted_bytes),
        "blocked_count": blocked_count,
        "blocked_bytes": blocked_bytes,
        "blocked_bytes_label": _format_bytes(blocked_bytes),
        "malformed_count": malformed_count,
        "legacy_count": legacy_count,
        "admitted_ratio": admitted_ratio,
        "door_reasons": dict(door_reasons.most_common(6)),
    }


def _storage_footprint(groups: list[dict[str, Any]], selected_names: set[str]) -> dict[str, Any]:
    selected = [group for group in groups if group["name"] in selected_names]
    total_bytes = sum(group["total_bytes"] for group in selected)
    total_files = sum(group["file_count"] for group in selected)
    return {
        "group_names": sorted(selected_names),
        "total_bytes": total_bytes,
        "total_bytes_label": _format_bytes(total_bytes),
        "total_files": total_files,
        "groups": selected,
    }


def read_storage_overview() -> dict[str, Any]:
    areas = [
        _storage_area_summary("memory/collective", MEMORY_DIR / "collective", notes=["governed collective records"]),
        _storage_area_summary("memory/dispatch", DISPATCH_DIR, notes=["dispatch petition queue"]),
        _storage_area_summary("memory/drafts", MEMORY_DIR / "drafts", notes=["petition drafts"]),
        _storage_area_summary("memory/inbox", INBOX_DIR, notes=["raw intake"]),
        _storage_area_summary("memory/promotion", PROMOTION_DIR, notes=["promotion candidates"]),
        _storage_area_summary("memory/compacted", COMPACTED_DIR, notes=["compaction outputs"]),
        _storage_area_summary("memory/archive", ARCHIVE_DIR, notes=["archived source records"]),
        _storage_area_summary("logs/support", ROOT / "logs" / "support", notes=["support helper records"]),
        _storage_area_summary("logs/compactor", COMPACTOR_LOG_DIR, notes=["compactor run history"]),
        _storage_area_summary("logs/governance", GOVERNANCE_DIR, notes=["governance status records"]),
        _storage_area_summary("logs/nanny", ROOT / "logs" / "nanny", notes=["nanny and weather state"]),
    ]

    collective = _collective_door_footprint()
    compactor_last_run = _load_json_object(COMPACTOR_LOG_DIR / "last_run.json")

    active_footprint = _storage_footprint(
        areas,
        {
            "memory/collective",
            "memory/dispatch",
            "memory/drafts",
            "memory/inbox",
            "memory/promotion",
            "logs/support",
            "logs/governance",
            "logs/nanny",
        },
    )
    archive_footprint = _storage_footprint(
        areas,
        {
            "memory/archive",
            "memory/compacted",
        },
    )
    compaction_metadata_footprint = _storage_footprint(
        areas,
        {
            "logs/compactor",
        },
    )

    hotspots = sorted(
        areas,
        key=lambda item: (item["pressure_score"], item["total_bytes"], item["file_count"]),
        reverse=True,
    )[:6]

    return {
        "available": True,
        "generated_at": iso_now(),
        "areas": areas,
        "hotspots": hotspots,
        "collective_door": collective,
        "footprints": {
            "active": active_footprint,
            "archive": archive_footprint,
            "compaction": compaction_metadata_footprint,
            "all_observed_bytes": _format_bytes(sum(area["total_bytes"] for area in areas)),
        },
        "compactor_last_run": compactor_last_run or {},
    }


def read_hermes_runs(limit: int = 8) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in _latest_json_files(HERMES_RUNS_DIR, limit):
        source_path = _safe_relative_path(path)
        try:
            payload = _load_json(path)
        except Exception as exc:
            items.append({
                "ok": False,
                "source_path": source_path,
                "captured_at": _mtime_iso(path),
                "error": f"malformed json: {exc}",
            })
            continue

        if not isinstance(payload, dict):
            items.append({
                "ok": False,
                "source_path": source_path,
                "captured_at": _mtime_iso(path),
                "error": "run record must be a JSON object",
            })
            continue

        run_id = str(payload.get("run_id") or "").strip()
        mode = str(payload.get("mode") or "").strip()
        if not run_id or not mode:
            items.append({
                "ok": False,
                "source_path": source_path,
                "captured_at": _mtime_iso(path),
                "error": "run record missing run_id or mode",
            })
            continue

        ok, reason = validate_response_object(payload, run_id, mode)
        if not ok:
            items.append({
                "ok": False,
                "source_path": source_path,
                "captured_at": _mtime_iso(path),
                "error": reason,
            })
            continue

        items.append({
            "ok": True,
            "source_path": source_path,
            "captured_at": _mtime_iso(path),
            "run_id": run_id,
            "mode": mode,
            "status": str(payload.get("status") or ""),
            "summary": str(payload.get("summary") or ""),
            "evidence_refs": list(payload.get("evidence_refs") or []),
            "recommended_action": str(payload.get("recommended_action") or ""),
            "petition_kind": payload.get("petition_kind"),
            "confidence": float(payload.get("confidence") or 0.0),
            "classification": payload.get("classification"),
        })
    return items


def read_petition_draft_previews(limit: int = 8) -> list[dict[str, Any]]:
    drafts_dir = MEMORY_DIR / "drafts"
    return_all = read_return_all_state()
    nanny = read_nanny_state()
    items: list[dict[str, Any]] = []

    for path in _latest_json_files(drafts_dir, limit):
        source_path = _safe_relative_path(path)
        try:
            payload = _load_json(path)
            draft = validate_draft_petition(payload, path=path)
            preview = build_review_payload(
                draft,
                draft_path=path,
                return_all=return_all,
                nanny=nanny,
            )
        except Exception as exc:
            items.append({
                "ok": False,
                "source_path": source_path,
                "error": str(exc),
            })
            continue

        items.append({
            "ok": True,
            "source_path": source_path,
            "draft": {
                "petition_id": draft["petition_id"],
                "mode": draft["mode"],
                "petition_kind": draft["petition_kind"],
                "petition_type": draft["petition_type"],
                "requested_action": draft["requested_action"],
                "confidence": draft["confidence"],
                "source_run_id": draft["source_run_id"],
                "summary": draft["summary"],
                "evidence_refs": draft["evidence_refs"],
            },
            "review_preview": preview,
        })

    return items


def read_latest_clarification_packet() -> dict[str, Any]:
    latest = _latest_json_files(CLARIFICATION_PACKETS_DIR, 1)
    source_root = _safe_relative_path(CLARIFICATION_PACKETS_DIR)
    if not latest:
        return {
            "ok": True,
            "available": False,
            "source_root": source_root,
            "item": None,
        }

    path = latest[0]
    source_path = _safe_relative_path(path)
    try:
        payload = _load_json(path)
        packet = validate_clarification_packet(payload, path=path)
    except Exception as exc:
        return {
            "ok": False,
            "available": False,
            "source_root": source_root,
            "source_path": source_path,
            "error": str(exc),
            "item": None,
        }

    return {
        "ok": True,
        "available": True,
        "source_root": source_root,
        "source_path": source_path,
        "item": packet,
    }


def read_latest_mission_manifest() -> dict[str, Any]:
    latest = _latest_mission_manifest_files(1)
    source_root = _safe_relative_path(EXPEDITIONS_ACTIVE_DIR)
    if not latest:
        return {
            "ok": True,
            "available": False,
            "source_root": source_root,
            "item": None,
        }

    path = latest[0]
    source_path = _safe_relative_path(path)
    try:
        payload = _load_json(path)
        if not isinstance(payload, dict):
            raise ValueError("mission manifest must be a JSON object")
        required = [
            "manifest_id",
            "mission_id",
            "run_id",
            "status",
            "summary",
            "artifact_counts",
            "artifact_refs",
            "priority_views",
            "mission_signals",
            "open_questions",
            "recommended_next_step",
            "created_at",
            "updated_at",
        ]
        missing = [field for field in required if field not in payload]
        if missing:
            raise ValueError(f"mission manifest missing field(s): {', '.join(missing)}")
    except Exception as exc:
        return {
            "ok": False,
            "available": False,
            "source_root": source_root,
            "source_path": source_path,
            "error": str(exc),
            "item": None,
        }

    return {
        "ok": True,
        "available": True,
        "source_root": source_root,
        "source_path": source_path,
        "item": payload,
    }


def read_dispatch_counts() -> dict[str, int]:
    counts = {"pending": 0, "approved": 0, "deferred": 0, "rejected": 0}
    for petition in read_dispatch_petitions():
        status = str(petition.get("status") or "").strip()
        if status in counts:
            counts[status] += 1
    counts["total"] = sum(counts.values())
    return counts


def read_mirror_door_test_status() -> dict[str, Any]:
    script_path = ROOT / "scripts" / "test_mirror_door_contracts.py"
    fixture_root = ROOT / "tests" / "mirror_door_contracts"
    signature = _mirror_door_signature(script_path, fixture_root)
    cached_signature = str(MIRROR_DOOR_CACHE.get("signature") or "")
    cached_value = MIRROR_DOOR_CACHE.get("value")
    if cached_signature == signature and isinstance(cached_value, dict):
        return cached_value

    summary: dict[str, Any] = {
        "available": script_path.exists() and fixture_root.exists(),
        "script_path": "scripts/test_mirror_door_contracts.py",
        "fixture_root": "tests/mirror_door_contracts",
        "fixture_categories": [],
        "fixture_files": 0,
        "total": 0,
        "correctly_blocked": 0,
        "validly_accepted": 0,
        "unexpected_accept": 0,
        "unexpected_error": 0,
        "recent_failures": [],
    }
    if not summary["available"]:
        MIRROR_DOOR_CACHE["signature"] = signature
        MIRROR_DOOR_CACHE["value"] = summary
        return summary

    try:
        import test_mirror_door_contracts as mirror_tests
    except Exception as exc:  # pragma: no cover - import fallback only
        summary["available"] = False
        summary["error"] = f"unable to import mirror-door test script: {exc}"
        MIRROR_DOOR_CACHE["signature"] = signature
        MIRROR_DOOR_CACHE["value"] = summary
        return summary

    try:
        cases = list(mirror_tests.iter_case_files())
        results = [mirror_tests.run_case(case) for case in cases]
    except Exception as exc:
        summary["available"] = False
        summary["error"] = f"mirror-door test execution failed: {exc}"
        MIRROR_DOOR_CACHE["signature"] = signature
        MIRROR_DOOR_CACHE["value"] = summary
        return summary

    counts: Counter[str] = Counter(result.bucket for result in results)
    failures = [
        {
            "category": result.category,
            "case_id": result.case_id,
            "expected": result.expected,
            "actual": result.actual,
            "reason": result.reason,
            "attack_surface": result.attack_surface,
            "source_file": _safe_relative_path(result.source_file),
        }
        for result in results
        if result.bucket in {"unexpected_accept", "unexpected_error"}
    ]
    fixture_categories = sorted(path.name for path in fixture_root.iterdir() if path.is_dir())

    summary.update(
        {
            "fixture_categories": fixture_categories,
            "fixture_files": sum(1 for path in fixture_root.rglob("*.json") if path.is_file()),
            "total": len(results),
            "correctly_blocked": int(counts.get("correctly_blocked", 0)),
            "validly_accepted": int(counts.get("validly_accepted", 0)),
            "unexpected_accept": int(counts.get("unexpected_accept", 0)),
            "unexpected_error": int(counts.get("unexpected_error", 0)),
            "recent_failures": failures[:6],
            "generated_at": iso_now(),
        }
    )
    MIRROR_DOOR_CACHE["signature"] = signature
    MIRROR_DOOR_CACHE["value"] = summary
    return summary


@app.get("/api/status")
def api_status():
    sessions_total, sessions_items = get_sessions(10)
    peers_total, peers_items = get_peers(10)

    return jsonify({
        "ok": True,
        "workspace_id": WORKSPACE_ID,
        "honcho_sessions_total": sessions_total,
        "honcho_peers_total": peers_total,
        "honcho_sessions": sessions_items,
        "honcho_peers": peers_items,
        "events_recent": get_events(50),
        "return_all": read_return_all_state(),
        "nanny": read_item_world_status(),
        "dispatch_counts": read_dispatch_counts(),
        "support_helper_activity": read_support_helper_activity(),
        "mirror_door_test": read_mirror_door_test_status(),
        "storage_overview": read_storage_overview(),
    })


@app.get("/api/events")
def api_events():
    return jsonify({
        "ok": True,
        "items": get_events(200)
    })


@app.get("/api/dispatch")
def api_dispatch():
    return jsonify({
        "ok": True,
        "petitions": read_dispatch_petitions(),
    })


@app.get("/api/hermes/runs")
def api_hermes_runs():
    try:
        limit = max(1, min(20, int(request.args.get("limit", 8))))
    except Exception:
        limit = 8
    return jsonify({
        "ok": True,
        "source_root": _safe_relative_path(HERMES_RUNS_DIR),
        "items": read_hermes_runs(limit),
    })


@app.get("/api/petition-drafts")
def api_petition_drafts():
    try:
        limit = max(1, min(20, int(request.args.get("limit", 8))))
    except Exception:
        limit = 8
    return jsonify({
        "ok": True,
        "source_root": _safe_relative_path(MEMORY_DIR / "drafts"),
        "items": read_petition_draft_previews(limit),
    })


@app.get("/api/clarification/latest")
def api_clarification_latest():
    return jsonify(read_latest_clarification_packet())


@app.get("/api/mission-manifest/latest")
def api_mission_manifest_latest():
    return jsonify(read_latest_mission_manifest())


@app.get("/api/expeditions")
def api_expeditions_list():
    return jsonify({
        "ok": True,
        "source_root": _safe_relative_path(EXPEDITIONS_ACTIVE_DIR),
        "items": _list_expeditions(),
    })


@app.get("/api/expeditions/<mission_id>")
def api_expedition_detail(mission_id: str):
    try:
        exists = _mission_exists(mission_id)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "available": False,
            "error": str(exc),
            "item": None,
        }), 400
    if not exists:
        return jsonify({
            "ok": False,
            "available": False,
            "error": "mission not found",
            "item": None,
        }), 404
    try:
        item = _build_expedition_detail(mission_id)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "available": False,
            "error": str(exc),
            "item": None,
        }), 400
    return jsonify({
        "ok": True,
        "available": True,
        "item": item,
    })


@app.post("/api/expeditions")
def api_expeditions_create():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    objective = str(payload.get("objective") or payload.get("task_text") or "").strip()
    if not objective:
        return jsonify({
            "ok": False,
            "error": "objective is required",
        }), 400

    mission_id = _generate_mission_id()
    mission_dir = _mission_root(mission_id)
    mission_dir.mkdir(parents=True, exist_ok=True)
    _ensure_workbench_structure(mission_id)
    write_state(mission_id, "MISSION_DEFINED")
    _create_mission_brief(mission_id, objective)

    detail = _build_expedition_detail(mission_id)
    return jsonify({
        "ok": True,
        "item": detail,
    })


@app.post("/api/expeditions/<mission_id>/input")
def api_expedition_input(mission_id: str):
    try:
        mission = normalize_mission_id(mission_id)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 400
    if not _mission_exists(mission):
        return jsonify({
            "ok": False,
            "error": "mission not found",
        }), 404
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    content = str(payload.get("content") or payload.get("text") or "").strip()
    if not content:
        return jsonify({
            "ok": False,
            "error": "content is required",
        }), 400

    return jsonify({
        "ok": True,
        "item": _write_mission_input(mission, content),
        "mission": _build_expedition_detail(mission),
    })


@app.post("/api/expeditions/<mission_id>/respond")
def api_expedition_respond(mission_id: str):
    return api_expedition_chat(mission_id)


@app.get("/api/expeditions/<mission_id>/chat")
def api_expedition_chat_get(mission_id: str):
    try:
        mission = normalize_mission_id(mission_id)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 400
    if not _mission_exists(mission):
        return jsonify({
            "ok": False,
            "error": "mission not found",
        }), 404
    return jsonify({
        "ok": True,
        "item": _build_expedition_detail(mission),
        "messages": _mission_chat_messages(mission),
        "source_root": _safe_relative_path(_mission_chat_path(mission).parent),
    })


@app.post("/api/expeditions/<mission_id>/chat")
def api_expedition_chat(mission_id: str):
    try:
        mission = normalize_mission_id(mission_id)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 400
    if not _mission_exists(mission):
        return jsonify({
            "ok": False,
            "error": "mission not found",
        }), 404
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    content = str(payload.get("content") or payload.get("text") or "").strip()
    if not content:
        return jsonify({
            "ok": False,
            "error": "content is required",
        }), 400

    quick_reply = str(payload.get("quick_reply") or payload.get("preset") or "").strip() or None
    exchange = _append_chat_exchange(mission, content, quick_reply=quick_reply)
    return jsonify({
        "ok": True,
        "item": _build_expedition_detail(mission),
        "messages": _mission_chat_messages(mission),
        "exchange": exchange,
        "response": {
            "kind": "chat",
            "summary": "Mission chat updated.",
            "answer": str((exchange.get("messages") or [{}])[-1].get("message") if isinstance(exchange, dict) else ""),
            "questions": [],
            "artifact": "mission_chat",
        },
    })


@app.get("/api/governance/return-all")
def api_governance_return_all():
    return jsonify(read_return_all_state())


@app.get("/api/item-world-status")
def api_item_world_status():
    return jsonify(read_item_world_status())


@app.post("/api/event")
def api_event_create():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    event = normalize_event(payload)
    IN_MEMORY_EVENTS.append(event)
    if len(IN_MEMORY_EVENTS) > IN_MEMORY_EVENTS_MAX:
        del IN_MEMORY_EVENTS[:-IN_MEMORY_EVENTS_MAX]
    return jsonify({
        "ok": True,
        "item": event,
        "total": len(IN_MEMORY_EVENTS),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5051, debug=False)
