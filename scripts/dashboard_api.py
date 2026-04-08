from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
import threading
import urllib.request
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from flask import Flask, jsonify, request

from agent_invocation import invoke_role
from autonomy_guardrails import build_autonomy_status_view, evaluate_autonomy_guardrails
from validate_clarification_packet import validate_clarification_packet
from state_machine import (
    mission_brief_path,
    mission_manifest_path,
    normalize_mission_id,
    read_artifact_index,
    read_mission_brief,
    read_working_memory,
    read_state,
    upsert_artifact_index_entry,
    working_memory_path,
    write_working_memory,
    write_state,
)
from governance_utils import can_bridge_to_honcho, read_nanny_state, read_return_all_state
from helper_model_runtime import load_helper_runtime_profile
import mirror_api as mirror_api_routes
import mission_api as mission_api_routes
import mission_read_model
import mission_storage
from prompt_translator import read_prompt_translations, translate_and_store_prompt
from review_and_submit_petition import build_review_payload, validate_draft_petition
import save_api as save_api_helpers
from run_hermes_v1 import (
    extract_json_candidate,
    invoke_model,
    load_hermes_runtime_config,
    load_model_registry,
    validate_response_object,
)

ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG = ROOT / "logs" / "topology" / "events.jsonl"
HERMES_RUNS_DIR = ROOT / "logs" / "hermes" / "runs"
CLARIFICATION_PACKETS_DIR = ROOT / "logs" / "citadel" / "clarification_packets"
EXPEDITIONS_ACTIVE_DIR = ROOT / "expeditions" / "active"
WORKBENCH_MISSIONS_DIR = ROOT / "workbench" / "missions"
MISSION_CHAT_FILENAME = "chat.jsonl"
MISSION_PARKING_FILENAME = "parking_status.json"
MISSION_AGENT_DIRNAME = "agent"
MISSION_AGENT_PROFILE_FILENAME = "profile.json"
MISSION_AGENT_SOUL_FILENAME = "SOUL.md"
TRIGGERS_DIRNAME = "triggers"
TRIGGER_HANDOFF_FILENAME = "pending_handoff.json"
RUNNER_RETURNS_DIRNAME = "runner_returns"
RETRY_LEDGER_FILENAME = "retries.json"
ASSUMPTIONS_DIRNAME = "assumptions"
ASSUMPTION_LEDGER_FILENAME = "ledger.json"
INTERVENTIONS_DIRNAME = "interventions"
INTERVENTION_LOG_FILENAME = "log.jsonl"
MIRROR_DIRNAME = "mirror"
AGENT_RUNS_DIRNAME = "agent_runs"
MEMORY_DIR = ROOT / "memory"
DISPATCH_DIR = MEMORY_DIR / "dispatch"
GOVERNANCE_DIR = ROOT / "logs" / "governance"
SUPPORT_ORCHESTRATION_DIR = ROOT / "logs" / "support" / "orchestration"
SUPPORT_RETRIEVAL_DIR = ROOT / "logs" / "support" / "retrieval"
SUPPORT_ORCHESTRATION_INSTANCES_DIR = SUPPORT_ORCHESTRATION_DIR / "instances"
SUPPORT_RETRIEVAL_INSTANCES_DIR = SUPPORT_RETRIEVAL_DIR / "instances"
EXPEDITIONER_MODEL_LOG = ROOT / "logs" / "support" / "expeditioner_model_invocations.jsonl"
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
_MISSION_LOCKS: dict[str, threading.Lock] = {}
_MISSION_LOCKS_GUARD = threading.Lock()

KNOWN_PEERS = [
    {"id": "desktop", "metadata": {"created_by": "system"}},
    {"id": "laptop", "metadata": {"created_by": "system"}},
]

app = Flask(__name__)
PROMPT_TRANSLATOR_ACTIVE = False
_ROUTE_API = sys.modules[__name__]


ALLOWED_TRIGGER_KINDS: dict[str, dict[str, Any]] = {
    "sufficiency_unblocked_on_input": {
        "target_role": "spinetop-expeditioner",
        "allowed_action": "start_first_pass_expedition",
        "write_targets": ["workbench/missions/", "logs/support/"],
        "policy_basis": "explicit_input_sufficiency_flip",
        "allow_while_parked": False,
        "requires_first_pass_open": True,
        "counts_against_retry_budget": False,
    },
    "operator_refresh_requested": {
        "target_role": "spinetop-expeditioner",
        "allowed_action": "retry_expedition_refresh",
        "write_targets": ["workbench/missions/", "logs/support/"],
        "policy_basis": "operator_requested_refresh",
        "allow_while_parked": False,
        "requires_first_pass_open": False,
        "counts_against_retry_budget": True,
    },
    "mission_resumed": {
        "target_role": "spinetop-expeditioner",
        "allowed_action": "resume_expedition",
        "write_targets": ["workbench/missions/"],
        "policy_basis": "operator_explicit_resume",
        "allow_while_parked": True,
        "requires_first_pass_open": False,
        "counts_against_retry_budget": False,
    },
    "do_now_first_pass_requested": {
        "target_role": "spinetop-expeditioner",
        "allowed_action": "start_first_pass_expedition",
        "write_targets": ["workbench/missions/", "logs/support/"],
        "policy_basis": "operator_marked_do_now_first_pass",
        "allow_while_parked": False,
        "requires_first_pass_open": True,
        "counts_against_retry_budget": False,
        "requires_do_now": True,
    },
}
ALLOWED_TRIGGER_ACTIONS = {
    "start_first_pass_expedition",
    "retry_expedition_refresh",
    "resume_expedition",
}
TRIGGER_RETRY_BUDGET = 1
RETRY_BUDGET_TOTAL = 2
RETRY_LOG_LIMIT = 40
EXPEDITIONER_ROLE_ID = "spinetop-expeditioner"


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
        "operator_intervention",
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
        "applied",
        "blocked",
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


def _record_object(record: Any, key: str) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    value = record.get(key)
    return value if isinstance(value, dict) else None


def _mission_root(mission_id: str) -> Path:
    return EXPEDITIONS_ACTIVE_DIR / normalize_mission_id(mission_id)


@contextmanager
def _mission_trigger_lock(mission_id: str):
    mission = normalize_mission_id(mission_id)
    with _MISSION_LOCKS_GUARD:
        lock = _MISSION_LOCKS.setdefault(mission, threading.Lock())
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def _workbench_root(mission_id: str) -> Path:
    return WORKBENCH_MISSIONS_DIR / normalize_mission_id(mission_id)


def _ensure_workbench_structure(mission_id: str) -> Path:
    root = _workbench_root(mission_id)
    for folder in ["intake", "scratch", "code", "test_runs", "notes", "outputs"]:
        (root / folder).mkdir(parents=True, exist_ok=True)
    return root


def _workbench_notes_root(mission_id: str, *, ensure: bool = False) -> Path:
    root = _ensure_workbench_structure(mission_id) if ensure else _workbench_root(mission_id)
    return root / "notes"


def _mission_chat_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / MISSION_CHAT_FILENAME


def _mission_agent_root(mission_id: str, *, ensure: bool = False) -> Path:
    root = _mission_root(mission_id)
    if ensure:
        (root / MISSION_AGENT_DIRNAME).mkdir(parents=True, exist_ok=True)
    return root / MISSION_AGENT_DIRNAME


def _mission_agent_profile_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _mission_agent_root(mission_id, ensure=ensure) / MISSION_AGENT_PROFILE_FILENAME


def _mission_agent_soul_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _mission_agent_root(mission_id, ensure=ensure) / MISSION_AGENT_SOUL_FILENAME


def _mission_parking_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / MISSION_PARKING_FILENAME


def _triggers_dir(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / TRIGGERS_DIRNAME


def _trigger_handoff_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _triggers_dir(mission_id, ensure=ensure) / TRIGGER_HANDOFF_FILENAME


def _runner_returns_dir(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / RUNNER_RETURNS_DIRNAME


def _retry_ledger_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / RETRY_LEDGER_FILENAME


def _assumptions_dir(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / ASSUMPTIONS_DIRNAME


def _assumption_ledger_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _assumptions_dir(mission_id, ensure=ensure) / ASSUMPTION_LEDGER_FILENAME


def _mirror_dir(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / MIRROR_DIRNAME


def _agent_runs_dir(mission_id: str, *, ensure: bool = False) -> Path:
    root = _workbench_notes_root(mission_id, ensure=ensure) / AGENT_RUNS_DIRNAME
    if ensure:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _interventions_dir(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / INTERVENTIONS_DIRNAME


def _intervention_log_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _interventions_dir(mission_id, ensure=ensure) / INTERVENTION_LOG_FILENAME


def _archive_candidate_marker_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _interventions_dir(mission_id, ensure=ensure) / "archive_candidate.json"


def _read_archive_candidate_marker(mission_id: str) -> dict[str, Any]:
    path = _archive_candidate_marker_path(mission_id)
    if not path.exists():
        return {}
    marker = _load_json(path)
    return marker if isinstance(marker, dict) else {}


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


def _latest_index_path_ref(mission_id: str, kind: str) -> str:
    index = read_artifact_index(mission_id)
    item = _latest_index_item(list(index.get("items") or []), kind)
    if not isinstance(item, dict):
        return ""
    return str(item.get("path") or "").strip()


def _relative_or_absolute(path: Path | str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return (ROOT / candidate).resolve()


def _safe_mission_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return normalize_mission_id(text)
    except Exception:
        return ""


def _mission_id_from_path_ref(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    match = re.search(r"(?:^|/)(?:workbench/missions|expeditions/active)/([^/]+)/", text)
    if not match:
        return ""
    return _safe_mission_id(match.group(1))


def _support_refs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    refs: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            refs.append(text)
    return refs


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


def _helper_output_candidates(instance: dict[str, Any]) -> list[tuple[str, Path]]:
    refs: list[str] = []
    refs.extend(_support_refs(instance.get("outputs_refs")))
    helper_id = str(instance.get("helper_id") or "").strip()
    artifact_path = SUPPORT_ORCHESTRATION_DIR / "artifacts" / f"{helper_id}.json"
    try:
        artifact_payload = _load_json(artifact_path) if artifact_path.exists() else None
    except Exception:
        artifact_payload = None
    if isinstance(artifact_payload, dict):
        refs.extend(_support_refs(artifact_payload.get("outputs_refs")))

    candidates: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for ref in refs:
        path = _relative_or_absolute(ref)
        key = path.as_posix()
        if key in seen:
            continue
        seen.add(key)
        candidates.append((ref, path))

    helper_type = str(instance.get("helper_type") or "").strip()
    if helper_id:
        fallback_paths: list[Path] = []
        if helper_type == "runner_helper_2b":
            fallback_paths.append(ROOT / "logs" / "support" / "runs" / f"{helper_id}.json")
        elif helper_type == "retrieval_helper_2b":
            fallback_paths.append(ROOT / "logs" / "support" / "retrieval" / f"{helper_id}_result.json")
        for path in fallback_paths:
            key = path.as_posix()
            if key in seen:
                continue
            seen.add(key)
            try:
                ref = path.relative_to(ROOT).as_posix()
            except Exception:
                ref = path.as_posix()
            candidates.append((ref, path))
    return candidates


def _load_helper_output(instance: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    for ref, path in _helper_output_candidates(instance):
        try:
            payload = _load_json(path) if path.exists() else None
        except Exception:
            payload = None
        if isinstance(payload, dict):
            return payload, ref
    return None, ""


def _linked_mission_id_for_helper(instance: dict[str, Any], output_payload: dict[str, Any] | None = None) -> str:
    candidates: list[str] = []
    for value in [
        instance.get("mission_id"),
        (output_payload or {}).get("mission_id"),
    ]:
        mission = _safe_mission_id(value)
        if mission and mission not in candidates:
            candidates.append(mission)

    for value in [
        instance.get("request_ref"),
        instance.get("return_lane"),
        *(_support_refs(instance.get("inputs_refs"))),
        *(_support_refs(instance.get("outputs_refs"))),
        *(_support_refs((output_payload or {}).get("inputs_refs"))),
        *(_support_refs((output_payload or {}).get("outputs_refs"))),
        (output_payload or {}).get("source_path"),
        (output_payload or {}).get("lane"),
    ]:
        mission = _mission_id_from_path_ref(value)
        if mission and mission not in candidates:
            candidates.append(mission)

    if len(candidates) != 1:
        return ""
    return candidates[0]


def _runner_return_confidence(instance: dict[str, Any], output_payload: dict[str, Any] | None = None) -> float:
    helper_type = str(instance.get("helper_type") or "").strip()
    if helper_type == "retrieval_helper_2b":
        result_status = str((output_payload or {}).get("result_status") or instance.get("result_status") or "").strip()
        if result_status == "complete":
            return 0.58
        if result_status == "partial":
            return 0.42
        if result_status == "none_found":
            return 0.24
        return 0.16
    status = str((output_payload or {}).get("status") or instance.get("status") or "").strip()
    if status == "complete":
        return 0.46
    if status == "blocked":
        return 0.18
    return 0.14


def _build_runner_return_packet(mission_id: str, instance: dict[str, Any], output_payload: dict[str, Any] | None, *, source_ref: str) -> dict[str, Any]:
    helper_id = str(instance.get("helper_id") or "").strip()
    helper_type = str(instance.get("helper_type") or "").strip()
    lane = str(instance.get("return_lane") or source_ref or "").strip()
    created_at = str(
        (output_payload or {}).get("completed_at")
        or (output_payload or {}).get("last_run_at")
        or instance.get("updated_at")
        or instance.get("created_at")
        or iso_now()
    ).strip()

    findings: list[str] = []
    open_questions: list[str] = []
    recommended_next_step = "Review the helper output before deciding the next bounded mission step."
    summary = str((output_payload or {}).get("summary") or "").strip()

    if helper_type == "retrieval_helper_2b":
        query_scope = str((output_payload or {}).get("query_scope") or instance.get("query_scope") or instance.get("task_scope") or "").strip()
        result_status = str((output_payload or {}).get("result_status") or instance.get("result_status") or instance.get("status") or "").strip()
        evidence_refs = _support_refs((output_payload or {}).get("evidence_refs"))[:8]
        findings.extend(evidence_refs)
        if not findings:
            findings.extend(_support_refs((output_payload or {}).get("notes"))[:6])
        if not summary:
            summary = f"Retrieval helper {result_status or 'returned'} for {query_scope or helper_id}."
        if result_status == "none_found":
            open_questions.append(f"No evidence was found for {query_scope or 'the requested query'}.")
            recommended_next_step = "Refine the retrieval query or provide narrower source guidance."
        elif result_status == "partial":
            open_questions.append("The retrieval completed only partially and may need a follow-up pass.")
            recommended_next_step = "Review the partial evidence and decide whether to retry or proceed."
        elif result_status == "blocked":
            open_questions.append("The retrieval helper blocked before it could return a complete evidence bundle.")
            recommended_next_step = "Inspect the blocked retrieval receipt and decide whether replacement is needed."
        else:
            recommended_next_step = "Review the cited evidence and decide whether the mission needs another bounded helper pass."
    else:
        step_transcript = (output_payload or {}).get("step_transcript")
        if isinstance(step_transcript, list):
            for item in step_transcript[:8]:
                if not isinstance(item, dict):
                    continue
                step_text = str(item.get("step") or "").strip()
                status_text = str(item.get("status") or "").strip()
                if step_text:
                    findings.append(f"{status_text or 'complete'}: {step_text}")
        if not findings:
            task_plan = instance.get("task_plan")
            if isinstance(task_plan, list):
                findings.extend([str(item).strip() for item in task_plan[:8] if str(item).strip()])
        reason = str((output_payload or {}).get("reason") or "").strip()
        if not summary:
            summary = reason or f"Runner helper returned an operational receipt for {str(instance.get('task_scope') or helper_id).strip()}."
        if str((output_payload or {}).get("status") or instance.get("status") or "").strip() == "blocked":
            open_questions.append(reason or "The runner helper did not complete its bounded procedure.")
            recommended_next_step = "Inspect the blocked operational receipt and decide whether replacement is needed."
        else:
            recommended_next_step = "Review the operational receipt and decide whether the mission needs another bounded helper task."

    return {
        "mission_id": mission_id,
        "runner_id": helper_type or helper_id,
        "instance_id": helper_id,
        "created_at": created_at,
        "kind": "finding_return",
        "summary": summary or f"Helper return captured from {helper_id}.",
        "findings": findings,
        "confidence": _runner_return_confidence(instance, output_payload),
        "open_questions": open_questions,
        "recommended_next_step": recommended_next_step,
        "lane": lane,
        "derived_only": True,
        "helper_type": helper_type,
        "source_ref": source_ref,
    }


def _iter_helper_instances() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for root in [SUPPORT_ORCHESTRATION_INSTANCES_DIR, SUPPORT_RETRIEVAL_INSTANCES_DIR]:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            payload = _load_json(path)
            if not isinstance(payload, dict):
                continue
            payload["_instance_path"] = path.relative_to(ROOT).as_posix()
            items.append(payload)
    return items


def _read_runner_returns(mission_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = _runner_returns_dir(mission_id)
    if not root.exists():
        return rows
    for path in sorted(root.glob("*.json")):
        payload = _load_json(path)
        if not isinstance(payload, dict):
            continue
        payload["path"] = path.relative_to(ROOT).as_posix()
        rows.append(payload)
    rows.sort(key=lambda item: str(item.get("created_at") or item.get("path") or ""), reverse=True)
    return rows


def _read_mirror_notes(mission_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = _mirror_dir(mission_id)
    if not root.exists():
        return rows
    for path in sorted((p for p in root.glob("*.json") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True):
        payload = _load_json(path)
        if not isinstance(payload, dict):
            continue
        summary = str(
            payload.get("summary")
            or payload.get("reflection")
            or payload.get("note")
            or payload.get("text")
            or payload.get("body")
            or ""
        ).strip()
        rows.append({
            "note_id": str(payload.get("note_id") or payload.get("reflection_id") or path.stem).strip(),
            "role": str(payload.get("role") or "spinetop-mirror").strip() or "spinetop-mirror",
            "kind": str(payload.get("kind") or "mirror_reflection").strip() or "mirror_reflection",
            "summary": summary,
            "created_at": str(payload.get("created_at") or payload.get("updated_at") or "").strip(),
            "path": path.relative_to(ROOT).as_posix(),
        })
    return rows


def _read_agent_runs(mission_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = _agent_runs_dir(mission_id)
    if not root.exists():
        return rows
    for path in sorted((p for p in root.glob("*.json") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True):
        payload = _load_json(path)
        if not isinstance(payload, dict):
            continue
        output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
        summary = str(
            payload.get("summary")
            or output.get("result")
            or payload.get("result")
            or ""
        ).strip()
        rows.append({
            "run_id": str(payload.get("run_id") or path.stem).strip(),
            "role": str(payload.get("role") or "").strip(),
            "role_label": str(payload.get("role_label") or "").strip(),
            "kind": str(payload.get("artifact_kind") or "agent_role_invocation").strip(),
            "summary": summary,
            "created_at": str(payload.get("created_at") or "").strip(),
            "path": path.relative_to(ROOT).as_posix(),
            "status": str(payload.get("status") or "").strip(),
            "trigger_reason": str(payload.get("trigger_reason") or "").strip(),
            "confidence": payload.get("confidence", output.get("confidence")),
            "next_step": str(payload.get("next_step") or output.get("next_step") or "").strip(),
        })
    return rows


def _read_prompt_translations(mission_id: str) -> list[dict[str, Any]]:
    if not PROMPT_TRANSLATOR_ACTIVE:
        return []
    return read_prompt_translations(normalize_mission_id(mission_id))


def _read_operator_interventions(mission_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in reversed(_read_jsonl(_intervention_log_path(mission_id))):
        action = str(payload.get("action") or "").strip()
        status = str(payload.get("status") or "").strip()
        if not action or not status:
            continue
        rows.append({
            "intervention_id": str(payload.get("intervention_id") or "").strip(),
            "action": action,
            "status": status,
            "reason": str(payload.get("reason") or "").strip(),
            "note": str(payload.get("note") or "").strip(),
            "blocked_reason": str(payload.get("blocked_reason") or "").strip(),
            "created_at": str(payload.get("created_at") or "").strip(),
            "changed_paths": [str(item).strip() for item in payload.get("changed_paths", []) if str(item).strip()],
        })
    return rows


def _append_operator_intervention(
    mission_id: str,
    *,
    action: str,
    status: str,
    reason: str = "",
    note: str = "",
    blocked_reason: str = "",
    changed_paths: list[str] | None = None,
) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    created_at = iso_now()
    action_text = str(action).strip()
    status_text = str(status).strip().lower() or "applied"
    record = {
        "intervention_id": f"intervention_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{_short_digest(f'{mission}|{action_text}|{created_at}')}",
        "mission_id": mission,
        "action": action_text,
        "status": status_text,
        "reason": str(reason).strip(),
        "note": str(note).strip(),
        "blocked_reason": str(blocked_reason).strip(),
        "created_at": created_at,
        "changed_paths": [str(item).strip() for item in (changed_paths or []) if str(item).strip()],
        "derived_only": True,
    }
    _append_jsonl(_intervention_log_path(mission, ensure=True), record)
    detail = record["blocked_reason"] or record["reason"] or action_text
    log_topology_event("operator_intervention", f"{mission}:{action_text}", status_text, detail[:240])
    return record


def _pending_runner_return_sync_count(mission_id: str, runner_returns: list[dict[str, Any]] | None = None) -> int:
    mission = normalize_mission_id(mission_id)
    rows = runner_returns if isinstance(runner_returns, list) else _read_runner_returns(mission)
    known_instance_ids = {
        str(item.get("instance_id") or "").strip()
        for item in rows
        if isinstance(item, dict) and str(item.get("instance_id") or "").strip()
    }
    pending = 0
    for instance in _iter_helper_instances():
        helper_type = str(instance.get("helper_type") or "").strip()
        if helper_type not in {"runner_helper_2b", "retrieval_helper_2b"}:
            continue
        status = str(instance.get("status") or "").strip()
        if status not in {"complete", "partial", "none_found", "blocked", "failed"}:
            continue
        instance_id = str(instance.get("helper_id") or "").strip()
        if not instance_id or instance_id in known_instance_ids:
            continue
        output_payload, _ = _load_helper_output(instance)
        if _linked_mission_id_for_helper(instance, output_payload) == mission:
            pending += 1
    return pending


def _sync_runner_returns(mission_id: str) -> list[dict[str, Any]]:
    mission = normalize_mission_id(mission_id)
    returns_dir = _runner_returns_dir(mission, ensure=True)
    existing = _read_runner_returns(mission)
    known_instance_ids = {
        str(item.get("instance_id") or "").strip()
        for item in existing
        if str(item.get("instance_id") or "").strip()
    }

    helper_instances = _iter_helper_instances()
    for instance in helper_instances:
        helper_type = str(instance.get("helper_type") or "").strip()
        if helper_type not in {"runner_helper_2b", "retrieval_helper_2b"}:
            continue
        if helper_type == "retrieval_helper_2b" and "query_scope" not in instance:
            continue
        status = str(instance.get("status") or "").strip()
        if status not in {"complete", "partial", "none_found", "blocked", "failed"}:
            continue
        instance_id = str(instance.get("helper_id") or "").strip()
        if not instance_id or instance_id in known_instance_ids:
            continue
        output_payload, source_ref = _load_helper_output(instance)
        linked_mission = _linked_mission_id_for_helper(instance, output_payload)
        if linked_mission != mission:
            continue
        packet = _build_runner_return_packet(mission, instance, output_payload, source_ref=source_ref)
        packet_path = returns_dir / f"{instance_id}.json"
        _write_json(packet_path, packet)
        known_instance_ids.add(instance_id)

    return _read_runner_returns(mission)


def _sync_runner_returns_result(mission_id: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    before = _read_runner_returns(mission)
    before_ids = {
        str(item.get("instance_id") or "").strip(): item
        for item in before
        if str(item.get("instance_id") or "").strip()
    }
    after = _sync_runner_returns(mission)
    created = [
        {
            "instance_id": instance_id,
            "path": str(item.get("path") or "").strip(),
        }
        for item in after
        if isinstance(item, dict)
        for instance_id in [str(item.get("instance_id") or "").strip()]
        if instance_id and instance_id not in before_ids
    ]
    created.sort(key=lambda item: str(item.get("instance_id") or ""))
    return {
        "mission_id": mission,
        "created_count": len(created),
        "created_instance_ids": [str(item.get("instance_id") or "").strip() for item in created],
        "created": created,
        "runner_return_count": len(after),
        "latest_runner_return": after[0] if after else None,
    }


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


def _default_parking_status(mission_id: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    return {
        "mission_id": mission,
        "status": "active",
        "reason": "",
        "parked_at": "",
        "parked_by": "",
        "resume_hint": "",
        "updated_at": "",
    }


def _read_parking_status(mission_id: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    path = _mission_parking_path(mission)
    if not path.exists():
        return _default_parking_status(mission)
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return _default_parking_status(mission)
    record = _default_parking_status(mission)
    record["mission_id"] = str(payload.get("mission_id") or mission).strip() or mission
    status = str(payload.get("status") or "active").strip().lower()
    record["status"] = status if status in {"active", "parked"} else "active"
    record["reason"] = str(payload.get("reason") or "").strip()
    record["parked_at"] = str(payload.get("parked_at") or "").strip()
    parked_by = str(payload.get("parked_by") or "").strip()
    record["parked_by"] = parked_by if parked_by in {"operator", "system_read_model"} else ""
    record["resume_hint"] = str(payload.get("resume_hint") or "").strip()
    record["updated_at"] = str(payload.get("updated_at") or "").strip()
    if record["status"] != "parked":
        record["parked_at"] = ""
    return record


def _write_parking_status(
    mission_id: str,
    *,
    status: str,
    reason: str = "",
    parked_by: str = "operator",
    resume_hint: str = "",
) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    normalized_status = "parked" if str(status).strip().lower() == "parked" else "active"
    existing = _read_parking_status(mission)
    record = {
        "mission_id": mission,
        "status": normalized_status,
        "reason": str(reason).strip(),
        "parked_at": str(existing.get("parked_at") or "") if normalized_status == "parked" else "",
        "parked_by": str(parked_by).strip() or "operator",
        "resume_hint": str(resume_hint).strip(),
        "updated_at": iso_now(),
    }
    if normalized_status == "parked" and not record["parked_at"]:
        record["parked_at"] = record["updated_at"]
    if normalized_status != "parked":
        record["parked_by"] = ""
    _write_json(_mission_parking_path(mission, ensure=True), record)
    return record


def _default_trigger_handoff(mission_id: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    return {
        "mission_id": mission,
        "trigger_id": "",
        "target_role": "",
        "allowed_action": "",
        "status": "idle",
        "reason": "",
        "policy_basis": "",
        "updated_at": "",
        "derived_only": True,
    }


def _default_retry_ledger(mission_id: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    return {
        "mission_id": mission,
        "retry_budget_total": RETRY_BUDGET_TOTAL,
        "retry_budget_used": 0,
        "last_retry_at": "",
        "last_retry_evidence": "",
        "last_failure_reason": "",
        "retry_reasons": [],
        "stop_reason": "",
        "decision_log": [],
        "updated_at": "",
        "derived_only": True,
    }


def _normalize_retry_log_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for entry in value[-RETRY_LOG_LIMIT:]:
        if not isinstance(entry, dict):
            continue
        items.append({
            "decided_at": str(entry.get("decided_at") or "").strip(),
            "trigger_id": str(entry.get("trigger_id") or "").strip(),
            "trigger_kind": str(entry.get("trigger_kind") or "").strip(),
            "decision": str(entry.get("decision") or "").strip(),
            "retry_reason": str(entry.get("retry_reason") or "").strip(),
            "why_retried": str(entry.get("why_retried") or "").strip(),
            "why_blocked": str(entry.get("why_blocked") or "").strip(),
            "budget_total": int(entry.get("budget_total") or 0),
            "budget_used_before": int(entry.get("budget_used_before") or 0),
            "budget_used_after": int(entry.get("budget_used_after") or 0),
            "stop_condition": str(entry.get("stop_condition") or "").strip(),
            "failure_reason": str(entry.get("failure_reason") or "").strip(),
            "evidence_fingerprint": str(entry.get("evidence_fingerprint") or "").strip(),
        })
    return items


def _read_retry_ledger(mission_id: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    path = _retry_ledger_path(mission)
    if not path.exists():
        return _default_retry_ledger(mission)
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return _default_retry_ledger(mission)
    record = _default_retry_ledger(mission)
    record["mission_id"] = str(payload.get("mission_id") or mission).strip() or mission
    try:
        budget_total = int(payload.get("retry_budget_total") or RETRY_BUDGET_TOTAL)
    except Exception:
        budget_total = RETRY_BUDGET_TOTAL
    if budget_total < 0:
        budget_total = RETRY_BUDGET_TOTAL
    try:
        budget_used = int(payload.get("retry_budget_used") or 0)
    except Exception:
        budget_used = 0
    if budget_used < 0:
        budget_used = 0
    record["retry_budget_total"] = budget_total
    record["retry_budget_used"] = min(budget_used, budget_total)
    record["last_retry_at"] = str(payload.get("last_retry_at") or "").strip()
    record["last_retry_evidence"] = str(payload.get("last_retry_evidence") or "").strip()
    record["last_failure_reason"] = str(payload.get("last_failure_reason") or "").strip()
    record["retry_reasons"] = [str(item).strip() for item in payload.get("retry_reasons", []) if str(item).strip()][:20]
    record["stop_reason"] = str(payload.get("stop_reason") or "").strip()
    record["decision_log"] = _normalize_retry_log_items(payload.get("decision_log"))
    record["updated_at"] = str(payload.get("updated_at") or "").strip()
    record["derived_only"] = bool(payload.get("derived_only", True))
    return record


def _write_retry_ledger(mission_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    record = _default_retry_ledger(mission)
    record.update(payload)
    record["mission_id"] = mission
    try:
        record["retry_budget_total"] = max(0, int(record.get("retry_budget_total") or RETRY_BUDGET_TOTAL))
    except Exception:
        record["retry_budget_total"] = RETRY_BUDGET_TOTAL
    try:
        record["retry_budget_used"] = max(0, int(record.get("retry_budget_used") or 0))
    except Exception:
        record["retry_budget_used"] = 0
    record["retry_budget_used"] = min(record["retry_budget_used"], record["retry_budget_total"])
    record["retry_reasons"] = [str(item).strip() for item in record.get("retry_reasons", []) if str(item).strip()][:20]
    record["decision_log"] = _normalize_retry_log_items(record.get("decision_log"))
    record["updated_at"] = str(record.get("updated_at") or iso_now())
    record["derived_only"] = True
    _write_json(_retry_ledger_path(mission, ensure=True), record)
    return record


def _read_trigger_handoff(mission_id: str) -> dict[str, Any]:
    path = _trigger_handoff_path(mission_id)
    if not path.exists():
        return _default_trigger_handoff(mission_id)
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return _default_trigger_handoff(mission_id)
    record = _default_trigger_handoff(mission_id)
    for key in record:
        if key == "derived_only":
            record[key] = bool(payload.get(key, True))
        else:
            record[key] = payload.get(key, record[key])
    return record


def _write_trigger_handoff(mission_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    record = _default_trigger_handoff(mission_id)
    record.update(payload)
    record["mission_id"] = normalize_mission_id(mission_id)
    record["updated_at"] = str(record.get("updated_at") or iso_now())
    record["derived_only"] = True
    _write_json(_trigger_handoff_path(mission_id, ensure=True), record)
    return record


def _has_first_pass_attempt(detail: dict[str, Any]) -> bool:
    current_state = str(detail.get("current_state") or "").strip()
    if current_state in {
        "RELEASE_REQUESTED",
        "RELEASE_PREPARED",
        "EXPEDITION_ACTIVE",
        "WAREHOUSE_INTAKE",
        "WAREHOUSE_PROCESSING",
        "CITADEL_REVIEW_LOOP",
        "PACKAGE_READY",
        "BRIDGE_CONSIDERATION",
        "MISSION_CLOSED",
        "ARCHIVE_REVIEW",
    }:
        return True
    return bool(detail.get("latest_hermes_run") or detail.get("manifest"))


def _read_trigger_records(mission_id: str) -> list[dict[str, Any]]:
    directory = _triggers_dir(mission_id)
    if not directory.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted((p for p in directory.glob("*.json") if p.is_file() and p.name != TRIGGER_HANDOFF_FILENAME), key=lambda p: p.stat().st_mtime, reverse=True):
        payload = _load_json(path)
        if not isinstance(payload, dict):
            continue
        record = dict(payload)
        record["path"] = path.relative_to(ROOT).as_posix()
        records.append(record)
    return records


def _count_consumed_trigger_action(mission_id: str, allowed_action: str) -> int:
    return sum(
        1
        for record in _read_trigger_records(mission_id)
        if str(record.get("status") or "") in {"pending", "consumed"} and str(record.get("allowed_action") or "") == allowed_action
    )


def _has_pending_or_active_trigger_action(mission_id: str, allowed_action: str) -> bool:
    if not allowed_action:
        return False
    for record in _read_trigger_records(mission_id):
        if str(record.get("status") or "").strip() not in {"pending", "active"}:
            continue
        if str(record.get("allowed_action") or "").strip() == allowed_action:
            return True
    return False


def _has_pending_or_active_first_pass_intent(mission_id: str) -> bool:
    allowed_action = "start_first_pass_expedition"
    if _has_pending_or_active_trigger_action(mission_id, allowed_action):
        return True
    handoff = _read_trigger_handoff(mission_id)
    return (
        str(handoff.get("allowed_action") or "").strip() == allowed_action
        and str(handoff.get("status") or "").strip() in {"pending", "active"}
    )


def _retry_failure_signature(latest_runner_return: dict[str, Any] | None) -> str:
    if not isinstance(latest_runner_return, dict):
        return ""
    parts = [
        str(latest_runner_return.get("summary") or "").strip(),
        str(latest_runner_return.get("recommended_next_step") or "").strip(),
    ]
    open_questions = latest_runner_return.get("open_questions")
    if isinstance(open_questions, list):
        parts.extend(str(item).strip() for item in open_questions[:4] if str(item).strip())
    return " | ".join(part for part in parts if part)


def _retry_evidence_fingerprint(detail: dict[str, Any], latest_runner_return: dict[str, Any] | None = None) -> str:
    latest_input = None
    mission_inputs = detail.get("mission_inputs")
    if isinstance(mission_inputs, list) and mission_inputs:
        latest_input = mission_inputs[0] if isinstance(mission_inputs[0], dict) else None
    pieces = [
        str((latest_input or {}).get("input_id") or "").strip(),
        str((latest_input or {}).get("created_at") or "").strip(),
        str((latest_runner_return or {}).get("instance_id") or "").strip(),
        str((latest_runner_return or {}).get("created_at") or "").strip(),
        str((latest_runner_return or {}).get("path") or (latest_runner_return or {}).get("source_ref") or "").strip(),
    ]
    return "|".join(piece for piece in pieces if piece)


def _suggests_retry(latest_runner_return: dict[str, Any] | None) -> bool:
    if not isinstance(latest_runner_return, dict):
        return False
    text = " ".join([
        str(latest_runner_return.get("summary") or "").strip(),
        str(latest_runner_return.get("recommended_next_step") or "").strip(),
        " ".join(str(item).strip() for item in latest_runner_return.get("open_questions", []) if str(item).strip()) if isinstance(latest_runner_return.get("open_questions"), list) else "",
    ]).lower()
    return any(token in text for token in ["retry", "follow-up", "follow up", "replacement", "another bounded", "refine"])


def _is_missing_artifact_block(detail: dict[str, Any], latest_runner_return: dict[str, Any] | None = None) -> bool:
    working_memory = detail.get("working_memory") if isinstance(detail.get("working_memory"), dict) else {}
    text = " ".join([
        str(working_memory.get("blocked_reason") or "").strip(),
        str((latest_runner_return or {}).get("summary") or "").strip(),
        str((latest_runner_return or {}).get("recommended_next_step") or "").strip(),
        " ".join(str(item).strip() for item in latest_runner_return.get("open_questions", []) if str(item).strip()) if isinstance((latest_runner_return or {}).get("open_questions"), list) else "",
    ]).lower()
    return any(token in text for token in ["missing artifact", "missing file", "missing receipt", "missing evidence bundle", "artifact missing"])


def _classify_retry_reason(detail: dict[str, Any], ledger: dict[str, Any], reason: str) -> tuple[str, str, str]:
    latest_runner_return = detail.get("latest_runner_return") if isinstance(detail.get("latest_runner_return"), dict) else None
    mission_inputs = detail.get("mission_inputs")
    latest_input = mission_inputs[0] if isinstance(mission_inputs, list) and mission_inputs and isinstance(mission_inputs[0], dict) else None
    last_retry_at = str(ledger.get("last_retry_at") or "").strip()
    latest_input_at = str((latest_input or {}).get("created_at") or "").strip()
    if latest_input_at and (not last_retry_at or latest_input_at > last_retry_at):
        return (
            "missing_input_now_provided",
            "new mission input arrived after the previous retry decision",
            _retry_evidence_fingerprint(detail, latest_runner_return),
        )
    if _suggests_retry(latest_runner_return):
        return (
            "runner_suggested_retry",
            "latest runner return suggested one bounded follow-up attempt",
            _retry_evidence_fingerprint(detail, latest_runner_return),
        )
    normalized_reason = " ".join(reason.strip().lower().split())
    if "refresh" in normalized_reason:
        return (
            "role_specific_bounded_refresh",
            "operator requested a bounded refresh for the mission-local role",
            _retry_evidence_fingerprint(detail, latest_runner_return),
        )
    return (
        "operator_requested_retry",
        "operator explicitly requested one bounded retry",
        _retry_evidence_fingerprint(detail, latest_runner_return),
    )


def _build_retry_decision(
    mission_id: str,
    *,
    trigger_kind: str,
    reason: str,
    detail: dict[str, Any],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    latest_runner_return = detail.get("latest_runner_return") if isinstance(detail.get("latest_runner_return"), dict) else None
    parking_status = detail.get("parking_status") if isinstance(detail.get("parking_status"), dict) else {}
    parked = str(parking_status.get("status") or "active").strip() == "parked"
    retry_reason, why_retried, evidence_fingerprint = _classify_retry_reason(detail, ledger, reason)
    failure_reason = _retry_failure_signature(latest_runner_return)
    budget_total = int(ledger.get("retry_budget_total") or RETRY_BUDGET_TOTAL)
    budget_used = int(ledger.get("retry_budget_used") or 0)
    stop_condition = ""
    why_blocked = ""
    allowed = True

    if parked:
        allowed = False
        stop_condition = "mission_parked_retry_frozen"
        why_blocked = "retry frozen while mission is parked"
    elif trigger_kind != "operator_refresh_requested":
        allowed = False
        stop_condition = "retry_not_applicable"
        why_blocked = "retry policy only applies to mission-local refresh retries"
    elif budget_used >= budget_total:
        allowed = False
        stop_condition = "retry_budget_exhausted"
        why_blocked = "retry budget exhausted"
    elif _is_missing_artifact_block(detail, latest_runner_return):
        allowed = False
        stop_condition = "mission_blocked_on_missing_artifact"
        why_blocked = "mission is blocked on a missing artifact"
    elif (
        failure_reason
        and str(ledger.get("last_failure_reason") or "").strip() == failure_reason
        and str(ledger.get("last_retry_evidence") or "").strip() == evidence_fingerprint
    ):
        allowed = False
        stop_condition = "repeated_same_failure_without_new_evidence"
        why_blocked = "same failure reason repeated without new evidence"

    decision = {
        "mission_id": mission,
        "allowed": allowed,
        "retry_reason": retry_reason,
        "why_retried": why_retried,
        "why_blocked": why_blocked,
        "failure_reason": failure_reason,
        "evidence_fingerprint": evidence_fingerprint,
        "budget_total": budget_total,
        "budget_used_before": budget_used,
        "budget_used_after": budget_used + 1 if allowed else budget_used,
        "stop_condition": stop_condition,
    }
    return decision


def _apply_retry_decision(
    mission_id: str,
    *,
    trigger_id: str,
    trigger_kind: str,
    decision: dict[str, Any],
) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    ledger = _read_retry_ledger(mission)
    budget_total = int(ledger.get("retry_budget_total") or RETRY_BUDGET_TOTAL)
    budget_used_before = int(decision.get("budget_used_before") or 0)
    budget_used_after = int(decision.get("budget_used_after") or budget_used_before)
    allowed = bool(decision.get("allowed"))
    log_entry = {
        "decided_at": iso_now(),
        "trigger_id": trigger_id,
        "trigger_kind": trigger_kind,
        "decision": "allowed" if allowed else "blocked",
        "retry_reason": str(decision.get("retry_reason") or "").strip(),
        "why_retried": str(decision.get("why_retried") or "").strip(),
        "why_blocked": str(decision.get("why_blocked") or "").strip(),
        "budget_total": budget_total,
        "budget_used_before": budget_used_before,
        "budget_used_after": budget_used_after,
        "stop_condition": str(decision.get("stop_condition") or "").strip(),
        "failure_reason": str(decision.get("failure_reason") or "").strip(),
        "evidence_fingerprint": str(decision.get("evidence_fingerprint") or "").strip(),
    }

    updated = dict(ledger)
    decision_log = list(ledger.get("decision_log") or [])
    decision_log.append(log_entry)
    updated["decision_log"] = decision_log[-RETRY_LOG_LIMIT:]
    updated["updated_at"] = log_entry["decided_at"]
    if allowed:
        updated["retry_budget_used"] = min(budget_used_after, budget_total)
        updated["last_retry_at"] = log_entry["decided_at"]
        updated["last_retry_evidence"] = log_entry["evidence_fingerprint"]
        updated["last_failure_reason"] = log_entry["failure_reason"]
        retry_reasons = list(ledger.get("retry_reasons") or [])
        retry_reasons.append(log_entry["retry_reason"])
        updated["retry_reasons"] = retry_reasons[-20:]
        updated["stop_reason"] = "retry_budget_exhausted" if updated["retry_budget_used"] >= budget_total else ""
    elif log_entry["stop_condition"]:
        updated["stop_reason"] = log_entry["stop_condition"]
    return _write_retry_ledger(mission, updated)


def _evaluate_trigger_record(
    mission_id: str,
    *,
    trigger_kind: str,
    reason: str,
    source: str,
) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    spec = ALLOWED_TRIGGER_KINDS.get(trigger_kind) or {}
    detail = _build_expedition_detail(mission)
    ledger = _read_retry_ledger(mission)
    parking_status = detail.get("parking_status") if isinstance(detail.get("parking_status"), dict) else {}
    parked = str(parking_status.get("status") or "active") == "parked"
    return_all = read_return_all_state()
    nanny = read_nanny_state()
    summary = detail.get("mission_summary") if isinstance(detail.get("mission_summary"), dict) else {}
    working_memory = detail.get("working_memory") if isinstance(detail.get("working_memory"), dict) else {}
    conditions: list[str] = []
    allowed = True
    blocked_reason = ""
    retry_decision: dict[str, Any] | None = None
    guardrail = evaluate_autonomy_guardrails(
        mission_id=mission,
        trigger_kind=trigger_kind,
        target_role=str(spec.get("target_role") or ""),
        allowed_action=str(spec.get("allowed_action") or ""),
        policy_basis=str(spec.get("policy_basis") or ""),
        trigger_reason=reason,
        trigger_source=source,
        retry_budget_total=int(ledger.get("retry_budget_total") or RETRY_BUDGET_TOTAL),
        retry_budget_used=int(ledger.get("retry_budget_used") or 0),
        return_all_enabled=bool(return_all.get("enabled")),
        nanny_cooling=str(nanny.get("temperature") or "cool") in {"warm", "hot"} or bool(nanny.get("cooldown_active")),
        parked=parked,
        allow_while_parked=bool(spec.get("allow_while_parked")),
        counts_against_retry_budget=bool(spec.get("counts_against_retry_budget")),
        summary=summary,
        working_memory=working_memory,
        write_targets=[str(item).strip() for item in spec.get("write_targets", []) if str(item).strip()],
    )
    if guardrail.get("status") == "blocked":
        allowed = False
        blocked_reason = str(guardrail.get("reason") or "").strip()
        guardrail_checks = guardrail.get("checks") if isinstance(guardrail.get("checks"), list) else []
        for check in guardrail_checks:
            if not isinstance(check, dict) or bool(check.get("ok")):
                continue
            code = str(check.get("code") or "").strip()
            if code:
                conditions.append(code)

    if not reason.strip():
        allowed = False
        blocked_reason = blocked_reason or "blocked by invalid trigger policy"
        conditions.append("trigger_policy_invalid")
    if spec.get("requires_do_now") and str(summary.get("triage_bucket") or "") != "do_now":
        allowed = False
        blocked_reason = blocked_reason or "blocked by mission not marked do_now"
        conditions.append("not_do_now")
    if spec.get("requires_first_pass_open") and _has_first_pass_attempt(detail):
        allowed = False
        blocked_reason = blocked_reason or "blocked by existing first-pass expedition attempt"
        conditions.append("first_pass_already_attempted")
    if trigger_kind == "do_now_first_pass_requested" and _has_pending_or_active_first_pass_intent(mission):
        allowed = False
        blocked_reason = "first-pass already pending"
        conditions.append("first_pass_already_pending")
    if spec.get("counts_against_retry_budget"):
        retry_decision = _build_retry_decision(
            mission,
            trigger_kind=trigger_kind,
            reason=reason,
            detail=detail,
            ledger=ledger,
        )
        if not allowed:
            retry_decision["allowed"] = False
            retry_decision["budget_used_after"] = int(retry_decision.get("budget_used_before") or 0)
            retry_decision["why_blocked"] = blocked_reason or str(retry_decision.get("why_blocked") or "retry blocked")
            retry_decision["stop_condition"] = conditions[0] if conditions else str(retry_decision.get("stop_condition") or "")
        elif not bool(retry_decision.get("allowed")):
            allowed = False
            blocked_reason = blocked_reason or str(retry_decision.get("why_blocked") or "retry blocked")
            stop_condition = str(retry_decision.get("stop_condition") or "").strip()
            conditions.append(stop_condition or "retry_blocked")

    policy_condition = "trigger_allowed" if allowed else (conditions[0] if conditions else "trigger_blocked")
    evaluation = {
        "evaluated_at": iso_now(),
        "allowed": allowed,
        "decision": "allowed" if allowed else "blocked",
        "policy_condition": policy_condition,
        "policy_conditions": conditions or [policy_condition],
        "allowed_reason": "trigger allowed under minimal policy" if allowed else "",
        "blocked_reason": blocked_reason if not allowed else "",
        "reason": "trigger allowed under minimal policy" if allowed else blocked_reason,
        "guardrails": guardrail,
        "retry_policy": {
            "budget_total": int(ledger.get("retry_budget_total") or RETRY_BUDGET_TOTAL),
            "budget_used": int(ledger.get("retry_budget_used") or 0),
            "budget_remaining": max(0, int(ledger.get("retry_budget_total") or RETRY_BUDGET_TOTAL) - int(ledger.get("retry_budget_used") or 0)),
            "stop_reason": str(ledger.get("stop_reason") or "").strip(),
            "decision": retry_decision or {},
        },
    }
    handoff = {
        "mission_id": mission,
        "target_role": str(spec.get("target_role") or ""),
        "allowed_action": str(spec.get("allowed_action") or ""),
        "status": "pending" if allowed else "blocked",
        "reason": reason.strip(),
        "policy_basis": str(spec.get("policy_basis") or ""),
        "updated_at": evaluation["evaluated_at"],
        "derived_only": True,
    }
    return {
        "evaluation": evaluation,
        "handoff": handoff,
        "spec": spec,
    }


def _create_trigger_record(
    mission_id: str,
    *,
    trigger_kind: str,
    reason: str,
    source: str,
) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    with _mission_trigger_lock(mission):
        evaluated = _evaluate_trigger_record(mission, trigger_kind=trigger_kind, reason=reason, source=source)
        spec = evaluated["spec"]
        evaluation = evaluated["evaluation"]
        created_at = iso_now()
        trigger_id = f"trigger_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{_short_digest(f'{mission}|{trigger_kind}|{source}|{created_at}')}"
        record = {
            "trigger_id": trigger_id,
            "mission_id": mission,
            "created_at": created_at,
            "trigger_kind": trigger_kind,
            "reason": reason.strip(),
            "source": source.strip(),
            "target_role": str(spec.get("target_role") or ""),
            "allowed_action": str(spec.get("allowed_action") or ""),
            "policy_basis": str(spec.get("policy_basis") or ""),
            "status": "pending" if evaluation["allowed"] else "blocked",
            "derived_only": True,
            "evaluation": evaluation,
        }
        path = _triggers_dir(mission, ensure=True) / f"{trigger_id}.json"
        retry_ledger = None
        if bool(spec.get("counts_against_retry_budget")):
            retry_decision = evaluation.get("retry_policy")
            retry_decision_payload = retry_decision.get("decision") if isinstance(retry_decision, dict) else None
            if isinstance(retry_decision_payload, dict):
                retry_ledger = _apply_retry_decision(
                    mission,
                    trigger_id=trigger_id,
                    trigger_kind=trigger_kind,
                    decision=retry_decision_payload,
                )
                record["evaluation"] = {
                    **evaluation,
                    "retry_policy": {
                        **(retry_decision if isinstance(retry_decision, dict) else {}),
                        "budget_used": int(retry_ledger.get("retry_budget_used") or 0),
                        "budget_remaining": max(
                            0,
                            int(retry_ledger.get("retry_budget_total") or RETRY_BUDGET_TOTAL) - int(retry_ledger.get("retry_budget_used") or 0),
                        ),
                        "stop_reason": str(retry_ledger.get("stop_reason") or "").strip(),
                    },
                }
        _write_json(path, record)
        if evaluation["allowed"]:
            _write_trigger_handoff(
                mission,
                {
                    "trigger_id": trigger_id,
                    "target_role": record["target_role"],
                    "allowed_action": record["allowed_action"],
                    "status": "pending",
                    "reason": record["reason"],
                    "policy_basis": record["policy_basis"],
                },
            )
        return {
            **record,
            "path": path.relative_to(ROOT).as_posix(),
            "retry_ledger": retry_ledger,
            "handoff": {
                **evaluated["handoff"],
                "trigger_id": trigger_id,
            },
        }


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


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in items:
            items.append(text)
    return items


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            items.append(item)
    return items


def _normalize_question_text(text: str) -> str:
    return " ".join(str(text).strip().lower().split())


def _extract_confirmed_fact_items(text: str, *, source: str, created_at: str) -> list[dict[str, str]]:
    lowered = text.lower()
    facts: list[dict[str, str]] = []
    if any(token in lowered for token in ["production", "prod"]):
        facts.append({"text": "Environment confirmed: production.", "source": source, "created_at": created_at})
    if "staging" in lowered:
        facts.append({"text": "Environment confirmed: staging.", "source": source, "created_at": created_at})
    if "window" in lowered:
        facts.append({"text": "A timing window was provided.", "source": source, "created_at": created_at})
    if "objective" in lowered:
        facts.append({"text": "The mission objective was restated.", "source": source, "created_at": created_at})
    if "scope" in lowered:
        facts.append({"text": "The mission scope was clarified.", "source": source, "created_at": created_at})
    if "link" in lowered or "url" in lowered:
        facts.append({"text": "A reference link or URL was provided.", "source": source, "created_at": created_at})
    if "outcome" in lowered or "result" in lowered:
        facts.append({"text": "The desired outcome was stated.", "source": source, "created_at": created_at})
    return facts


def _assumption_items_from_packet(latest_packet: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(latest_packet, dict):
        return []
    assumptions = latest_packet.get("assumptions")
    if not isinstance(assumptions, list):
        return []
    items: list[dict[str, Any]] = []
    for index, assumption in enumerate(assumptions[:4]):
        if not isinstance(assumption, dict):
            continue
        statement = str(assumption.get("statement") or "").strip()
        if not statement:
            continue
        items.append({
            "assumption_id": str(assumption.get("assumption_id") or f"assumption_{index + 1}"),
            "statement": statement,
            "confidence": float(assumption.get("confidence") or 0.0),
            "source": str(assumption.get("source") or "Sentinel result"),
            "type": str(assumption.get("type") or "default"),
            "reason": "Provisional assumption carried forward from the latest clarification packet.",
        })
    return items


def _default_assumption_ledger(mission_id: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    return {
        "mission_id": mission,
        "derived_only": True,
        "updated_at": "",
        "entries": [],
    }


def _normalize_assumption_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in {"active", "accepted", "rejected", "invalidated", "resolved"}:
        return status
    return "active"


def _normalize_operator_assumption_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in {"unreviewed", "accepted", "rejected"}:
        return status
    return "unreviewed"


def _normalize_basis_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if not isinstance(value, list):
        return refs
    for item in value:
        text = str(item or "").strip()
        if text and text not in refs:
            refs.append(text)
    return refs[:8]


def _normalize_invalidation_triggers(value: Any) -> list[str]:
    triggers: list[str] = []
    if not isinstance(value, list):
        return triggers
    for item in value:
        text = str(item or "").strip()
        if text and text not in triggers:
            triggers.append(text)
    return triggers[:6]


def _normalize_assumption_entry(mission_id: str, payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    mission = normalize_mission_id(mission_id)
    text = str(payload.get("text") or payload.get("statement") or "").strip()
    if not text:
        return None
    assumption_id = str(payload.get("assumption_id") or f"assumption_{_short_digest(f'{mission}|{text.lower()}')}").strip()
    created_at = str(payload.get("created_at") or "").strip() or iso_now()
    updated_at = str(payload.get("updated_at") or "").strip() or created_at
    raw_confidence = payload.get("confidence")
    confidence = 0.0
    if isinstance(raw_confidence, (int, float)):
        confidence = max(0.0, min(1.0, float(raw_confidence)))
    confirmation_payload = payload.get("confirmation") if isinstance(payload.get("confirmation"), dict) else {}
    operator_status = _normalize_operator_assumption_status(confirmation_payload.get("operator_status"))
    status = _normalize_assumption_status(payload.get("status"))
    if operator_status == "accepted":
        status = "accepted"
    elif operator_status == "rejected":
        status = "rejected"
    return {
        "assumption_id": assumption_id,
        "mission_id": mission,
        "created_at": created_at,
        "updated_at": updated_at,
        "text": text,
        "reason": str(payload.get("reason") or "").strip(),
        "confidence": round(confidence, 2),
        "basis_refs": _normalize_basis_refs(payload.get("basis_refs")),
        "invalidation_triggers": _normalize_invalidation_triggers(payload.get("invalidation_triggers")),
        "status": status,
        "confirmation": {
            "operator_status": operator_status,
            "operator_note": str(confirmation_payload.get("operator_note") or "").strip(),
            "operator_updated_at": str(confirmation_payload.get("operator_updated_at") or "").strip(),
        },
        "derived_only": True,
    }


def _assumption_sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
    status = str(item.get("status") or "").strip()
    priority = 0 if status in {"active", "accepted"} else 1 if status == "invalidated" else 2
    return (priority, str(item.get("updated_at") or ""), str(item.get("assumption_id") or ""))


def _sorted_assumption_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(entries, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    rows.sort(key=lambda item: 0 if str(item.get("status") or "").strip() in {"active", "accepted"} else 1 if str(item.get("status") or "").strip() == "invalidated" else 2)
    return rows


def _read_assumption_ledger_entries(mission_id: str) -> list[dict[str, Any]]:
    mission = normalize_mission_id(mission_id)
    path = _assumption_ledger_path(mission)
    if not path.exists():
        return []
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return []
    rows = payload.get("entries")
    if not isinstance(rows, list):
        return []
    entries: list[dict[str, Any]] = []
    for row in rows:
        item = _normalize_assumption_entry(mission, row)
        if item:
            entries.append(item)
    return _sorted_assumption_entries(entries)


def _write_assumption_ledger_entries(mission_id: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mission = normalize_mission_id(mission_id)
    normalized: list[dict[str, Any]] = []
    for item in entries:
        row = _normalize_assumption_entry(mission, item)
        if row:
            normalized.append(row)
    normalized = _sorted_assumption_entries(normalized)
    _write_json(
        _assumption_ledger_path(mission, ensure=True),
        {
            "mission_id": mission,
            "derived_only": True,
            "updated_at": iso_now(),
            "entry_count": len(normalized),
            "entries": normalized,
        },
    )
    return normalized


def _assumption_display_items(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in entries:
        status = str(item.get("status") or "").strip()
        if status not in {"active", "accepted"}:
            continue
        items.append({
            "assumption_id": str(item.get("assumption_id") or ""),
            "statement": str(item.get("text") or "").strip(),
            "confidence": item.get("confidence"),
            "source": "mission-local ledger",
            "type": "ledger",
            "reason": str(item.get("reason") or "").strip(),
            "status": status,
            "operator_status": str(((item.get("confirmation") or {}) if isinstance(item.get("confirmation"), dict) else {}).get("operator_status") or "unreviewed"),
        })
    return items[:4]


def _assumptions_last_updated(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return ""
    return max(str(item.get("updated_at") or item.get("created_at") or "") for item in entries)


def _latest_assumption_changes(entries: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    rows = sorted(entries, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    changes: list[dict[str, Any]] = []
    for item in rows[:limit]:
        changes.append({
            "assumption_id": str(item.get("assumption_id") or ""),
            "text": str(item.get("text") or "").strip(),
            "status": str(item.get("status") or "").strip(),
            "updated_at": str(item.get("updated_at") or "").strip(),
            "operator_status": str(((item.get("confirmation") or {}) if isinstance(item.get("confirmation"), dict) else {}).get("operator_status") or "unreviewed"),
        })
    return changes


def _assumption_basis_seed(
    mission_id: str,
    mission_inputs: list[dict[str, Any]],
    mission_chat: list[dict[str, Any]],
    latest_packet_ref: str,
    latest_runner_return: dict[str, Any] | None,
) -> list[str]:
    refs: list[str] = []
    brief_path = _mission_root(mission_id) / "mission_brief.json"
    if brief_path.exists():
        refs.append(brief_path.relative_to(ROOT).as_posix())
    if latest_packet_ref:
        refs.append(latest_packet_ref)
    for item in mission_inputs[:2]:
        ref = str(item.get("path") or "").strip()
        if ref and ref not in refs:
            refs.append(ref)
    for item in mission_chat[:2]:
        message_id = str(item.get("message_id") or "").strip()
        if not message_id:
            continue
        ref = f"{_mission_chat_path(mission_id).relative_to(ROOT).as_posix()}#{message_id}"
        if ref not in refs:
            refs.append(ref)
    if isinstance(latest_runner_return, dict):
        ref = str(latest_runner_return.get("path") or latest_runner_return.get("source_ref") or "").strip()
        if ref and ref not in refs:
            refs.append(ref)
    return refs[:6]


def _derive_assumption_candidates(
    mission_id: str,
    *,
    objective: str,
    current_state: str,
    latest_packet: dict[str, Any] | None,
    latest_runner_return: dict[str, Any] | None,
    mission_inputs: list[dict[str, Any]],
    mission_chat: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sufficient_to_proceed, _ = _is_sufficient_to_proceed(
        objective,
        mission_inputs,
        current_state,
        latest_packet,
    )
    if not sufficient_to_proceed:
        return []

    now = iso_now()
    packet_ref = _latest_index_path_ref(mission_id, "clarification_packet")
    base_refs = _assumption_basis_seed(mission_id, mission_inputs, mission_chat, packet_ref, latest_runner_return)
    entries: list[dict[str, Any]] = []

    for item in _assumption_items_from_packet(latest_packet)[:2]:
        text = str(item.get("statement") or "").strip()
        if not text:
            continue
        entries.append({
            "assumption_id": f"assumption_{_short_digest(f'{mission_id}|{text.lower()}')}",
            "mission_id": mission_id,
            "created_at": now,
            "updated_at": now,
            "text": text,
            "reason": str(item.get("reason") or "Provisional assumption carried forward from a mission-local clarification artifact.").strip(),
            "confidence": round(max(0.2, min(0.95, float(item.get("confidence") or 0.45))), 2),
            "basis_refs": base_refs or ([packet_ref] if packet_ref else []),
            "invalidation_triggers": [
                "The operator provides a more specific direction.",
                "A newer mission-local artifact contradicts this assumption.",
            ],
            "status": "active",
            "confirmation": {
                "operator_status": "unreviewed",
                "operator_note": "",
                "operator_updated_at": "",
            },
            "derived_only": True,
        })

    if entries:
        return entries[:3]

    objective_normalized = _normalize_mission_objective(objective)
    fallback_text = ""
    fallback_reason = ""
    fallback_confidence = 0.0
    fallback_triggers = [
        "The operator specifies a narrower scope or environment.",
        "A mission-local artifact contradicts this assumption.",
    ]
    if "python" in objective_normalized and "csv" in objective_normalized:
        fallback_text = "Assuming a standard Python 3 environment with file-based CSV input and output expectations."
        fallback_reason = "The mission brief reads like a general coding request and does not specify a custom runtime, framework, or data transport."
        fallback_confidence = 0.58
        fallback_triggers = [
            "The operator specifies a different runtime, framework, or execution target.",
            "The operator provides a non-file CSV source or output contract.",
        ]
    elif any(token in objective_normalized for token in ["dog", "obedience", "puppy", "sit", "stay", "training"]):
        fallback_text = "Assuming a general beginner household obedience context."
        fallback_reason = "The mission brief reads like general guidance rather than a specialized veterinary or behavioral emergency case."
        fallback_confidence = 0.56
        fallback_triggers = [
            "The operator specifies an advanced training context or a behavioral issue.",
            "The operator provides breed, age, or environment constraints that change the approach.",
        ]
    elif _is_general_instruction_task(objective):
        fallback_text = "Assuming the mission is asking for a general-purpose example rather than a production-integrated implementation."
        fallback_reason = "The mission brief is already sufficient to proceed, but it does not specify a deployment environment or system-specific constraints."
        fallback_confidence = 0.48

    if not fallback_text:
        return []

    return [{
        "assumption_id": f"assumption_{_short_digest(f'{mission_id}|{fallback_text.lower()}')}",
        "mission_id": mission_id,
        "created_at": now,
        "updated_at": now,
        "text": fallback_text,
        "reason": fallback_reason,
        "confidence": fallback_confidence,
        "basis_refs": base_refs,
        "invalidation_triggers": fallback_triggers,
        "status": "active",
        "confirmation": {
            "operator_status": "unreviewed",
            "operator_note": "",
            "operator_updated_at": "",
        },
        "derived_only": True,
    }]


def _refresh_assumption_ledger(mission_id: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    detail = _build_expedition_detail(mission)
    derived = _derive_assumption_candidates(
        mission,
        objective=str(detail.get("objective") or "").strip(),
        current_state=str(detail.get("current_state") or "").strip(),
        latest_packet=detail.get("latest_clarification_packet") if isinstance(detail.get("latest_clarification_packet"), dict) else None,
        latest_runner_return=detail.get("latest_runner_return") if isinstance(detail.get("latest_runner_return"), dict) else None,
        mission_inputs=_dict_list(detail.get("mission_inputs")),
        mission_chat=_dict_list(detail.get("mission_chat")),
    )
    existing = _read_assumption_ledger_entries(mission)
    existing_by_id = {str(item.get("assumption_id") or ""): item for item in existing}
    now = iso_now()
    refreshed: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in derived:
        assumption_id = str(item.get("assumption_id") or "").strip()
        previous = existing_by_id.get(assumption_id)
        confirmation = dict((previous or {}).get("confirmation") or {})
        operator_status = _normalize_operator_assumption_status(confirmation.get("operator_status"))
        status = "accepted" if operator_status == "accepted" else "rejected" if operator_status == "rejected" else "active"
        refreshed.append({
            **item,
            "created_at": str((previous or {}).get("created_at") or item.get("created_at") or now),
            "updated_at": now,
            "status": status,
            "confirmation": {
                "operator_status": operator_status,
                "operator_note": str(confirmation.get("operator_note") or "").strip(),
                "operator_updated_at": str(confirmation.get("operator_updated_at") or "").strip(),
            },
            "derived_only": True,
        })
        seen_ids.add(assumption_id)

    for item in existing:
        assumption_id = str(item.get("assumption_id") or "").strip()
        if not assumption_id or assumption_id in seen_ids:
            continue
        status = str(item.get("status") or "").strip()
        if status in {"active", "accepted"}:
            updated = dict(item)
            updated["status"] = "resolved"
            updated["updated_at"] = now
            refreshed.append(updated)
        else:
            refreshed.append(item)

    written = _write_assumption_ledger_entries(mission, refreshed)
    return {
        "mission_id": mission,
        "ledger_path": _assumption_ledger_path(mission, ensure=True).relative_to(ROOT).as_posix(),
        "derived_count": len(derived),
        "assumption_count": len(written),
        "active_assumption_count": len([item for item in written if str(item.get("status") or "") in {"active", "accepted"}]),
        "entries": written,
    }


def _update_assumption_confirmation(mission_id: str, assumption_id: str, *, operator_status: str, operator_note: str = "") -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    target_id = str(assumption_id or "").strip()
    entries = _read_assumption_ledger_entries(mission)
    updated_entries: list[dict[str, Any]] = []
    target: dict[str, Any] | None = None
    now = iso_now()
    for item in entries:
        if str(item.get("assumption_id") or "").strip() != target_id:
            updated_entries.append(item)
            continue
        confirmation_status = _normalize_operator_assumption_status(operator_status)
        updated = dict(item)
        updated["updated_at"] = now
        updated["status"] = "accepted" if confirmation_status == "accepted" else "rejected"
        updated["confirmation"] = {
            "operator_status": confirmation_status,
            "operator_note": str(operator_note or "").strip(),
            "operator_updated_at": now,
        }
        updated_entries.append(updated)
        target = updated
    if target is None:
        raise FileNotFoundError("assumption not found")
    _write_assumption_ledger_entries(mission, updated_entries)
    return target


def _question_items_from_packet(latest_packet: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(latest_packet, dict):
        return []
    ranked = latest_packet.get("clarifying_questions_ranked")
    if not isinstance(ranked, list):
        return []
    items: list[dict[str, Any]] = []
    for index, question in enumerate(ranked[:4]):
        if not isinstance(question, dict):
            continue
        text = str(question.get("question") or "").strip()
        if not text:
            continue
        impact = str(question.get("impact") or "medium").strip()
        if impact not in {"low", "medium", "high"}:
            impact = "medium"
        items.append({
            "question": text,
            "impact": impact,
            "source": "clarification packet",
            "asked_count": 0,
            "last_asked_at": "",
            "question_id": f"question_{index + 1}",
        })
    return items


def _question_items_from_summary(summary: dict[str, Any], latest_packet: dict[str, Any] | None) -> list[dict[str, Any]]:
    questions = _question_items_from_packet(latest_packet)
    if questions:
        return questions
    next_question = str(summary.get("next_question") or "").strip()
    if next_question:
        impact = "high" if summary.get("status") == "blocked" else "medium"
        return [{
            "question": next_question,
            "impact": impact,
            "source": "mission summary",
            "asked_count": 0,
            "last_asked_at": "",
            "question_id": "summary_question_1",
        }]
    needs = summary.get("what_we_need_from_you")
    if isinstance(needs, list) and needs:
        items: list[dict[str, Any]] = []
        for index, item in enumerate(needs[:3]):
            text = str(item).strip()
            if not text:
                continue
            items.append({
                "question": text,
                "impact": "high" if index == 0 and summary.get("status") == "blocked" else "medium",
                "source": "mission summary",
                "asked_count": 0,
                "last_asked_at": "",
                "question_id": f"need_{index + 1}",
            })
        return items
    return []


def _question_is_blocking(question: str) -> bool:
    lower = question.lower()
    return any(
        token in lower
        for token in [
            "approve",
            "approval",
            "review preview",
            "submit",
            "dispatch",
            "bridge",
            "governance",
            "which path",
            "final answer",
            "publish",
        ]
    )


def _is_general_instruction_task(objective: str) -> bool:
    normalized = _normalize_mission_objective(objective)
    if not normalized:
        return False
    prefixes = (
        "how do i ",
        "how to ",
        "what is ",
        "explain ",
        "teach me ",
        "show me ",
        "walk me through ",
        "help me understand ",
        "write a ",
        "write an ",
        "create a ",
        "make a ",
        "draft a ",
        "give me a ",
    )
    if normalized.startswith(prefixes):
        return True
    tokens = normalized.split()
    instructional_markers = {"how", "teach", "explain", "guide", "steps", "example", "script"}
    return any(marker in tokens for marker in instructional_markers)


def _mission_requires_external_artifact(objective: str) -> bool:
    normalized = _normalize_mission_objective(objective)
    if not normalized:
        return False
    external_patterns = [
        r"\bsummarize\s+(this|my|the)\s+(text|article|document|essay|note|transcript)\b",
        r"\bfix\s+(this|my|the)\s+(code|script|program|bug|error|stack trace)\b",
        r"\bdebug\s+(this|my|the)\s+(code|script|program|bug|error|stack trace|log)\b",
        r"\banalyze\s+(this|my|the)\s+(dataset|data|csv|spreadsheet|table|report)\b",
        r"\breview\s+(this|my|the)\s+(code|script|document|dataset|report)\b",
    ]
    return any(re.search(pattern, normalized) for pattern in external_patterns)


def _mission_inputs_supply_artifact(inputs: Any, latest_packet: dict[str, Any] | None) -> bool:
    for item in _dict_list(inputs):
        content = str(item.get("content") or item.get("text") or "").strip()
        if len(content) >= 40 or "\n" in content or "```" in content:
            return True
    if isinstance(latest_packet, dict):
        provisional = str((latest_packet.get("provisional_answer") or {}).get("text") or "").strip()
        if provisional:
            return True
    return False


def _missing_artifact_question(objective: str) -> str:
    normalized = _normalize_mission_objective(objective)
    if "summarize" in normalized and "text" in normalized:
        return "Please provide the text you want summarized."
    if any(token in normalized for token in ["fix", "debug", "code", "script"]):
        return "Please provide the code or error output you want fixed."
    if any(token in normalized for token in ["analyze", "dataset", "data", "csv", "spreadsheet"]):
        return "Please provide the dataset or data sample you want analyzed."
    return "Please provide the missing file, text, or data needed for this mission."


def _is_sufficient_to_proceed(
    objective: str,
    inputs: Any,
    current_state: str,
    latest_packet: dict[str, Any] | None,
) -> tuple[bool, str]:
    del current_state
    normalized = _normalize_mission_objective(objective)
    if not normalized:
        return False, "Please provide the mission objective."
    if _mission_requires_external_artifact(objective) and not _mission_inputs_supply_artifact(inputs, latest_packet):
        return False, _missing_artifact_question(objective)
    if _is_general_instruction_task(objective):
        return True, "general_instruction_task"
    return True, "self_contained_objective"


def _question_quick_replies(question: str, *, can_continue_without_input: bool) -> list[dict[str, str]]:
    lower = question.lower()
    if "production or staging" in lower or ("production" in lower and "staging" in lower):
        return [
            {"label": "Production", "value": "production"},
            {"label": "Staging", "value": "staging"},
            {"label": "Not sure", "value": "Not sure"},
        ]
    if "yes / no" in lower or "yes/no" in lower or lower.startswith("is "):
        return [
            {"label": "Yes", "value": "Yes"},
            {"label": "No", "value": "No"},
            {"label": "Not sure", "value": "Not sure"},
        ]
    if any(token in lower for token in ["objective", "scope", "link", "desired outcome"]):
        return [
            {"label": "Objective", "value": "objective"},
            {"label": "Scope", "value": "scope"},
            {"label": "Link", "value": "link"},
            {"label": "Desired outcome", "value": "desired outcome"},
        ]
    replies = [
        {"label": "Not sure", "value": "Not sure"},
        {"label": "Write more information", "value": "Write more information"},
    ]
    if can_continue_without_input:
        replies.insert(0, {"label": "Proceed with assumptions", "value": "Proceed with assumptions"})
    return replies


def _merge_unique_structured(items: list[dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        key = _normalize_question_text(item.get(key_name) or item.get("statement") or item.get("text") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _merge_unique_strings(items: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = _normalize_question_text(item or "")
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(str(item).strip())
    return merged


def _merge_deferred_questions(
    existing: Any,
    new_questions: list[dict[str, Any]],
    confirmed_facts: list[dict[str, Any]],
    operator_text: str,
    quick_reply: str | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(existing, list):
        for item in existing:
            if isinstance(item, dict) and str(item.get("question") or "").strip():
                items.append(item)

    fact_text = " ".join(str(item.get("text") or "") for item in confirmed_facts).lower()
    for question in new_questions:
        question_text = str(question.get("question") or "").strip()
        if not question_text:
            continue
        normalized = _normalize_question_text(question_text)
        resolved = False
        if normalized in fact_text and fact_text:
            resolved = True
        if "production or staging" in normalized and any(token in fact_text for token in ["production", "staging"]):
            resolved = True
        if "outage window" in normalized and "window" in fact_text:
            resolved = True
        if any(token in normalized for token in ["objective", "scope", "link", "desired outcome"]) and any(
            token in fact_text for token in ["objective", "scope", "link", "desired outcome"]
        ):
            resolved = True
        if quick_reply and _normalize_question_text(quick_reply) in normalized:
            resolved = True
        if operator_text and _normalize_question_text(operator_text) in normalized:
            resolved = True
        if resolved:
            continue
        items.append({
            "question": question_text,
            "impact": str(question.get("impact") or "medium"),
            "source": str(question.get("source") or "mission summary"),
            "asked_count": int(question.get("asked_count") or 0),
            "last_asked_at": str(question.get("last_asked_at") or ""),
            "question_id": str(question.get("question_id") or _normalize_question_text(question_text).replace(" ", "_")[:40]),
        })

    return _merge_unique_structured(items, "question")


def _assumption_summary_lines(assumptions: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in assumptions[:4]:
        statement = str(item.get("statement") or item.get("text") or "").strip()
        if not statement:
            continue
        confidence = item.get("confidence")
        reason = str(item.get("reason") or "").strip()
        if isinstance(confidence, (int, float)):
            line = f"{statement} (confidence {float(confidence):.2f})"
        else:
            line = statement
        if reason:
            line = f"{line} - {reason}"
        lines.append(line)
    return lines


def _fact_summary_lines(facts: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in facts[:5]:
        text = str(item.get("text") or "").strip()
        if text:
            lines.append(text)
    return lines


def _question_summary_lines(questions: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in questions[:4]:
        text = str(item.get("question") or "").strip()
        if text:
            lines.append(text)
    return lines


def _working_memory_baseline_confidence(detail: dict[str, Any]) -> float:
    score = 0.18
    if detail.get("latest_hermes_run"):
        score += 0.22
    if detail.get("latest_clarification_packet"):
        score += 0.18
    if detail.get("latest_draft"):
        score += 0.12
    if detail.get("manifest"):
        score += 0.08
    if detail.get("mission_inputs"):
        score += min(0.08, len(detail.get("mission_inputs") or []) * 0.02)
    return max(0.05, min(0.95, score))


def _working_memory_operating_status(
    *,
    current_state: str,
    confidence: float,
    active_assumptions: list[dict[str, Any]],
    open_questions: list[dict[str, Any]],
    deferred_questions: list[dict[str, Any]],
) -> tuple[str, bool, str]:
    current_state = current_state or "MISSION_DEFINED"
    blocking_questions = [item for item in open_questions if _question_is_blocking(str(item.get("question") or ""))]
    if current_state in {"MISSION_CLOSED", "ARCHIVE_REVIEW"}:
        return "idle", True, ""
    if current_state in {"PACKAGE_READY", "BRIDGE_CONSIDERATION"}:
        return "ready_for_review", True, ""
    if blocking_questions:
        reason = str(blocking_questions[0].get("question") or "A blocking clarification is required.").strip()
        return "blocked", False, reason
    if current_state in {"CLARIFICATION_NEEDED", "RECONSIDERATION_REQUESTED"}:
        if active_assumptions:
            if confidence < 0.45 or open_questions:
                reason = str(open_questions[0].get("question") or "Proceeding under explicit assumptions.").strip() if open_questions else "Proceeding under explicit assumptions."
                return "needs_clarification_but_continuing", True, reason
            return "proceeding_with_assumptions", True, ""
        if confidence < 0.35:
            reason = str(open_questions[0].get("question") or "Low confidence but no safe blocker is present.").strip() if open_questions else "Low confidence but no safe blocker is present."
            return "low_confidence_continue", True, reason
        if open_questions:
            return "needs_clarification_but_continuing", True, str(open_questions[0].get("question") or "").strip()
        return "proceeding_with_assumptions", True, ""
    if confidence < 0.35:
        return "low_confidence_continue", True, "Confidence is still low, but the mission can continue."
    if open_questions:
        return "proceeding_with_assumptions", True, str(open_questions[0].get("question") or "").strip()
    if active_assumptions:
        return "proceeding_with_assumptions", True, ""
    return "proceeding_with_assumptions", True, ""


def _build_working_memory_payload(
    detail: dict[str, Any],
    *,
    operator_text: str = "",
    operator_reply_at: str = "",
    source: str = "",
    quick_reply: str | None = None,
) -> dict[str, Any]:
    mission_id = str(detail.get("mission_id") or "").strip()
    current_state = str(detail.get("current_state") or "MISSION_DEFINED").strip() or "MISSION_DEFINED"
    mission_summary = detail.get("mission_summary") if isinstance(detail.get("mission_summary"), dict) else {}
    latest_packet = detail.get("latest_clarification_packet") if isinstance(detail.get("latest_clarification_packet"), dict) else None
    objective = str(detail.get("objective") or "").strip()
    existing = read_working_memory(mission_id) if mission_id else {}

    confirmed_facts: list[dict[str, Any]] = []
    if isinstance(existing, dict):
        confirmed_facts.extend(_dict_list(existing.get("confirmed_facts")))
    created_at = operator_reply_at or iso_now()
    if objective:
        confirmed_facts.append({
            "text": f"Mission objective: {objective}",
            "source": "mission brief",
            "created_at": str(detail.get("created_at") or created_at),
        })
    if operator_text:
        confirmed_facts.extend(_extract_confirmed_fact_items(operator_text, source=source or "operator input", created_at=created_at))
    confirmed_facts = _merge_unique_structured(confirmed_facts, "text")

    active_assumptions = _merge_unique_structured(
        _assumption_display_items(_dict_list(detail.get("assumptions"))),
        "statement",
    )

    open_questions = _question_items_from_summary(mission_summary, latest_packet)
    deferred_questions = _merge_deferred_questions(
        existing.get("deferred_questions") if isinstance(existing, dict) else [],
        open_questions,
        confirmed_facts,
        operator_text,
        quick_reply,
    )
    if not open_questions and deferred_questions:
        open_questions = deferred_questions[:2]

    baseline_confidence = _working_memory_baseline_confidence(detail)
    confidence_penalty = min(0.25, 0.05 * max(0, len(active_assumptions) - 1))
    if open_questions:
        confidence_penalty += 0.03 if any(_question_is_blocking(str(item.get("question") or "")) for item in open_questions) else 0.05
    if current_state in {"CLARIFICATION_NEEDED", "RECONSIDERATION_REQUESTED"}:
        confidence_penalty += 0.05
    if quick_reply and _normalize_question_text(quick_reply) == "proceed with assumptions":
        confidence_penalty = max(0.02, confidence_penalty - 0.03)
    confidence_penalty = min(0.4, confidence_penalty)
    confidence = max(0.05, min(0.95, baseline_confidence - confidence_penalty))

    operating_status, can_continue_without_input, blocked_reason = _working_memory_operating_status(
        current_state=current_state,
        confidence=confidence,
        active_assumptions=active_assumptions,
        open_questions=open_questions,
        deferred_questions=deferred_questions,
    )
    crew_recalled = not can_continue_without_input and operating_status == "blocked"
    existing_parked_at = str(existing.get("parked_at") or "") if isinstance(existing, dict) else ""
    parked_at = existing_parked_at
    if crew_recalled and not parked_at:
        parked_at = iso_now()
    if not crew_recalled:
        parked_at = ""

    latest_summary = str(mission_summary.get("summary") or "").strip()
    if not latest_summary:
        latest_summary = str((detail.get("latest_hermes_run") or {}).get("summary") or "").strip()
    if not latest_summary:
        latest_summary = str((detail.get("manifest") or {}).get("summary") or "").strip()
    if not latest_summary and objective:
        latest_summary = f"Mission focused on {objective}."

    memory = {
        "mission_id": mission_id,
        "confirmed_facts": confirmed_facts,
        "active_assumptions": active_assumptions,
        "open_questions": open_questions[:4],
        "deferred_questions": deferred_questions[:8],
        "latest_summary": latest_summary,
        "latest_confidence": round(confidence, 2),
        "confidence_reduction": round(max(0.0, baseline_confidence - confidence), 2),
        "last_operator_reply_at": operator_reply_at or (str(existing.get("last_operator_reply_at") or "") if isinstance(existing, dict) else ""),
        "updated_at": iso_now(),
        "operating_status": operating_status,
        "blocked_reason": blocked_reason,
        "can_continue_without_input": can_continue_without_input,
        "crew_status": "recalled" if crew_recalled else "active",
        "crew_recalled": crew_recalled,
        "expedition_activity": "paused" if crew_recalled else "running",
        "wake_hint": str(open_questions[0].get("question") or blocked_reason or "") if open_questions or blocked_reason else "",
        "parked_at": parked_at,
    }
    return memory


def _refresh_working_memory(
    mission_id: str,
    *,
    operator_text: str = "",
    operator_reply_at: str = "",
    source: str = "",
    quick_reply: str | None = None,
) -> dict[str, Any]:
    detail = _build_expedition_detail(mission_id)
    memory = _build_working_memory_payload(
        detail,
        operator_text=operator_text,
        operator_reply_at=operator_reply_at,
        source=source,
        quick_reply=quick_reply,
    )
    write_working_memory(mission_id, memory)
    return memory


def _blocking_question_lines(
    open_question_items: list[dict[str, Any]],
    latest_packet: dict[str, Any] | None,
) -> list[str]:
    questions: list[str] = []
    for item in open_question_items:
        text = str(item.get("question") or "").strip()
        if text and _question_is_blocking(text):
            questions.append(text)
    if not questions and isinstance(latest_packet, dict):
        for item in _dict_list(latest_packet.get("clarifying_questions_ranked")):
            text = str(item.get("question") or "").strip()
            impact = str(item.get("impact") or "medium").strip().lower()
            if text and impact == "high":
                questions.append(text)
    return _merge_unique_strings(questions)[:3]


def _operator_options(
    *,
    operator_posture: str,
    blocking_questions: list[str],
    has_review_preview: bool,
    parking_status: dict[str, Any],
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    if operator_posture != "parked":
        options.append({"label": "Proceed with assumptions", "value": "Proceed with assumptions", "kind": "assume"})
    if blocking_questions:
        options.append({"label": "Answer blockers", "value": "Answer blockers", "kind": "blockers"})
    if has_review_preview:
        options.append({"label": "Open review preview", "value": "Open review preview", "kind": "review"})
    return options[:5]


def _clarification_facts_from_text(text: str) -> list[str]:
    lowered = text.lower()
    facts: list[str] = []
    if any(token in lowered for token in ["production", "prod"]):
        facts.append("production")
    if "staging" in lowered:
        facts.append("staging")
    if "window" in lowered:
        facts.append("window")
    if "objective" in lowered:
        facts.append("objective")
    if "scope" in lowered:
        facts.append("scope")
    if "link" in lowered or "url" in lowered:
        facts.append("link")
    if "outcome" in lowered or "result" in lowered:
        facts.append("desired outcome")
    return facts


def _first_pass_answer(objective: str, assumptions: list[str]) -> str:
    normalized = _normalize_mission_objective(objective)
    assumption_clause = f" Assumption: {assumptions[0]}." if assumptions else ""

    if any(token in normalized for token in ["dog", "puppy", "sit", "stay", "training", "obedience"]):
        return (
            "First pass: use a treat to guide the dog into a sit, mark the moment the hips touch the floor, "
            "reward immediately, and repeat 5 to 10 short reps. Then add the cue word \"sit,\" practice in a "
            "low-distraction space, and gradually phase out the lure while still rewarding successful reps."
            f"{assumption_clause}"
        )
    if "python" in normalized and "csv" in normalized:
        return (
            "First pass: start with a small Python 3 script that reads the CSV with csv.DictReader, performs the "
            "minimum required transformation, and writes the result back with csv.DictWriter. Keep the input and "
            "output file paths explicit first, then refine for environment-specific needs once they exist."
            f"{assumption_clause}"
        )
    if _is_general_instruction_task(objective):
        return (
            "First pass: take the smallest useful version of the task, make the current assumptions explicit, "
            "produce a practical draft or step sequence now, and refine only after a concrete constraint appears."
            f"{assumption_clause}"
        )
    return ""


def _normalize_section_lines(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                lines.append(text)
        return lines
    return []


def _format_expeditioner_output(first_pass_answer: str, assumptions: list[str] | None = None, next_steps: list[str] | None = None) -> str:
    answer_text = str(first_pass_answer or "").strip() or "No bounded first-pass answer was available."
    sections = [f"First-pass answer: {answer_text}"]

    normalized_assumptions = [item for item in (assumptions or []) if str(item).strip()]
    if normalized_assumptions:
        sections.append("Assumptions:\n" + "\n".join(f"- {item}" for item in normalized_assumptions))

    normalized_next_steps = [item for item in (next_steps or []) if str(item).strip()]
    if normalized_next_steps:
        sections.append("Next steps:\n" + "\n".join(f"- {item}" for item in normalized_next_steps))

    return "\n\n".join(sections)


def _fallback_expeditioner_output(detail: dict[str, Any], message: str, quick_reply: str | None) -> str:
    reply, _ = _clarification_reply_text(message, quick_reply, detail)
    summary = detail.get("mission_summary") if isinstance(detail.get("mission_summary"), dict) else {}
    assumptions = _assumption_summary_lines(_dict_list(detail.get("assumptions")))
    next_step = str(summary.get("recommended_next_step") or "").strip()
    return _format_expeditioner_output(reply, assumptions=assumptions, next_steps=[next_step] if next_step else [])


def _operator_invoke_role_text(message: str, quick_reply: str | None = None) -> str | None:
    quick = str(quick_reply or "").strip().lower()
    if quick == "invoke-role":
        return quick
    raw_message = str(message or "").strip()
    lowered = raw_message.lower()
    if lowered.startswith("invoke-role:"):
        return raw_message[len("invoke-role:"):].strip()
    if lowered.startswith("/invoke-role"):
        return raw_message[len("/invoke-role"):].strip()
    return None


def _chat_semantic_text(message: str) -> str:
    return mirror_api_routes._chat_semantic_text(message)


def _clean_mirror_query_text(value: str) -> str:
    return mirror_api_routes._clean_mirror_query_text(value)


def _mirror_retrieval_plan(message: str, quick_reply: str | None = None) -> dict[str, Any]:
    return mirror_api_routes.build_mirror_retrieval_plan(_ROUTE_API, message, quick_reply)


def _mirror_token_forms(token: str) -> set[str]:
    return mirror_api_routes._mirror_token_forms(token)


def _mirror_query_tokens(query_text: str) -> list[str]:
    return mirror_api_routes._mirror_query_tokens(_ROUTE_API, query_text)


def _mirror_note_match_score(note_text: str, query_text: str) -> int:
    return mirror_api_routes._mirror_note_match_score(_ROUTE_API, note_text, query_text)


def _compact_mirror_note_text(text: str, limit: int = 180) -> str:
    return mirror_api_routes._compact_mirror_note_text(text, limit)


def _display_mirror_timestamp(value: str) -> str:
    return mirror_api_routes._display_mirror_timestamp(value)


def _concierge_mirror_retrieval_result(mission_id: str, message: str, quick_reply: str | None = None) -> dict[str, Any] | None:
    return mirror_api_routes.concierge_mirror_retrieval_result(_ROUTE_API, mission_id, message, quick_reply)


def _blocking_chat_fallback_reply(detail: dict[str, Any]) -> str:
    summary = detail.get("mission_summary") if isinstance(detail.get("mission_summary"), dict) else {}
    working_memory = detail.get("working_memory") if isinstance(detail.get("working_memory"), dict) else {}
    can_continue_without_input = bool(summary.get("can_continue_without_input", True))
    blocked_reason = str(
        working_memory.get("blocked_reason")
        or summary.get("blocked_reason")
        or ""
    ).strip()
    if blocked_reason and not can_continue_without_input:
        return f"Blocked: {blocked_reason}"

    blocking_questions = [str(item or "").strip() for item in list(summary.get("blocking_questions") or detail.get("blocking_questions") or []) if str(item or "").strip()]
    next_question = str(summary.get("next_question") or "").strip()
    clarification_reason = str(summary.get("clarification_reason") or "").strip()
    operator_posture = str(summary.get("operator_posture") or detail.get("operator_posture") or "").strip()

    if blocking_questions and not can_continue_without_input:
        return f"Blocked: {blocking_questions[0]}"

    if operator_posture == "needs_operator_answer" or not can_continue_without_input:
        followup = blocking_questions[0] if blocking_questions else next_question or clarification_reason
        if followup:
            return f"Blocked: {followup}"
    return ""


def _quiet_chat_fallback_reply(message: str, quick_reply: str | None, detail: dict[str, Any]) -> str:
    if str(quick_reply or "").strip():
        return ""
    if _operator_save_text(message) is not None:
        return ""
    if _operator_invoke_role_text(message, quick_reply) is not None:
        return ""
    has_structured_action, _ = _expeditioner_trigger_context(detail, quick_reply)
    if has_structured_action:
        return ""
    blocker_reply = _blocking_chat_fallback_reply(detail)
    if blocker_reply:
        return blocker_reply
    return "Recorded."


def _expeditioner_runtime_binding() -> dict[str, Any]:
    profile = load_helper_runtime_profile(EXPEDITIONER_ROLE_ID)
    binding: dict[str, Any] = {
        "role": profile.role_id,
        "enabled": False,
        "active_flag": profile.active,
        "execution_backend": profile.execution_backend,
        "model_key": "",
        "fallback_model_key": profile.fallback_model_key,
        "provider": "",
        "model_name": "",
    }
    if not profile.active or profile.execution_backend != "model_backed" or not profile.default_model_key:
        return binding

    models = load_model_registry()
    model_entry = models.get(profile.default_model_key, {})
    if not isinstance(model_entry, dict):
        return binding

    provider = str(model_entry.get("provider") or "").strip().lower()
    model_name = str(model_entry.get("model") or "").strip()
    if not provider or not model_name:
        return binding

    binding.update(
        {
            "enabled": True,
            "model_key": profile.default_model_key,
            "provider": provider,
            "model_name": model_name,
        }
    )
    return binding


def _expeditioner_trigger_context(detail: dict[str, Any], quick_reply: str | None) -> tuple[bool, str]:
    latest_trigger = detail.get("latest_trigger") if isinstance(detail.get("latest_trigger"), dict) else {}
    handoff = detail.get("trigger_handoff") if isinstance(detail.get("trigger_handoff"), dict) else {}
    parking_status = detail.get("parking_status") if isinstance(detail.get("parking_status"), dict) else {}
    summary = detail.get("mission_summary") if isinstance(detail.get("mission_summary"), dict) else {}
    if (
        str(parking_status.get("status") or "active").strip() == "parked"
        or str(summary.get("operator_posture") or "").strip() == "parked"
        or str(summary.get("triage_bucket") or "").strip() == "parked"
    ):
        return False, ""
    trigger_status = str(latest_trigger.get("status") or "").strip()
    trigger_kind = str(latest_trigger.get("trigger_kind") or "").strip()
    trigger_eval = latest_trigger.get("evaluation") if isinstance(latest_trigger.get("evaluation"), dict) else {}
    if (
        trigger_status in {"pending", "active"}
        and trigger_kind in ALLOWED_TRIGGER_KINDS
        and bool(trigger_eval.get("allowed"))
    ):
        trigger_reason = str(latest_trigger.get("reason") or trigger_kind or "trigger_record").strip()
        return True, trigger_reason

    allowed_action = str(handoff.get("allowed_action") or "").strip()
    handoff_status = str(handoff.get("status") or "").strip()
    if (
        str(handoff.get("target_role") or "").strip() == EXPEDITIONER_ROLE_ID
        and handoff_status in {"pending", "active"}
        and allowed_action in ALLOWED_TRIGGER_ACTIONS
    ):
        trigger_reason = str(handoff.get("reason") or allowed_action or "trigger_handoff").strip()
        return True, trigger_reason

    return False, ""


def _expeditioner_model_prompt(detail: dict[str, Any], message: str, quick_reply: str | None) -> str:
    summary = detail.get("mission_summary") if isinstance(detail.get("mission_summary"), dict) else {}
    working_memory = detail.get("working_memory") if isinstance(detail.get("working_memory"), dict) else {}
    prompt = {
        "role": "Spinetop-Expeditioner",
        "mission_id": str(detail.get("mission_id") or "").strip(),
        "objective": str(detail.get("objective") or "").strip(),
        "current_state": str(detail.get("current_state") or "").strip(),
        "operator_message": str(message or "").strip(),
        "quick_reply": str(quick_reply or "").strip(),
        "mission_summary": {
            "status": str(summary.get("status") or "").strip(),
            "operator_posture": str(summary.get("operator_posture") or "").strip(),
            "latest_summary": str(summary.get("latest_summary") or "").strip(),
            "recommended_next_step": str(summary.get("recommended_next_step") or "").strip(),
        },
        "active_assumptions": _assumption_summary_lines(_dict_list(detail.get("assumptions"))),
        "confirmed_facts": _fact_summary_lines(_dict_list(working_memory.get("confirmed_facts"))),
        "open_questions": _question_summary_lines(_dict_list(working_memory.get("open_questions"))),
        "constraints": [
            "Return only JSON with keys: first_pass_answer, assumptions, next_steps.",
            "Do not write truth, approve, submit, or alter governance state.",
            "Stay bounded, trigger-driven, and mission-local.",
            "Omit assumptions and next_steps by using empty arrays when not needed.",
        ],
    }
    return json.dumps(prompt, indent=2, ensure_ascii=False)


def _normalize_expeditioner_model_output(raw_response: str) -> str:
    candidate = extract_json_candidate(raw_response)
    parsed: Any = None
    if candidate is not None:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None

    if isinstance(parsed, dict):
        answer = str(parsed.get("first_pass_answer") or parsed.get("answer") or "").strip()
        assumptions = _normalize_section_lines(parsed.get("assumptions"))
        next_steps = _normalize_section_lines(parsed.get("next_steps"))
        if answer:
            return _format_expeditioner_output(answer, assumptions=assumptions, next_steps=next_steps)

    text = str(raw_response or "").strip()
    if not text:
        raise ValueError("model returned empty Expeditioner output")
    return _format_expeditioner_output(text)


def _log_expeditioner_model_invocation(
    *,
    mission_id: str,
    trigger_reason: str,
    binding: dict[str, Any],
    status: str,
    error: str = "",
) -> None:
    _append_jsonl(
        EXPEDITIONER_MODEL_LOG,
        {
            "logged_at": iso_now(),
            "mission_id": mission_id,
            "role": EXPEDITIONER_ROLE_ID,
            "model_key": str(binding.get("model_key") or "").strip(),
            "provider": str(binding.get("provider") or "").strip(),
            "model_used": str(binding.get("model_name") or "").strip(),
            "trigger_reason": trigger_reason,
            "status": status,
            "error": error,
        },
    )


def _try_expeditioner_model_reply(message: str, quick_reply: str | None, detail: dict[str, Any]) -> str | None:
    objective = str(detail.get("objective") or "").strip()
    current_state = str(detail.get("current_state") or "MISSION_DEFINED").strip() or "MISSION_DEFINED"
    latest_packet = detail.get("latest_clarification_packet") if isinstance(detail.get("latest_clarification_packet"), dict) else None
    sufficient, _ = _is_sufficient_to_proceed(objective, detail.get("mission_inputs"), current_state, latest_packet)
    if not sufficient:
        return None

    has_action, trigger_reason = _expeditioner_trigger_context(detail, quick_reply)
    if not has_action:
        return None

    binding = _expeditioner_runtime_binding()
    if not bool(binding.get("enabled")):
        return None

    runtime_config = load_hermes_runtime_config()
    system_prompt = (
        "You are Spinetop-Expeditioner. Return only JSON with keys first_pass_answer, assumptions, and next_steps. "
        "Stay bounded, derived-only, trigger-driven, and operator-visible. Never write truth, approve, submit, "
        "change governance, or imply background execution."
    )
    prompt = _expeditioner_model_prompt(detail, message, quick_reply)
    mission_id = str(detail.get("mission_id") or "").strip()

    try:
        raw_response = invoke_model(
            str(binding.get("model_key") or "").strip(),
            prompt,
            runtime_config,
            system_prompt=system_prompt,
            response_format="json_object",
        )
        normalized = _normalize_expeditioner_model_output(raw_response)
        _log_expeditioner_model_invocation(
            mission_id=mission_id,
            trigger_reason=trigger_reason,
            binding=binding,
            status="success",
        )
        return normalized
    except Exception as exc:
        _log_expeditioner_model_invocation(
            mission_id=mission_id,
            trigger_reason=trigger_reason,
            binding=binding,
            status="failure",
            error=str(exc),
        )
        return None


def _clarification_reply_text(message: str, quick_reply: str | None, detail: dict[str, Any]) -> tuple[str, str]:
    quick = str(quick_reply or "").strip().lower()
    summary = detail.get("mission_summary") if isinstance(detail.get("mission_summary"), dict) else {}
    parking_status = detail.get("parking_status") if isinstance(detail.get("parking_status"), dict) else {}
    working_memory = detail.get("working_memory") if isinstance(detail.get("working_memory"), dict) else {}
    next_question = str(summary.get("next_question") or "").strip()
    reason = str(summary.get("clarification_reason") or "").strip()
    blocked_reason = str(working_memory.get("blocked_reason") or "").strip()
    current_state = str(detail.get("current_state") or "")
    operator_posture = str(summary.get("operator_posture") or detail.get("operator_posture") or "").strip()
    message_lower = message.lower().strip()
    assumption_lines = _assumption_summary_lines(_dict_list(detail.get("assumptions")))
    open_questions = _question_summary_lines(_dict_list(working_memory.get("open_questions")))
    blocking_questions = list(summary.get("blocking_questions") or detail.get("blocking_questions") or [])
    can_continue_without_input = bool(summary.get("can_continue_without_input", True))
    review_preview = _record_object(detail.get("latest_draft"), "review_preview") if isinstance(detail, dict) else None
    objective = str(detail.get("objective") or "").strip()
    first_pass = _first_pass_answer(objective, assumption_lines)

    if quick in {"park mission", "resume mission"}:
        return "Parking is controlled by the mission parking button; this chat note does not change parking state.", "watch"
    if quick == "answer blockers":
        if blocking_questions:
            return f"The top blocker is: {blocking_questions[0]}", "watch"
        if open_questions:
            return f"The top open question is: {open_questions[0]}", "watch"
        return "There is no hard blocker right now. The mission can continue under bounded assumptions.", "good"
    if quick == "open review preview":
        if isinstance(review_preview, dict):
            preview_path = str(review_preview.get("draft_path") or "").strip()
            if preview_path:
                return f"Review preview is ready. Open the draft preview at {preview_path} to inspect it without submitting anything.", "good"
        return "No review preview is ready yet. I'll keep the mission in its current safe lane until a draft exists.", "watch"

    if quick == "proceed with assumptions":
        if first_pass:
            return first_pass, "good"
        if assumption_lines:
            preview = "; ".join(assumption_lines[:2])
            return f"Understood. I'm proceeding with explicit assumptions: {preview}. I'll keep the remaining question queued.", "good"
        return "Understood. I'm proceeding with the safest available assumptions and will keep the remaining question queued.", "good"
    if quick in {"production", "staging"}:
        return f"Thanks. I've recorded the environment as {quick} and will use that as the working assumption.", "good"
    if quick in {"objective", "scope", "link", "desired outcome"}:
        return f"Thanks. I've marked {quick} as the missing detail and will keep the mission moving with the current assumptions.", "good"

    if quick == "yes":
        if "production or staging" in next_question.lower():
            return "Confirmed. I'm treating this as an environment decision point and will keep the mission moving with the current working assumption.", "good"
        if "outage window" in next_question.lower():
            return "Thanks. That confirms the outage-window focus and narrows the mission.", "good"
        return "Thanks. I've recorded the confirmation and will use it to narrow the mission.", "good"
    if quick == "no":
        if "production or staging" in next_question.lower():
            return "Understood. I'll avoid locking the environment assumption and will continue with the safest fallback.", "watch"
        return "Understood. I'll avoid assuming that detail and keep the mission on the least risky path.", "watch"
    if quick == "not sure":
        if blocked_reason:
            return f"No problem. I still need one concrete blocker answer: {blocked_reason}", "watch"
        if first_pass:
            return first_pass, "good"
        return "No problem. I'll keep the mission moving under the current assumptions.", "good"
    if quick in {"write more information", "more info", "more information"}:
        if next_question:
            return f"Please add the missing detail for this mission: {next_question}", "watch"
        if blocked_reason:
            return f"Please add the missing detail that would unblock the mission: {blocked_reason}", "watch"
        return "Please add the missing detail that would improve confidence, even though the mission can continue.", "watch"

    facts = _clarification_facts_from_text(message)
    if facts:
        if "production" in facts or "staging" in facts:
            return "Thanks - that gives me an environment signal. I'm treating the mission as environment-scoped and will keep asking only for the most important remaining question.", "good"
        if "window" in facts:
            return "Thanks - I have the timing focus now. I'll use the outage window as the active constraint.", "good"
        if "link" in facts:
            return "Thanks - I've got a reference to work from, which helps narrow the mission.", "good"
        if "desired outcome" in facts:
            return "That helps. I now have a clearer outcome target and can narrow the next question.", "good"
        return "Thanks - I've recorded that as mission input and used it to narrow the clarification path.", "good"

    if operator_posture == "parked":
        wake_hint = str(parking_status.get("resume_hint") or next_question or blocked_reason or "").strip()
        if wake_hint:
            return f"The mission is parked. One clear answer would wake it: {wake_hint}", "watch"
        return "The mission is parked until you send fresh input to wake it.", "watch"

    if can_continue_without_input and operator_posture != "needs_operator_answer":
        if quick == "not sure":
            if first_pass:
                return first_pass, "good"
            return "No problem. There is no blocking clarification right now; the mission can proceed with the current objective.", "good"
        if quick in {"write more information", "more info", "more information"}:
            return "More context is optional here. The mission is already sufficient to proceed.", "good"
        if message.strip():
            if first_pass:
                return f"Thanks - I've recorded that as mission input. {first_pass}", "good"
            if assumption_lines:
                preview = "; ".join(assumption_lines[:2])
                return f"Thanks - I've recorded that as mission input. The mission can keep moving under these assumptions: {preview}.", "good"
            return "Thanks - I've recorded that as mission input. No additional clarification is required to proceed.", "good"
        if first_pass:
            return first_pass, "good"
        return "No immediate clarification is required. The mission can proceed with the current objective.", "good"

    if "?" in message_lower or current_state in {"CLARIFICATION_NEEDED", "RECONSIDERATION_REQUESTED"}:
        if blocked_reason:
            return f"I need one concrete blocker answer to continue: {blocked_reason}", "watch"
        if reason:
            return f"I can continue with assumptions, but this would improve things: {reason}", "watch"
        if next_question:
            return next_question, "watch"
        if open_questions:
            return f"I can continue, but the most useful next question is: {open_questions[0]}", "watch"
        return "I can continue with assumptions, but one clear answer would improve confidence.", "watch"

    if message.strip():
        if first_pass:
            return f"Thanks - I've recorded that as mission input. {first_pass}", "good"
        if assumption_lines:
            preview = "; ".join(assumption_lines[:2])
            return f"Thanks - I've recorded that as mission input. I'm keeping the mission moving under these assumptions: {preview}.", "good"
        return "Thanks - I've recorded that as mission input and will use it to refine the next clarification.", "good"

    if blocked_reason:
        return f"I need one concrete blocker answer before I can move this mission forward: {blocked_reason}", "watch"
    return "I can continue with assumptions, but one more detail would improve confidence.", "watch"


def _chat_reply(message: str, quick_reply: str | None, detail: dict[str, Any]) -> dict[str, str]:
    model_reply = _try_expeditioner_model_reply(message, quick_reply, detail)
    if model_reply:
        return {
            "role": "assistant",
            "tone": "good",
            "message": model_reply,
        }

    quiet_fallback = _quiet_chat_fallback_reply(message, quick_reply, detail)
    if quiet_fallback:
        return {
            "role": "assistant",
            "tone": "good",
            "message": quiet_fallback,
        }

    reply, tone = _clarification_reply_text(message, quick_reply, detail)
    return {
        "role": "assistant",
        "tone": tone,
        "message": _fallback_expeditioner_output(detail, message, quick_reply) if _expeditioner_trigger_context(detail, quick_reply)[0] else reply,
    }


def _operator_raw_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("text", "message", "content"):
        value = payload.get(key)
        if value is None:
            continue
        text = str(value)
        if text:
            return text
    return ""


def _operator_save_text(message: str) -> str | None:
    return save_api_helpers.extract_save_text(message)


def _operator_save_response(artifact: dict[str, Any]) -> dict[str, Any]:
    return save_api_helpers.build_operator_save_response(artifact)


def _operator_save_empty_response() -> dict[str, Any]:
    return save_api_helpers.build_operator_save_empty_response()


def _build_chat_exchange_items(mission_id: str, message: str, assistant: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    mission = normalize_mission_id(mission_id)
    created_at = iso_now()
    user_item = {
        "message_id": f"chat_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{_short_digest(f'{mission}|user|{message}|{created_at}')}",
        "mission_id": mission,
        "sender": "user",
        "role": "user",
        "message": message,
        "tone": "info",
        "created_at": created_at,
        "kind": "message",
    }
    assistant_message = str(assistant.get("message") or "")
    assistant_item = {
        "message_id": f"chat_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{_short_digest(f'{mission}|assistant|{assistant_message}|{created_at}')}",
        "mission_id": mission,
        "sender": str(assistant.get("sender") or "assistant"),
        "role": str(assistant.get("role") or "assistant"),
        "message": assistant_message,
        "tone": str(assistant.get("tone") or "info"),
        "created_at": iso_now(),
        "kind": str(assistant.get("kind") or "reply"),
    }
    return user_item, assistant_item


def _append_chat_exchange(mission_id: str, message: str, *, quick_reply: str | None = None) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    detail = _build_expedition_detail(mission)
    path = _mission_chat_path(mission, ensure=True)
    assistant = _chat_reply(message, quick_reply, detail)
    user_item, assistant_item = _build_chat_exchange_items(mission, message, assistant)
    _append_jsonl(path, user_item)
    _append_jsonl(path, assistant_item)
    working_memory = _build_working_memory_payload(
        detail,
        operator_text=message,
        operator_reply_at=user_item["created_at"],
        source="mission chat",
        quick_reply=quick_reply,
    )
    working_memory["latest_summary"] = str(detail.get("mission_summary", {}).get("summary") or working_memory.get("latest_summary") or "")
    working_memory["last_operator_reply_at"] = user_item["created_at"]
    write_working_memory(mission, working_memory)
    return {
        "messages": [user_item, assistant_item],
        "path": path.relative_to(ROOT).as_posix(),
        "summary": detail.get("summary") or "",
    }


def _mission_status_badge(
    current_state: str,
    manifest_status: str,
    latest_run_id: str,
    input_count: int,
    operating_status: str = "",
    operator_posture: str = "",
    triage_bucket: str = "",
) -> str:
    if current_state in {"MISSION_CLOSED", "ARCHIVE_REVIEW"}:
        return "idle"
    if operator_posture == "parked" or triage_bucket == "parked":
        return "waiting_for_user"
    if current_state in {"PACKAGE_READY", "BRIDGE_CONSIDERATION"} or manifest_status in {"ready_for_review"} or operating_status == "ready_for_review" or triage_bucket == "review":
        return "ready_for_review"
    if operator_posture == "needs_operator_answer" or triage_bucket == "waiting":
        return "waiting_for_user"
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
        return "researching"
    if operating_status in {"proceeding_with_assumptions", "needs_clarification_but_continuing", "low_confidence_continue"}:
        return "researching"
    if not latest_run_id and input_count == 0:
        return "researching"
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


def _mission_read_model_helpers() -> dict[str, Any]:
    mission_storage.configure_root(ROOT)
    return {
        "root": ROOT,
        "record_object": _record_object,
        "dict_list": _dict_list,
        "assumption_display_items": _assumption_display_items,
        "fact_summary_lines": _fact_summary_lines,
        "assumption_summary_lines": _assumption_summary_lines,
        "question_summary_lines": _question_summary_lines,
        "blocking_question_lines": _blocking_question_lines,
        "is_sufficient_to_proceed": _is_sufficient_to_proceed,
        "operator_options": _operator_options,
        "assumptions_last_updated": _assumptions_last_updated,
        "pending_runner_return_sync_count": _pending_runner_return_sync_count,
        "read_operator_interventions": _read_operator_interventions,
        "safe_operator_actions": _safe_operator_actions,
        "safe_relative_path": _safe_relative_path,
        "trigger_handoff_path": mission_storage._trigger_handoff_path,
        "mission_manifest_path": mission_manifest_path,
        "read_mission_agent_profile": _read_mission_agent_profile,
        "mission_chat_messages": _mission_chat_messages,
        "latest_run_summary": _latest_run_summary,
        "latest_draft_summary": _latest_draft_summary,
        "latest_clarification_summary": _latest_clarification_summary,
        "read_assumption_ledger_entries": _read_assumption_ledger_entries,
        "latest_assumption_changes": _latest_assumption_changes,
        "mission_status_badge": _mission_status_badge,
        "queue_hygiene_flags": _queue_hygiene_flags,
        "normalize_mission_objective": _normalize_mission_objective,
        "read_prompt_translations": _read_prompt_translations,
        "queue_summary_from_items": _queue_summary_from_items,
        "queue_sort_timestamp": _queue_sort_timestamp,
    }


def _sync_mission_storage() -> None:
    mission_storage.configure_root(ROOT)


def _mission_summary_payload(
    *,
    mission_id: str,
    objective: str,
    current_state: str,
    manifest: dict[str, Any] | None,
    latest_run: dict[str, Any] | None,
    latest_draft: dict[str, Any] | None,
    latest_packet: dict[str, Any] | None,
    latest_runner_return: dict[str, Any] | None,
    mission_inputs: list[dict[str, Any]],
    assumption_entries: list[dict[str, Any]] | None = None,
    working_memory: dict[str, Any] | None = None,
    parking_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _sync_mission_storage()
    return mission_read_model._mission_summary_payload(
        mission_id=mission_id,
        objective=objective,
        current_state=current_state,
        manifest=manifest,
        latest_run=latest_run,
        latest_draft=latest_draft,
        latest_packet=latest_packet,
        latest_runner_return=latest_runner_return,
        mission_inputs=mission_inputs,
        assumption_entries=assumption_entries,
        working_memory=working_memory,
        parking_status=parking_status,
        helpers=_mission_read_model_helpers(),
    )


def _safe_operator_actions(
    *,
    parking_status: dict[str, Any],
    summary_preview: dict[str, Any],
    queue_hygiene: dict[str, Any] | None = None,
    last_blocked_reason: str,
    retry_ledger: dict[str, Any],
    latest_runner_return: dict[str, Any] | None,
    latest_mirror_note: dict[str, Any] | None,
    pending_helper_syncs: int,
    active_handoff: dict[str, Any] | None,
) -> list[str]:
    actions: list[str] = []

    def add(action: str, *, condition: bool = True) -> None:
        action_text = str(action).strip()
        if condition and action_text and action_text not in actions:
            actions.append(action_text)

    parked = str(parking_status.get("status") or "active") == "parked"
    hygiene = queue_hygiene if isinstance(queue_hygiene, dict) else {}
    blocked_questions = [str(item).strip() for item in summary_preview.get("blocking_questions", []) if str(item).strip()]
    blocked_reason = str(summary_preview.get("blocked_reason") or last_blocked_reason or "").strip()
    operator_posture = str(summary_preview.get("operator_posture") or "").strip()
    retry_budget_total = int(retry_ledger.get("retry_budget_total") or 0)
    retry_budget_used = int(retry_ledger.get("retry_budget_used") or 0)
    retry_available = retry_budget_used < retry_budget_total

    if parked:
        add("resume mission")
        add(
            "clear stale pending handoff",
            condition=isinstance(active_handoff, dict) and str(active_handoff.get("status") or "").strip() in {"pending", "active", "blocked"},
        )
        return actions[:5]

    add("resume mission", condition=parked)
    add("answer blocker", condition=bool(blocked_questions) or bool(blocked_reason) or operator_posture == "needs_operator_answer")
    add("refresh assumptions", condition=bool(summary_preview.get("assumption_review_needed")))
    add("sync helper returns", condition=pending_helper_syncs > 0)
    add("retry bounded action", condition=retry_available and _suggests_retry(latest_runner_return))
    add("clear stale pending handoff", condition=isinstance(active_handoff, dict) and str(active_handoff.get("status") or "").strip() == "blocked")
    add("inspect mirror note", condition=isinstance(latest_mirror_note, dict) and bool(latest_mirror_note.get("path")))
    add("park mission", condition=bool(hygiene.get("stale_candidate")) and not parked and not bool(hygiene.get("review_ready")))
    add("mark archive candidate", condition=bool(hygiene.get("archive_candidate")))

    if isinstance(active_handoff, dict) and str(active_handoff.get("status") or "").strip() in {"pending", "active"}:
        action = str(active_handoff.get("allowed_action") or "").strip()
        if action == "resume_expedition":
            add("resume mission")
        elif action == "retry_expedition_refresh":
            add("retry bounded action", condition=retry_available)

    if not actions:
        add(str(summary_preview.get("recommended_next_step") or "monitor mission state"))
    return actions[:5]


def _role_label_for_helper(helper_type: str) -> str:
    helper = str(helper_type or "").strip()
    if helper == "retrieval_helper_2b":
        return "helper_2b"
    if helper == "runner_helper_2b":
        return "Expeditioner"
    return helper or "unknown"


def _latest_role_activity(
    *,
    latest_agent_run: dict[str, Any] | None,
    latest_runner_return: dict[str, Any] | None,
    latest_mirror_note: dict[str, Any] | None,
    trigger_handoff: dict[str, Any],
    manifest: dict[str, Any] | None,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    if isinstance(latest_agent_run, dict) and (latest_agent_run.get("created_at") or latest_agent_run.get("path")):
        candidates.append({
            "role": str(latest_agent_run.get("role_label") or latest_agent_run.get("role") or "").strip() or "role",
            "kind": "agent_run",
            "summary": str(latest_agent_run.get("summary") or "").strip(),
            "created_at": str(latest_agent_run.get("created_at") or "").strip(),
            "source_ref": str(latest_agent_run.get("path") or "").strip(),
        })
    if isinstance(latest_runner_return, dict) and (latest_runner_return.get("created_at") or latest_runner_return.get("path")):
        candidates.append({
            "role": _role_label_for_helper(str(latest_runner_return.get("helper_type") or latest_runner_return.get("runner_id") or "")),
            "kind": "runner_return",
            "summary": str(latest_runner_return.get("summary") or "").strip(),
            "created_at": str(latest_runner_return.get("created_at") or "").strip(),
            "source_ref": str(latest_runner_return.get("path") or latest_runner_return.get("source_ref") or "").strip(),
        })
    if isinstance(latest_mirror_note, dict) and (latest_mirror_note.get("created_at") or latest_mirror_note.get("path")):
        candidates.append({
            "role": "Mirror",
            "kind": "mirror_note",
            "summary": str(latest_mirror_note.get("summary") or "").strip(),
            "created_at": str(latest_mirror_note.get("created_at") or "").strip(),
            "source_ref": str(latest_mirror_note.get("path") or "").strip(),
        })
    if str(trigger_handoff.get("status") or "").strip() in {"pending", "active", "blocked"}:
        candidates.append({
            "role": str(trigger_handoff.get("target_role") or "").strip() or "Expeditioner",
            "kind": "trigger_handoff",
            "summary": str(trigger_handoff.get("allowed_action") or trigger_handoff.get("reason") or "").strip(),
            "created_at": str(trigger_handoff.get("updated_at") or "").strip(),
            "source_ref": _safe_relative_path(_trigger_handoff_path(str(trigger_handoff.get("mission_id") or ""))),
        })
    if isinstance(manifest, dict) and (manifest.get("updated_at") or manifest.get("created_at")):
        candidates.append({
            "role": "Expeditioner",
            "kind": "mission_manifest",
            "summary": str(manifest.get("summary") or manifest.get("recommended_next_step") or "").strip(),
            "created_at": str(manifest.get("updated_at") or manifest.get("created_at") or "").strip(),
            "source_ref": _safe_relative_path(mission_manifest_path(str(manifest.get("mission_id") or ""))),
        })
    if not candidates:
        return None
    candidates.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("source_ref") or "")), reverse=True)
    return candidates[0]


def _build_control_tower_summary(
    *,
    mission_id: str,
    manifest: dict[str, Any] | None,
    latest_draft: dict[str, Any] | None,
    latest_packet: dict[str, Any] | None,
    prompt_translation_count: int,
    summary_preview: dict[str, Any],
    autonomy_status: dict[str, Any],
    latest_trigger: dict[str, Any] | None,
    trigger_handoff: dict[str, Any],
    retry_ledger: dict[str, Any],
    parking_status: dict[str, Any],
    agent_runs: list[dict[str, Any]],
    runner_returns: list[dict[str, Any]],
    mirror_notes: list[dict[str, Any]],
) -> dict[str, Any]:
    _sync_mission_storage()
    return mission_read_model._build_control_tower_summary(
        mission_id=mission_id,
        manifest=manifest,
        latest_draft=latest_draft,
        latest_packet=latest_packet,
        prompt_translation_count=prompt_translation_count,
        summary_preview=summary_preview,
        autonomy_status=autonomy_status,
        latest_trigger=latest_trigger,
        trigger_handoff=trigger_handoff,
        retry_ledger=retry_ledger,
        parking_status=parking_status,
        agent_runs=agent_runs,
        runner_returns=runner_returns,
        mirror_notes=mirror_notes,
        helpers=_mission_read_model_helpers(),
    )


def _build_expedition_detail(mission_id: str) -> dict[str, Any]:
    _sync_mission_storage()
    return mission_read_model._build_expedition_detail(
        mission_id,
        helpers=_mission_read_model_helpers(),
    )


def _write_mission_input(mission: str, content: str) -> dict[str, Any]:
    _sync_mission_storage()
    return mission_storage._write_mission_input(mission, content)


_write_json = mission_storage._write_json
_load_json = mission_storage._load_json
_mission_root = mission_storage._mission_root
_workbench_root = mission_storage._workbench_root
_ensure_workbench_structure = mission_storage._ensure_workbench_structure
_workbench_notes_root = mission_storage._workbench_notes_root
_mission_chat_path = mission_storage._mission_chat_path
_mission_agent_root = mission_storage._mission_agent_root
_mission_agent_profile_path = mission_storage._mission_agent_profile_path
_mission_agent_soul_path = mission_storage._mission_agent_soul_path
_mission_parking_path = mission_storage._mission_parking_path
_triggers_dir = mission_storage._triggers_dir
_trigger_handoff_path = mission_storage._trigger_handoff_path
_runner_returns_dir = mission_storage._runner_returns_dir
_retry_ledger_path = mission_storage._retry_ledger_path
_assumptions_dir = mission_storage._assumptions_dir
_assumption_ledger_path = mission_storage._assumption_ledger_path
_mirror_dir = mission_storage._mirror_dir
_agent_runs_dir = mission_storage._agent_runs_dir
_interventions_dir = mission_storage._interventions_dir
_intervention_log_path = mission_storage._intervention_log_path
_archive_candidate_marker_path = mission_storage._archive_candidate_marker_path
_read_archive_candidate_marker = mission_storage._read_archive_candidate_marker
_mission_manifest_payload = mission_storage._mission_manifest_payload
_latest_mtime = mission_storage._latest_mtime
_read_runner_returns = mission_storage._read_runner_returns
_read_mirror_notes = mission_storage._read_mirror_notes
_read_agent_runs = mission_storage._read_agent_runs
_workbench_files = mission_storage._workbench_files
_mission_inputs = mission_storage._mission_inputs
_read_jsonl = mission_storage._read_jsonl
_append_jsonl = mission_storage._append_jsonl
_default_parking_status = mission_storage._default_parking_status
_read_parking_status = mission_storage._read_parking_status
_write_parking_status = mission_storage._write_parking_status
_default_trigger_handoff = mission_storage._default_trigger_handoff
_default_retry_ledger = mission_storage._default_retry_ledger
_normalize_retry_log_items = mission_storage._normalize_retry_log_items
_read_retry_ledger = mission_storage._read_retry_ledger
_write_retry_ledger = mission_storage._write_retry_ledger
_read_trigger_handoff = mission_storage._read_trigger_handoff
_write_trigger_handoff = mission_storage._write_trigger_handoff
_read_trigger_records = mission_storage._read_trigger_records


def _clear_parked_mission_handoff(mission_id: str, *, reason: str = "") -> dict[str, Any] | None:
    mission = normalize_mission_id(mission_id)
    existing = _read_trigger_handoff(mission)
    if str(existing.get("status") or "").strip() not in {"pending", "active", "blocked"}:
        return None
    return _write_trigger_handoff(
        mission,
        {
            "trigger_id": "",
            "target_role": "",
            "allowed_action": "",
            "status": "idle",
            "reason": str(reason).strip() or "parked missions stay cold until explicitly resumed",
            "policy_basis": "",
        },
    )


def _control_tower_intervention_reason(action: str, detail: dict[str, Any]) -> str:
    summary = detail.get("control_tower_summary") if isinstance(detail.get("control_tower_summary"), dict) else {}
    mission_summary = detail.get("mission_summary") if isinstance(detail.get("mission_summary"), dict) else {}
    action_key = str(action).strip().lower()
    if action_key == "resume_mission":
        return "operator explicitly resumed the parked mission from control tower"
    if action_key == "retry_bounded_action":
        return (
            str(summary.get("operator_attention_reason") or "").strip()
            or str(summary.get("last_retry_reason") or "").strip()
            or str(summary.get("last_blocked_reason") or "").strip()
            or "operator requested one bounded retry from control tower"
        )
    if action_key == "refresh_assumptions":
        return "operator requested an explicit assumption refresh from control tower"
    if action_key == "sync_helper_returns":
        return "operator requested a mission-local helper return sync from control tower"
    if action_key == "clear_stale_pending_handoff":
        return (
            str(summary.get("last_blocked_reason") or "").strip()
            or str(mission_summary.get("blocked_reason") or "").strip()
            or "operator cleared a stale blocked handoff from control tower"
        )
    if action_key == "mark_archive_candidate":
        return "operator explicitly marked this mission as an archive-review candidate in mission-local notes"
    return "operator intervention from control tower"


def _apply_control_tower_intervention(
    mission_id: str,
    *,
    action: str,
    reason: str = "",
    note: str = "",
) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    action_key = str(action).strip().lower()
    if action_key not in {
        "resume_mission",
        "retry_bounded_action",
        "refresh_assumptions",
        "sync_helper_returns",
        "clear_stale_pending_handoff",
        "mark_archive_candidate",
    }:
        raise ValueError("unsupported intervention")

    detail = _build_expedition_detail(mission)
    effective_reason = str(reason).strip() or _control_tower_intervention_reason(action_key, detail)
    changed_paths: list[str] = []
    blocked_reason = ""
    outcome: dict[str, Any] | None = None

    if action_key == "resume_mission":
        parking_status = detail.get("parking_status") if isinstance(detail.get("parking_status"), dict) else {}
        if str(parking_status.get("status") or "active").strip() != "parked":
            blocked_reason = "mission is not parked"
        else:
            record = _write_parking_status(mission, status="active", reason=effective_reason, parked_by="operator")
            changed_paths.append(_mission_parking_path(mission).relative_to(ROOT).as_posix())
            trigger = _create_trigger_record(
                mission,
                trigger_kind="mission_resumed",
                reason=effective_reason,
                source="control_tower_intervention",
            )
            if str(trigger.get("path") or "").strip():
                changed_paths.append(str(trigger["path"]).strip())
            changed_paths.append(_trigger_handoff_path(mission).relative_to(ROOT).as_posix())
            outcome = {"parking_status": record, "trigger": trigger}
    elif action_key == "retry_bounded_action":
        trigger = _create_trigger_record(
            mission,
            trigger_kind="operator_refresh_requested",
            reason=effective_reason,
            source="control_tower_intervention",
        )
        if str(trigger.get("path") or "").strip():
            changed_paths.append(str(trigger["path"]).strip())
        if trigger.get("retry_ledger"):
            changed_paths.append(_retry_ledger_path(mission).relative_to(ROOT).as_posix())
        if str(((trigger.get("handoff") or {}).get("status") or "")).strip() == "pending":
            changed_paths.append(_trigger_handoff_path(mission).relative_to(ROOT).as_posix())
        evaluation = trigger.get("evaluation") if isinstance(trigger.get("evaluation"), dict) else {}
        if str(trigger.get("status") or "").strip() == "blocked":
            blocked_reason = str(evaluation.get("blocked_reason") or "retry blocked").strip()
        outcome = {"trigger": trigger}
    elif action_key == "refresh_assumptions":
        refresh = _refresh_assumption_ledger(mission)
        changed_paths.append(str(refresh.get("ledger_path") or _assumption_ledger_path(mission).relative_to(ROOT).as_posix()))
        outcome = {"refresh": refresh}
    elif action_key == "sync_helper_returns":
        pending = _pending_runner_return_sync_count(mission)
        if pending <= 0:
            blocked_reason = "no unsynced helper returns are available"
        else:
            sync = _sync_runner_returns_result(mission)
            created_paths = [
                str(item.get("path") or "").strip()
                for item in sync.get("created", [])
                if isinstance(item, dict) and str(item.get("path") or "").strip()
            ]
            changed_paths.extend(created_paths)
            outcome = {"sync": sync}
    elif action_key == "clear_stale_pending_handoff":
        handoff = _read_trigger_handoff(mission)
        handoff_status = str(handoff.get("status") or "idle").strip()
        if handoff_status != "blocked":
            blocked_reason = "pending handoff is not a blocked stale overlay"
        else:
            cleared = _write_trigger_handoff(
                mission,
                {
                    "trigger_id": "",
                    "target_role": "",
                    "allowed_action": "",
                    "status": "idle",
                    "reason": effective_reason,
                    "policy_basis": "",
                },
            )
            changed_paths.append(_trigger_handoff_path(mission).relative_to(ROOT).as_posix())
            outcome = {"handoff": cleared}
    elif action_key == "mark_archive_candidate":
        hygiene = detail.get("queue_hygiene") if isinstance(detail.get("queue_hygiene"), dict) else {}
        marker_path = _archive_candidate_marker_path(mission, ensure=True)
        marker = {
            "mission_id": mission,
            "status": "archive_candidate",
            "marked_at": iso_now(),
            "marked_by": "operator",
            "reason": effective_reason,
            "recommended_action": str(hygiene.get("recommended_action") or "archive candidate"),
            "signals": [str(item).strip() for item in hygiene.get("signals", []) if str(item).strip()][:6],
            "heuristic_match": bool(hygiene.get("archive_candidate")),
            "derived_only": True,
        }
        _write_json(marker_path, marker)
        changed_paths.append(marker_path.relative_to(ROOT).as_posix())
        outcome = {"archive_candidate": marker}

    status = "blocked" if blocked_reason else "applied"
    intervention = _append_operator_intervention(
        mission,
        action=action_key,
        status=status,
        reason=effective_reason,
        note=note,
        blocked_reason=blocked_reason,
        changed_paths=changed_paths,
    )
    item = _build_expedition_detail(mission)
    return {
        "ok": not bool(blocked_reason),
        "blocked": bool(blocked_reason),
        "error": blocked_reason,
        "intervention": intervention,
        "result": outcome or {},
        "item": item,
    }


def _mission_exists(mission_id: str) -> bool:
    mission = normalize_mission_id(mission_id)
    return _mission_root(mission).exists() or _workbench_root(mission).exists()


def _project_latest_meaningful_activity(detail: dict[str, Any]) -> dict[str, Any] | None:
    control_tower = detail.get("control_tower_summary") if isinstance(detail.get("control_tower_summary"), dict) else {}
    latest_role_activity = control_tower.get("latest_role_activity") if isinstance(control_tower.get("latest_role_activity"), dict) else {}
    if latest_role_activity:
        return {
            "kind": str(latest_role_activity.get("kind") or "").strip(),
            "role": str(latest_role_activity.get("role") or "").strip(),
            "summary": str(latest_role_activity.get("summary") or "").strip(),
            "created_at": str(latest_role_activity.get("created_at") or "").strip(),
            "artifact_ref": str(latest_role_activity.get("source_ref") or "").strip(),
        }

    latest_trigger = detail.get("latest_trigger") if isinstance(detail.get("latest_trigger"), dict) else {}
    if latest_trigger:
        return {
            "kind": "trigger",
            "role": str(latest_trigger.get("target_role") or "").strip(),
            "summary": str(latest_trigger.get("reason") or latest_trigger.get("trigger_kind") or "").strip(),
            "created_at": str(latest_trigger.get("created_at") or "").strip(),
            "artifact_ref": str(latest_trigger.get("path") or "").strip(),
        }
    return None


def _expedition_state_api_item(detail: dict[str, Any]) -> dict[str, Any]:
    mission_summary = detail.get("mission_summary") if isinstance(detail.get("mission_summary"), dict) else {}
    control_tower = detail.get("control_tower_summary") if isinstance(detail.get("control_tower_summary"), dict) else {}
    return {
        "mission_id": str(detail.get("mission_id") or "").strip(),
        "objective": str(detail.get("objective") or "").strip(),
        "current_state": str(detail.get("current_state") or "").strip(),
        "operator_posture": str(detail.get("operator_posture") or mission_summary.get("operator_posture") or "").strip(),
        "autonomy_state": str(control_tower.get("autonomy_state") or "").strip(),
        "blocked_reason": str(mission_summary.get("blocked_reason") or "").strip() or None,
        "latest_meaningful_activity": _project_latest_meaningful_activity(detail),
        "recommended_next_step": str(mission_summary.get("recommended_next_step") or "").strip(),
    }


def _timeline_agent_run_item(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(run.get("run_id") or "").strip(),
        "role": str(run.get("role_label") or run.get("role") or "").strip(),
        "status": str(run.get("status") or "").strip(),
        "summary": str(run.get("summary") or "").strip(),
        "trigger_reason": str(run.get("trigger_reason") or "").strip(),
        "created_at": str(run.get("created_at") or "").strip(),
        "artifact_ref": str(run.get("path") or "").strip(),
    }


def _timeline_trigger_item(trigger: dict[str, Any]) -> dict[str, Any]:
    evaluation = trigger.get("evaluation") if isinstance(trigger.get("evaluation"), dict) else {}
    return {
        "trigger_id": str(trigger.get("trigger_id") or "").strip(),
        "trigger_kind": str(trigger.get("trigger_kind") or "").strip(),
        "status": str(trigger.get("status") or "").strip(),
        "reason": str(trigger.get("reason") or "").strip(),
        "target_role": str(trigger.get("target_role") or "").strip(),
        "allowed_action": str(trigger.get("allowed_action") or "").strip(),
        "created_at": str(trigger.get("created_at") or "").strip(),
        "blocked_reason": str(evaluation.get("blocked_reason") or trigger.get("blocked_reason") or "").strip() or None,
        "artifact_ref": str(trigger.get("path") or "").strip(),
    }


def _timeline_intervention_item(intervention: dict[str, Any]) -> dict[str, Any]:
    return {
        "intervention_id": str(intervention.get("intervention_id") or "").strip(),
        "action": str(intervention.get("action") or "").strip(),
        "status": str(intervention.get("status") or "").strip(),
        "reason": str(intervention.get("reason") or "").strip(),
        "blocked_reason": str(intervention.get("blocked_reason") or "").strip() or None,
        "created_at": str(intervention.get("created_at") or "").strip(),
        "artifact_refs": [str(item).strip() for item in intervention.get("changed_paths", []) if str(item).strip()],
    }


def _expedition_timeline_api_item(mission_id: str) -> dict[str, Any]:
    _sync_mission_storage()
    mission = normalize_mission_id(mission_id)
    agent_runs = sorted(
        _read_agent_runs(mission),
        key=lambda item: (str(item.get("created_at") or ""), str(item.get("path") or "")),
        reverse=True,
    )[:10]
    triggers = sorted(
        _read_trigger_records(mission),
        key=lambda item: (str(item.get("created_at") or ""), str(item.get("path") or "")),
        reverse=True,
    )[:10]
    interventions = sorted(
        _read_operator_interventions(mission),
        key=lambda item: (str(item.get("created_at") or ""), str(item.get("intervention_id") or "")),
        reverse=True,
    )[:10]
    retry_ledger = _read_retry_ledger(mission)
    timestamps = {
        "latest_agent_run_at": str(agent_runs[0].get("created_at") or "").strip() if agent_runs else "",
        "latest_trigger_at": str(triggers[0].get("created_at") or "").strip() if triggers else "",
        "latest_intervention_at": str(interventions[0].get("created_at") or "").strip() if interventions else "",
        "last_retry_at": str(retry_ledger.get("last_retry_at") or "").strip(),
        "updated_at": _latest_mtime([
            _agent_runs_dir(mission),
            _triggers_dir(mission),
            _interventions_dir(mission),
            _retry_ledger_path(mission),
        ]),
    }

    artifact_refs: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    for kind, rows in (("agent_run", agent_runs), ("trigger", triggers)):
        for row in rows:
            ref = str(row.get("path") or "").strip()
            if not ref or ref in seen_refs:
                continue
            seen_refs.add(ref)
            artifact_refs.append({
                "kind": kind,
                "artifact_ref": ref,
                "created_at": str(row.get("created_at") or "").strip(),
            })
    for row in interventions:
        for ref in [str(item).strip() for item in row.get("changed_paths", []) if str(item).strip()]:
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
            artifact_refs.append({
                "kind": "intervention_change",
                "artifact_ref": ref,
                "created_at": str(row.get("created_at") or "").strip(),
            })

    return {
        "mission_id": mission,
        "recent_agent_runs": [_timeline_agent_run_item(item) for item in agent_runs],
        "recent_triggers": [_timeline_trigger_item(item) for item in triggers],
        "recent_interventions": [_timeline_intervention_item(item) for item in interventions],
        "retries_summary": {
            "retry_budget_total": int(retry_ledger.get("retry_budget_total") or 0),
            "retry_budget_used": int(retry_ledger.get("retry_budget_used") or 0),
            "last_retry_at": str(retry_ledger.get("last_retry_at") or "").strip(),
            "last_failure_reason": str(retry_ledger.get("last_failure_reason") or "").strip(),
            "stop_reason": str(retry_ledger.get("stop_reason") or "").strip(),
            "recent_decisions": [
                {
                    "decided_at": str(item.get("decided_at") or "").strip(),
                    "decision": str(item.get("decision") or "").strip(),
                    "retry_reason": str(item.get("retry_reason") or item.get("why_retried") or "").strip(),
                    "why_blocked": str(item.get("why_blocked") or "").strip() or None,
                }
                for item in list(retry_ledger.get("decision_log") or [])[-5:]
                if isinstance(item, dict)
            ],
        },
        "timestamps": timestamps,
        "artifact_refs": artifact_refs[:20],
    }


def _latest_mirror_reflection(mission_id: str) -> tuple[dict[str, Any] | None, str]:
    _sync_mission_storage()
    mission = normalize_mission_id(mission_id)
    mirror_notes = _read_mirror_notes(mission)
    latest_note = mirror_notes[0] if mirror_notes else None
    if not isinstance(latest_note, dict):
        return None, ""
    path_text = str(latest_note.get("path") or "").strip()
    if not path_text:
        return None, ""
    payload = _load_json(_relative_or_absolute(path_text))
    if not isinstance(payload, dict):
        return None, ""
    return payload, path_text


def _expedition_interpretation_api_item(mission_id: str) -> dict[str, Any] | None:
    reflection, _path_text = _latest_mirror_reflection(mission_id)
    if not isinstance(reflection, dict):
        return None
    return {
        "summary": str(reflection.get("summary") or "").strip(),
        "patterns": [str(item).strip() for item in reflection.get("patterns", []) if str(item).strip()],
        "contradictions": [str(item).strip() for item in reflection.get("contradictions", []) if str(item).strip()],
        "suggested_focus": [str(item).strip() for item in reflection.get("suggested_focus", []) if str(item).strip()],
    }


def _interpretation_mode_error(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if not normalized:
        return ""
    if normalized in {"strict", "interpretive"}:
        return "mode parameter is deferred because only one existing Mirror-derived interpretation surface is available"
    return "mode must be one of: strict, interpretive"


def _expedition_signals_api_item(mission_id: str) -> dict[str, Any]:
    detail = _build_expedition_detail(mission_id)
    mission_summary = detail.get("mission_summary") if isinstance(detail.get("mission_summary"), dict) else {}
    control_tower = detail.get("control_tower_summary") if isinstance(detail.get("control_tower_summary"), dict) else {}
    queue_hygiene = detail.get("queue_hygiene") if isinstance(detail.get("queue_hygiene"), dict) else {}
    interpretation, _path_text = _latest_mirror_reflection(mission_id)
    contradictions = [
        str(item).strip()
        for item in ((interpretation or {}).get("contradictions") or [])
        if str(item).strip()
    ]

    latest_activity = _project_latest_meaningful_activity(detail)
    activity = None
    if isinstance(latest_activity, dict):
        activity = {
            "status": "active",
            "kind": str(latest_activity.get("kind") or "").strip(),
            "role": str(latest_activity.get("role") or "").strip(),
            "summary": str(latest_activity.get("summary") or "").strip(),
            "created_at": str(latest_activity.get("created_at") or "").strip(),
        }

    blocked_reason = (
        str(mission_summary.get("blocked_reason") or "").strip()
        or str(control_tower.get("last_blocked_reason") or "").strip()
    )
    blocked = None
    if blocked_reason or str(control_tower.get("autonomy_state") or "").strip() == "blocked":
        blocked = {
            "present": True,
            "reason": blocked_reason or str(control_tower.get("operator_attention_reason") or "").strip(),
            "operator_posture": str(detail.get("operator_posture") or "").strip(),
            "autonomy_state": str(control_tower.get("autonomy_state") or "").strip(),
        }

    contradiction = None
    if contradictions:
        contradiction = {
            "present": True,
            "count": len(contradictions),
            "summary": contradictions[0],
        }

    stall = None
    if bool(queue_hygiene.get("stale_candidate")) or bool(queue_hygiene.get("blocked_candidate")):
        signals = [str(item).strip() for item in queue_hygiene.get("signals", []) if str(item).strip()]
        stall = {
            "present": True,
            "summary": signals[0] if signals else str(queue_hygiene.get("recommendation_reason") or "").strip(),
            "last_activity_at": str(queue_hygiene.get("last_activity_at") or "").strip(),
            "last_activity_age_days": queue_hygiene.get("last_activity_age_days"),
        }

    handoff = None
    active_handoff = control_tower.get("active_role_handoff") if isinstance(control_tower.get("active_role_handoff"), dict) else {}
    if active_handoff:
        handoff = {
            "present": True,
            "status": str(active_handoff.get("status") or "").strip(),
            "target_role": str(active_handoff.get("target_role") or "").strip(),
            "allowed_action": str(active_handoff.get("allowed_action") or "").strip(),
            "reason": str(active_handoff.get("reason") or "").strip(),
            "updated_at": str(active_handoff.get("updated_at") or "").strip(),
        }

    return {
        "mission_id": str(detail.get("mission_id") or "").strip(),
        "activity": activity,
        "blocked": blocked,
        "contradiction": contradiction,
        "stall": stall,
        "handoff": handoff,
    }


def _replay_event_key(kind: str, created_at: str, artifact_ref: str, identity: str) -> str:
    seed = "|".join([kind, created_at, artifact_ref, identity])
    return f"{kind}_{_short_digest(seed)}"


def _timeline_event_record(kind: str, item: dict[str, Any]) -> dict[str, Any] | None:
    created_at = str(item.get("created_at") or "").strip()
    if not created_at:
        return None
    artifact_ref = str(item.get("artifact_ref") or "").strip()
    if kind == "agent_run":
        identity = str(item.get("run_id") or "").strip()
        return {
            "event_key": _replay_event_key(kind, created_at, artifact_ref, identity),
            "kind": kind,
            "created_at": created_at,
            "summary": str(item.get("summary") or "").strip(),
            "role": str(item.get("role") or "").strip(),
            "status": str(item.get("status") or "").strip(),
            "artifact_ref": artifact_ref,
            "run_id": identity,
        }
    if kind == "trigger":
        identity = str(item.get("trigger_id") or "").strip()
        return {
            "event_key": _replay_event_key(kind, created_at, artifact_ref, identity),
            "kind": kind,
            "created_at": created_at,
            "summary": str(item.get("reason") or item.get("trigger_kind") or "").strip(),
            "role": str(item.get("target_role") or "").strip(),
            "status": str(item.get("status") or "").strip(),
            "artifact_ref": artifact_ref,
            "trigger_id": identity,
            "trigger_kind": str(item.get("trigger_kind") or "").strip(),
            "allowed_action": str(item.get("allowed_action") or "").strip(),
        }
    if kind == "intervention":
        identity = str(item.get("intervention_id") or "").strip()
        refs = [str(ref).strip() for ref in item.get("artifact_refs", []) if str(ref).strip()]
        primary_ref = refs[0] if refs else artifact_ref
        return {
            "event_key": _replay_event_key(kind, created_at, primary_ref, identity),
            "kind": kind,
            "created_at": created_at,
            "summary": str(item.get("reason") or item.get("action") or "").strip(),
            "role": "operator",
            "status": str(item.get("status") or "").strip(),
            "artifact_ref": primary_ref,
            "intervention_id": identity,
            "action": str(item.get("action") or "").strip(),
            "artifact_refs": refs,
        }
    return None


def _expedition_replay_truth_events(mission_id: str) -> list[dict[str, Any]]:
    timeline = _expedition_timeline_api_item(mission_id)
    events: list[dict[str, Any]] = []
    for kind, field in (
        ("agent_run", "recent_agent_runs"),
        ("trigger", "recent_triggers"),
        ("intervention", "recent_interventions"),
    ):
        for item in timeline.get(field, []) or []:
            if not isinstance(item, dict):
                continue
            record = _timeline_event_record(kind, item)
            if record:
                events.append(record)
    events.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("event_key") or "")))
    for index, item in enumerate(events):
        item["event_index"] = index
    return events


_REPLAY_RELATIVE_TIME_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$", re.IGNORECASE)


def _parse_replay_relative_time(value: Any) -> timedelta:
    match = _REPLAY_RELATIVE_TIME_RE.match(str(value or ""))
    if not match:
        raise ValueError("relative_time value must look like '5m', '30s', '2h', or '1d'")
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if amount <= 0:
        raise ValueError("relative_time value must be greater than zero")
    if unit == "s":
        return timedelta(seconds=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    return timedelta(days=amount)


def _encode_replay_window_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"rw_{_short_digest(raw.decode('utf-8'))}_{token}"


def _decode_replay_window_payload(replay_window_id: str) -> dict[str, Any]:
    value = str(replay_window_id or "").strip()
    if not value.startswith("rw_"):
        raise ValueError("invalid replay_window_id")
    parts = value.split("_", 2)
    if len(parts) != 3:
        raise ValueError("invalid replay_window_id")
    token = parts[2]
    padding = "=" * (-len(token) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(token + padding).decode("utf-8"))
    except Exception as exc:
        raise ValueError("invalid replay_window_id") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid replay_window_id")
    return payload


def _build_replay_window(mission_id: str, mode: str, value: Any) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    events = _expedition_replay_truth_events(mission)
    if not events:
        raise ValueError("replay window unavailable because no mission timeline events are available")

    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode == "event_count":
        try:
            count = int(value)
        except Exception as exc:
            raise ValueError("event_count value must be an integer") from exc
        if count <= 0:
            raise ValueError("event_count value must be greater than zero")
        window_events = events[-count:]
    elif normalized_mode == "relative_time":
        delta = _parse_replay_relative_time(value)
        latest_time = parse_iso(str(events[-1].get("created_at") or ""))
        if latest_time is None:
            raise ValueError("relative_time replay window requires timeline events with timestamps")
        window_start_threshold = latest_time - delta
        window_events = [
            item for item in events
            if (parse_iso(str(item.get("created_at") or "")) or latest_time) >= window_start_threshold
        ]
    else:
        raise ValueError("mode must be one of: relative_time, event_count")

    if not window_events:
        raise ValueError("replay window contains no events")

    payload = {
        "mission_id": mission,
        "window_start": str(window_events[0].get("created_at") or "").strip(),
        "window_end": str(window_events[-1].get("created_at") or "").strip(),
        "event_keys": [str(item.get("event_key") or "").strip() for item in window_events],
    }
    return {
        "replay_window_id": _encode_replay_window_payload(payload),
        "mission_id": mission,
        "window_start": payload["window_start"],
        "window_end": payload["window_end"],
        "event_count": len(window_events),
        "available_directions": ["forward", "reverse"],
        "truth_frozen": True,
    }


def _replay_window_events(mission_id: str, replay_window_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = _decode_replay_window_payload(replay_window_id)
    mission = normalize_mission_id(mission_id)
    if str(payload.get("mission_id") or "").strip() != mission:
        raise ValueError("replay_window_id does not belong to this mission")
    event_keys = [str(item).strip() for item in payload.get("event_keys", []) if str(item).strip()]
    if not event_keys:
        raise ValueError("replay_window_id contains no events")
    event_map = {
        str(item.get("event_key") or "").strip(): item
        for item in _expedition_replay_truth_events(mission)
        if isinstance(item, dict)
    }
    window_events = [event_map[key] for key in event_keys if key in event_map]
    if not window_events:
        raise ValueError("replay window events are no longer available from mission-local truth")
    for index, item in enumerate(window_events):
        item["window_index"] = index
    return payload, window_events


def _resolve_replay_cursor_index(
    events: list[dict[str, Any]],
    *,
    cursor_index: Any = None,
    cursor_time: str = "",
    direction: str = "forward",
) -> int:
    if not events:
        raise ValueError("replay window contains no events")
    if cursor_index is not None and cursor_index != "":
        index = int(cursor_index)
        if index < 0 or index >= len(events):
            raise ValueError("cursor_index is outside the replay window")
        return index
    if cursor_time:
        for index, item in enumerate(events):
            if str(item.get("created_at") or "").strip() == cursor_time:
                return index
        raise ValueError("cursor_time is outside the replay window")
    return len(events) - 1 if str(direction or "").strip().lower() == "reverse" else 0


def _normalize_replay_direction(direction: str, *, default: str = "forward") -> str:
    normalized = str(direction or "").strip().lower() or default
    if normalized not in {"forward", "reverse"}:
        raise ValueError("direction must be one of: forward, reverse")
    return normalized


def _normalize_replay_speed(value: Any) -> float:
    if value in (None, ""):
        return 1.0
    speed = float(value)
    if speed <= 0:
        raise ValueError("speed must be greater than zero")
    return speed


def _build_replay_cursor_state(
    mission_id: str,
    replay_window_id: str,
    action: str,
    *,
    cursor_position: Any = None,
    cursor_time: str = "",
    direction: str = "",
    speed: Any = None,
) -> dict[str, Any]:
    _payload, events = _replay_window_events(mission_id, replay_window_id)
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in {"play", "pause", "reverse", "step_forward", "step_backward", "jump"}:
        raise ValueError("action must be one of: play, pause, reverse, step_forward, step_backward, jump")

    effective_direction = _normalize_replay_direction(direction, default="forward")
    index = _resolve_replay_cursor_index(events, cursor_index=cursor_position, cursor_time=cursor_time, direction=effective_direction)
    paused = normalized_action == "pause"
    effective_speed = _normalize_replay_speed(speed)

    if normalized_action == "play":
        paused = False
    elif normalized_action == "reverse":
        paused = False
        effective_direction = "reverse"
    elif normalized_action == "step_forward":
        effective_direction = "forward"
        paused = True
        index = min(len(events) - 1, index + 1)
    elif normalized_action == "step_backward":
        effective_direction = "reverse"
        paused = True
        index = max(0, index - 1)
    elif normalized_action == "jump":
        paused = True

    current = events[index]
    return {
        "replay_window_id": replay_window_id,
        "cursor_time": str(current.get("created_at") or "").strip(),
        "cursor_index": index,
        "direction": effective_direction,
        "speed": effective_speed,
        "paused": paused,
    }


def _replay_activity_signal(event: dict[str, Any]) -> dict[str, Any]:
    role = str(event.get("role") or "").strip()
    summary = str(event.get("summary") or "").strip()
    kind = str(event.get("kind") or "").strip()
    return {
        "status": "active",
        "kind": kind,
        "role": role,
        "summary": summary,
        "created_at": str(event.get("created_at") or "").strip(),
    }


def _replay_mirror_observation(event: dict[str, Any], interpretation: dict[str, Any] | None, signals: dict[str, Any], direction: str) -> str:
    summary = str(event.get("summary") or "").strip() or str(event.get("kind") or "").strip()
    role = str(event.get("role") or "").strip() or "mission-local activity"
    contradiction = (signals.get("contradiction") or {}) if isinstance(signals.get("contradiction"), dict) else {}
    blocked = (signals.get("blocked") or {}) if isinstance(signals.get("blocked"), dict) else {}
    mirror_summary = str((interpretation or {}).get("summary") or "").strip()

    clauses = [f"Mirror observes: {role} is visible as {summary}."]
    if contradiction.get("present"):
        clauses.append(f"Mirror detects: contradiction remains present ({str(contradiction.get('summary') or '').strip()}).")
    elif blocked.get("present"):
        clauses.append(f"Mirror notes: the mission remains blocked ({str(blocked.get('reason') or '').strip()}).")
    elif mirror_summary:
        clauses.append(f"Mirror notes: {mirror_summary}")
    if direction == "reverse":
        clauses.append("Mirror notes: reverse traversal changes view order, not causality.")
    return " ".join(clause for clause in clauses if clause)


def _replay_observer_note(direction: str) -> str:
    if direction == "reverse":
        return "Direction reversed. Truth is unchanged; interpretation is current."
    return "Truth is unchanged; interpretation is current."


def _replay_frame_context(events: list[dict[str, Any]], index: int) -> dict[str, Any]:
    current = events[index]
    previous_event = events[index - 1] if index > 0 else None
    next_event = events[index + 1] if index + 1 < len(events) else None
    nearby_events = events[max(0, index - 1): min(len(events), index + 2)]
    return {
        "window_start": str(events[0].get("created_at") or "").strip(),
        "window_end": str(events[-1].get("created_at") or "").strip(),
        "event_count": len(events),
        "current_event": current,
        "previous_event": previous_event,
        "next_event": next_event,
        "nearby_events": nearby_events,
    }


def _build_replay_frame(
    mission_id: str,
    replay_window_id: str,
    *,
    cursor_index: Any = None,
    cursor_time: str = "",
    direction: str = "",
    lens: str = "",
) -> dict[str, Any]:
    _payload, events = _replay_window_events(mission_id, replay_window_id)
    effective_direction = _normalize_replay_direction(direction, default="forward")
    index = _resolve_replay_cursor_index(events, cursor_index=cursor_index, cursor_time=cursor_time, direction=effective_direction)
    current = events[index]

    signals = _expedition_signals_api_item(mission_id)
    signals["activity"] = _replay_activity_signal(current)
    interpretation = _expedition_interpretation_api_item(mission_id)

    return {
        "mission_id": normalize_mission_id(mission_id),
        "replay_window_id": replay_window_id,
        "cursor_time": str(current.get("created_at") or "").strip(),
        "cursor_index": index,
        "direction": effective_direction,
        "lens": str(lens or "").strip() or None,
        "frame_context": _replay_frame_context(events, index),
        "active_signals": signals,
        "mirror_observation": _replay_mirror_observation(current, interpretation, signals, effective_direction),
        "observer_note": _replay_observer_note(effective_direction),
        "artifact_fidelity": {
            "chat_output_unchanged": True,
            "mission_state_unchanged": True,
            "artifacts_unchanged": True,
        },
    }


def _normalize_mission_objective(objective: str) -> str:
    text = re.sub(r"[^\w\s]+", " ", str(objective or "").lower().strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _list_expeditions() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _sync_mission_storage()
    return mission_read_model._list_expeditions(helpers=_mission_read_model_helpers())


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


def _mission_agent_name(mission_id: str) -> str:
    mission = normalize_mission_id(mission_id)
    return normalize_mission_id(f"mission_agent_{mission}_expeditioner")


def _mission_agent_soul_text(mission_id: str, objective: str, agent_id: str) -> str:
    mission = normalize_mission_id(mission_id)
    expedition_ref = _mission_root(mission).relative_to(ROOT).as_posix()
    workbench_ref = _workbench_root(mission).relative_to(ROOT).as_posix()
    return (
        f"# SOUL: {agent_id}\n\n"
        "## Identity\n"
        f"- Mission agent id: `{agent_id}`\n"
        f"- Mission id: `{mission}`\n"
        "- Runtime role: `spinetop-expeditioner`\n"
        f"- Objective: {objective}\n\n"
        "## Bounded Scope\n"
        f"- You operate only for mission `{mission}`.\n"
        f"- Read scope is limited to mission-local expedition context under `{expedition_ref}` and mission-local workbench context under `{workbench_ref}`.\n"
        "- Do not widen scope to other missions, collective memory, dispatch-approved state, governance state, or Honcho.\n"
        "- Do not self-start loops, schedules, retries, or follow-on autonomy beyond the explicit mission trigger already granted.\n\n"
        "## Return Discipline\n"
        "- Produce derived mission-local outputs only.\n"
        "- Return work through existing bounded lanes: mission-local workbench artifacts, runner-return-compatible notes, assumption lanes, and control-tower-compatible review lanes.\n"
        "- Keep outputs inspectable, structured, and reviewable by the spine.\n"
        "- If a result could affect truth, approval, promotion, dispatch, or bridge state, stop and return a bounded review artifact instead.\n\n"
        "## Hard Prohibitions\n"
        "- No truth writes.\n"
        "- No governance bypass.\n"
        "- No direct writes to `memory/collective`.\n"
        "- No direct writes to `memory/dispatch/approved`.\n"
        "- No writes to Honcho or bridge submission paths.\n"
        "- No mutation of canonical mission state beyond allowed mission-local derived artifacts.\n"
        "- No fake completion claims, fabricated evidence, or silent guessing.\n\n"
        "## Blocked / Uncertain Behavior\n"
        "- If blocked, return to base with bounded options, blockers, and the smallest safe next actions.\n"
        "- If uncertain, prefer an inspectable partial return with explicit assumptions over an ungrounded answer.\n"
        "- If evidence is missing, say what is missing and where the bounded return should be reviewed.\n"
    )


def _create_mission_agent_identity(mission_id: str, objective: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    created_at = iso_now()
    agent_id = _mission_agent_name(mission)
    config_root = _mission_agent_root(mission, ensure=True)
    soul_path = _mission_agent_soul_path(mission, ensure=True)
    profile_path = _mission_agent_profile_path(mission, ensure=True)
    soul_path.write_text(_mission_agent_soul_text(mission, objective, agent_id), encoding="utf-8")
    profile = {
        "agent_id": agent_id,
        "mission_id": mission,
        "role_id": EXPEDITIONER_ROLE_ID,
        "status": "bounded_active",
        "created_at": created_at,
        "config_root": config_root.relative_to(ROOT).as_posix(),
        "mission_root": _mission_root(mission).relative_to(ROOT).as_posix(),
        "workbench_root": _workbench_root(mission).relative_to(ROOT).as_posix(),
        "soul_ref": soul_path.relative_to(ROOT).as_posix(),
        "operator_chat_required": False,
        "scope": {
            "mission_local_only": True,
            "expedition_root_ref": _mission_root(mission).relative_to(ROOT).as_posix(),
            "workbench_root_ref": _workbench_root(mission).relative_to(ROOT).as_posix(),
        },
        "return_path_policy": {
            "allowed_lanes": [
                "workbench/missions/<mission_id>/notes/",
                "workbench/missions/<mission_id>/outputs/",
                "workbench/missions/<mission_id>/notes/runner_returns/",
                "workbench/missions/<mission_id>/notes/assumptions/",
                "control-tower-compatible mission detail and review lanes",
            ],
            "must_use_existing_governed_paths": True,
            "parallel_truth_path_forbidden": True,
        },
        "forbidden_writes": [
            "memory/collective/",
            "memory/dispatch/approved/",
            "logs/governance/",
            "services/honcho/",
            "Honcho",
        ],
        "constraints": {
            "no_autonomy_loops": True,
            "no_truth_writes": True,
            "no_governance_bypass": True,
            "mission_local_only": True,
            "fake_completion_forbidden": True,
        },
    }
    _write_json(profile_path, profile)
    upsert_artifact_index_entry(mission, "mission_agent_profile", profile_path, created_at=created_at)
    upsert_artifact_index_entry(mission, "mission_agent_soul", soul_path, created_at=created_at)
    return profile


def _read_mission_agent_profile(mission_id: str) -> dict[str, Any] | None:
    profile = _load_json(_mission_agent_profile_path(mission_id))
    return profile if isinstance(profile, dict) else None


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


QUEUE_STALE_DAYS = 7
QUEUE_LONG_PARKED_DAYS = 14
QUEUE_BLOCKED_IDLE_DAYS = 5
QUEUE_JUNK_OBJECTIVE_RE = re.compile(
    r"^(?:test|tmp|temp|temporary|debug|scratch|demo|dummy|junk|throwaway|foo|bar|asdf)\b"
)


def _days_since(timestamp: str, *, now: datetime | None = None) -> float | None:
    parsed = parse_iso(timestamp)
    if parsed is None:
        return None
    current = now or datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (current - parsed).total_seconds() / 86400.0)


def _queue_last_activity_at(detail: dict[str, Any]) -> str:
    mission_summary = detail.get("mission_summary") if isinstance(detail.get("mission_summary"), dict) else {}
    parking_status = detail.get("parking_status") if isinstance(detail.get("parking_status"), dict) else {}
    candidates = [
        str(mission_summary.get("last_operator_reply_at") or "").strip(),
        str(parking_status.get("updated_at") or "").strip(),
        str(detail.get("last_updated") or "").strip(),
        str(detail.get("created_at") or "").strip(),
    ]
    return next((value for value in candidates if value), "")


def _queue_sort_timestamp(detail: dict[str, Any]) -> str:
    return _queue_last_activity_at(detail) or str(detail.get("created_at") or "").strip() or str(detail.get("last_updated") or "").strip()


def _queue_hygiene_flags(
    detail: dict[str, Any],
    *,
    duplicate_count: int,
    duplicate_rank: int,
    primary_mission_id: str,
    primary_last_updated: str,
    normalized_objective: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    mission_summary = detail.get("mission_summary") if isinstance(detail.get("mission_summary"), dict) else {}
    parking_status = detail.get("parking_status") if isinstance(detail.get("parking_status"), dict) else {}
    control_tower_summary = detail.get("control_tower_summary") if isinstance(detail.get("control_tower_summary"), dict) else {}
    archive_marker = _read_archive_candidate_marker(str(detail.get("mission_id") or ""))
    current_state = str(detail.get("current_state") or "").strip()
    operator_posture = str(detail.get("operator_posture") or mission_summary.get("operator_posture") or "").strip()
    triage_bucket = str(detail.get("triage_bucket") or mission_summary.get("triage_bucket") or "").strip()
    status_badge = str(detail.get("status_badge") or "").strip()
    blocked_reason = str(mission_summary.get("blocked_reason") or control_tower_summary.get("last_blocked_reason") or "").strip()
    objective = str(detail.get("objective") or "").strip()
    parked = str(parking_status.get("status") or "active").strip() == "parked" or operator_posture == "parked" or triage_bucket == "parked"
    review_ready = (
        status_badge == "ready_for_review"
        or triage_bucket == "review"
        or current_state in {"PACKAGE_READY", "BRIDGE_CONSIDERATION", "ARCHIVE_REVIEW"}
    )
    blocked = not parked and (
        operator_posture == "needs_operator_answer"
        or triage_bucket == "waiting"
        or (status_badge == "waiting_for_user" and not review_ready)
    )
    last_activity_at = _queue_last_activity_at(detail)
    last_activity_age_days = _days_since(last_activity_at, now=now)
    parked_age_days = _days_since(str(parking_status.get("parked_at") or "").strip(), now=now)
    stale_candidate = bool(last_activity_age_days is not None and last_activity_age_days >= QUEUE_STALE_DAYS and not review_ready)
    long_parked = bool(parked and parked_age_days is not None and parked_age_days >= QUEUE_LONG_PARKED_DAYS)
    blocked_without_new_input = bool(blocked and last_activity_age_days is not None and last_activity_age_days >= QUEUE_BLOCKED_IDLE_DAYS)
    superseded_by_newer_similar = bool(
        duplicate_count > 1
        and duplicate_rank > 1
        and primary_mission_id
        and primary_mission_id != str(detail.get("mission_id") or "")
        and str(primary_last_updated or "") >= _queue_sort_timestamp(detail)
    )
    junk_pattern = bool(normalized_objective and len(normalized_objective) <= 48 and QUEUE_JUNK_OBJECTIVE_RE.match(normalized_objective))
    archive_candidate = bool(
        long_parked
        or superseded_by_newer_similar
        or (junk_pattern and stale_candidate)
        or (current_state in {"MISSION_CLOSED", "ARCHIVE_REVIEW"} and stale_candidate)
        or archive_marker
    )

    signals: list[str] = []
    if duplicate_count > 1:
        signals.append(f"{duplicate_count} missions share the same normalized objective.")
    if stale_candidate and last_activity_age_days is not None:
        signals.append(f"No recent mission-local activity for {round(last_activity_age_days, 1)} day(s).")
    if long_parked and parked_age_days is not None:
        signals.append(f"Mission has been parked for {round(parked_age_days, 1)} day(s).")
    if blocked_without_new_input:
        signals.append("Mission is blocked and has not received fresh operator input recently.")
    if superseded_by_newer_similar:
        signals.append(f"A newer similar mission ({primary_mission_id}) looks like the active primary.")
    if junk_pattern:
        signals.append("Objective matches a safely identifiable test-like or throwaway pattern.")
    if archive_marker:
        signals.append("Operator explicitly marked this mission as an archive candidate in mission-local notes.")
    if review_ready:
        signals.append("Mission already has a review-ready posture.")

    recommended_action = "inspect before action"
    recommendation_reason = "The mission needs operator review before any queue cleanup decision."
    if review_ready:
        recommended_action = "inspect before action"
        recommendation_reason = "Review-ready missions should be checked before parking or archiving."
    elif archive_candidate:
        recommended_action = "archive candidate"
        recommendation_reason = "Signals suggest this mission can be marked for archive review without deleting anything."
    elif superseded_by_newer_similar or (duplicate_count > 1 and duplicate_rank > 1):
        recommended_action = "collapse duplicate"
        recommendation_reason = "This mission appears to be a duplicate or follower in a similar-objective group."
    elif stale_candidate and not parked:
        recommended_action = "park"
        recommendation_reason = "This mission looks stale enough to quiet safely without removing it."
    elif not blocked and not parked:
        recommended_action = "keep active"
        recommendation_reason = "This mission still looks like an active working queue item."

    return {
        "last_activity_at": last_activity_at,
        "last_activity_age_days": None if last_activity_age_days is None else round(last_activity_age_days, 2),
        "parked_age_days": None if parked_age_days is None else round(parked_age_days, 2),
        "duplicate_candidate": duplicate_count > 1,
        "stale_candidate": stale_candidate,
        "blocked_candidate": blocked,
        "parked_candidate": parked,
        "review_ready": review_ready,
        "archive_candidate": archive_candidate,
        "archive_candidate_marked": bool(archive_marker),
        "superseded_by_newer_similar": superseded_by_newer_similar,
        "junk_pattern": junk_pattern,
        "signals": signals[:6],
        "recommended_action": recommended_action,
        "recommendation_reason": recommendation_reason,
    }


def _queue_summary_from_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    total_queued = len(items)
    parked = sum(1 for item in items if bool((item.get("queue_hygiene") or {}).get("parked_candidate")))
    blocked = sum(1 for item in items if bool((item.get("queue_hygiene") or {}).get("blocked_candidate")))
    review_ready = sum(1 for item in items if bool((item.get("queue_hygiene") or {}).get("review_ready")))
    duplicate_candidates = sum(
        1 for item in items if bool((item.get("queue_hygiene") or {}).get("duplicate_candidate")) and not bool(item.get("is_group_primary"))
    )
    stale_candidates = sum(1 for item in items if bool((item.get("queue_hygiene") or {}).get("stale_candidate")))
    archive_candidates = sum(1 for item in items if bool((item.get("queue_hygiene") or {}).get("archive_candidate")))
    active = max(0, total_queued - parked - blocked - review_ready)
    return {
        "total_queued": total_queued,
        "active": active,
        "parked": parked,
        "blocked": blocked,
        "duplicate_candidates": duplicate_candidates,
        "stale_candidates": stale_candidates,
        "review_ready": review_ready,
        "archive_close_candidates": archive_candidates,
    }


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
            payload = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload.setdefault("system_signals", [])
                payload.setdefault("signal_count", len(payload.get("system_signals") or []))
                payload.setdefault("learning_summary", {
                    "stored_path": "workbench/system/operator_learning/nanny_pattern_memory.json",
                    "updated_at": "",
                    "counts": {},
                    "weak_question_count": 0,
                })
                payload.setdefault("derived_counts", {})
                return payload
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
        "system_signals": [],
        "signal_count": 0,
        "learning_summary": {
            "stored_path": "workbench/system/operator_learning/nanny_pattern_memory.json",
            "updated_at": "",
            "counts": {},
            "weak_question_count": 0,
        },
        "derived_counts": {},
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


def read_helper_2b_runtime_status() -> dict[str, Any]:
    try:
        profile = load_helper_runtime_profile("spinetop-helper-2b")
    except Exception as exc:
        return {
            "available": False,
            "configured": False,
            "enabled": False,
            "role_id": "spinetop-helper-2b",
            "role_description": "Spinetop-helper_2b is the mission-local field helper for tactical support.",
            "liveness": "unavailable",
            "error": str(exc),
        }

    provider = ""
    model = ""
    try:
        model_registry_payload = json.loads((ROOT / "config" / "model_registry.json").read_text(encoding="utf-8"))
        models = model_registry_payload.get("models", {}) if isinstance(model_registry_payload, dict) else {}
        if isinstance(models, dict) and profile.default_model_key:
            model_entry = models.get(profile.default_model_key, {})
            if isinstance(model_entry, dict):
                provider = str(model_entry.get("provider") or "").strip()
                model = str(model_entry.get("model") or "").strip()
    except Exception:
        provider = ""
        model = ""

    enabled = profile.execution_backend == "model_backed"
    return {
        "available": True,
        "configured": True,
        "enabled": enabled,
        "role_id": profile.role_id,
        "role_description": profile.role_description,
        "execution_backend": profile.execution_backend,
        "provider_requirement": profile.provider_requirement,
        "default_model_key": profile.default_model_key,
        "fallback_model_key": profile.fallback_model_key,
        "provider": provider,
        "model": model,
        "mapped_helpers": profile.mapped_helpers,
        "authority_boundary": profile.authority_boundary,
        "context_refs": profile.context_refs,
        "config_refs": profile.config_refs,
        "support_write_scope": profile.support_write_scope,
        "inactive_behavior": profile.inactive_behavior,
        "liveness": "model_backed_ready" if enabled else "disabled_safe_inactive",
        "notes": [
            "Field-helper work stays bounded to helper-local support lanes.",
            "Spinetop-helper_2b is not Sentinel, Expeditioner, or Mirror.",
            "Spinetop-helper_2b does not approve, create truth, or bypass governance.",
            "If runtime is inactive, the seam stays disabled-safe and returns structured receipts only.",
        ],
    }


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
        "helper_2b_runtime": read_helper_2b_runtime_status(),
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
    return mission_api_routes.handle_expeditions_list(_ROUTE_API)


@app.get("/api/expeditions/<mission_id>")
def api_expedition_detail(mission_id: str):
    return mission_api_routes.handle_expedition_detail(_ROUTE_API, mission_id)


@app.get("/api/expeditions/<mission_id>/state")
def api_expedition_state(mission_id: str):
    return mission_api_routes.handle_expedition_state(_ROUTE_API, mission_id)


@app.get("/api/expeditions/<mission_id>/timeline")
def api_expedition_timeline(mission_id: str):
    return mission_api_routes.handle_expedition_timeline(_ROUTE_API, mission_id)


@app.get("/api/expeditions/<mission_id>/interpretation")
def api_expedition_interpretation(mission_id: str):
    return mirror_api_routes.handle_expedition_interpretation(_ROUTE_API, mission_id)


@app.get("/api/expeditions/<mission_id>/mirror-notes")
def api_expedition_mirror_notes(mission_id: str):
    return mirror_api_routes.handle_expedition_mirror_notes(_ROUTE_API, mission_id)


@app.get("/api/expeditions/<mission_id>/signals")
def api_expedition_signals(mission_id: str):
    return mirror_api_routes.handle_expedition_signals(_ROUTE_API, mission_id)


@app.post("/api/expeditions/<mission_id>/replay/window")
def api_expedition_replay_window(mission_id: str):
    return mirror_api_routes.handle_expedition_replay_window(_ROUTE_API, mission_id)


@app.post("/api/expeditions/<mission_id>/replay/cursor")
def api_expedition_replay_cursor(mission_id: str):
    return mirror_api_routes.handle_expedition_replay_cursor(_ROUTE_API, mission_id)


@app.get("/api/expeditions/<mission_id>/replay/frame")
def api_expedition_replay_frame(mission_id: str):
    return mirror_api_routes.handle_expedition_replay_frame(_ROUTE_API, mission_id)


@app.post("/api/expeditions/<mission_id>/sync-runner-returns")
def api_expedition_sync_runner_returns(mission_id: str):
    return mission_api_routes.handle_expedition_sync_runner_returns(_ROUTE_API, mission_id)


@app.post("/api/expeditions/<mission_id>/invoke-role")
def api_expedition_invoke_role(mission_id: str):
    return mission_api_routes.handle_expedition_invoke_role(_ROUTE_API, mission_id)


@app.post("/api/expeditions/<mission_id>/refresh-assumptions")
def api_expedition_refresh_assumptions(mission_id: str):
    return mission_api_routes.handle_expedition_refresh_assumptions(_ROUTE_API, mission_id)


@app.post("/api/expeditions/<mission_id>/assumptions/<assumption_id>/confirm")
def api_expedition_confirm_assumption(mission_id: str, assumption_id: str):
    return mission_api_routes.handle_expedition_confirm_assumption(_ROUTE_API, mission_id, assumption_id)


@app.post("/api/expeditions/<mission_id>/assumptions/<assumption_id>/reject")
def api_expedition_reject_assumption(mission_id: str, assumption_id: str):
    return mission_api_routes.handle_expedition_reject_assumption(_ROUTE_API, mission_id, assumption_id)


@app.post("/api/expeditions")
def api_expeditions_create():
    return mission_api_routes.handle_expeditions_create(_ROUTE_API)


@app.post("/api/expeditions/<mission_id>/input")
def api_expedition_input(mission_id: str):
    return mission_api_routes.handle_expedition_input(_ROUTE_API, mission_id)


@app.post("/api/expeditions/<mission_id>/translate-prompt")
def api_expedition_translate_prompt(mission_id: str):
    return mission_api_routes.handle_expedition_translate_prompt(_ROUTE_API, mission_id)


@app.post("/api/expeditions/<mission_id>/parking")
def api_expedition_parking(mission_id: str):
    return mission_api_routes.handle_expedition_parking(_ROUTE_API, mission_id)


@app.post("/api/expeditions/<mission_id>/triggers")
def api_expedition_triggers_create(mission_id: str):
    return mission_api_routes.handle_expedition_triggers_create(_ROUTE_API, mission_id)


@app.post("/api/expeditions/<mission_id>/interventions")
def api_expedition_interventions(mission_id: str):
    return mission_api_routes.handle_expedition_interventions(_ROUTE_API, mission_id)


@app.post("/api/expeditions/<mission_id>/respond")
def api_expedition_respond(mission_id: str):
    return mission_api_routes.handle_expedition_respond(_ROUTE_API, mission_id)


@app.get("/api/expeditions/<mission_id>/chat")
def api_expedition_chat_get(mission_id: str):
    return mission_api_routes.handle_expedition_chat_get(_ROUTE_API, mission_id)


@app.post("/api/expeditions/<mission_id>/chat")
def api_expedition_chat(mission_id: str):
    return mission_api_routes.handle_expedition_chat(_ROUTE_API, mission_id)


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


_write_json = mission_storage._write_json
_load_json = mission_storage._load_json
_mission_root = mission_storage._mission_root
_workbench_root = mission_storage._workbench_root
_ensure_workbench_structure = mission_storage._ensure_workbench_structure
_workbench_notes_root = mission_storage._workbench_notes_root
_mission_chat_path = mission_storage._mission_chat_path
_mission_agent_root = mission_storage._mission_agent_root
_mission_agent_profile_path = mission_storage._mission_agent_profile_path
_mission_agent_soul_path = mission_storage._mission_agent_soul_path
_mission_parking_path = mission_storage._mission_parking_path
_triggers_dir = mission_storage._triggers_dir
_trigger_handoff_path = mission_storage._trigger_handoff_path
_runner_returns_dir = mission_storage._runner_returns_dir
_retry_ledger_path = mission_storage._retry_ledger_path
_assumptions_dir = mission_storage._assumptions_dir
_assumption_ledger_path = mission_storage._assumption_ledger_path
_mirror_dir = mission_storage._mirror_dir
_agent_runs_dir = mission_storage._agent_runs_dir
_interventions_dir = mission_storage._interventions_dir
_intervention_log_path = mission_storage._intervention_log_path
_archive_candidate_marker_path = mission_storage._archive_candidate_marker_path
_read_archive_candidate_marker = mission_storage._read_archive_candidate_marker
_mission_manifest_payload = mission_storage._mission_manifest_payload
_latest_mtime = mission_storage._latest_mtime
_read_runner_returns = mission_storage._read_runner_returns
_read_mirror_notes = mission_storage._read_mirror_notes
_read_agent_runs = mission_storage._read_agent_runs
_workbench_files = mission_storage._workbench_files
_mission_inputs = mission_storage._mission_inputs
_read_jsonl = mission_storage._read_jsonl
_append_jsonl = mission_storage._append_jsonl
_default_parking_status = mission_storage._default_parking_status
_read_parking_status = mission_storage._read_parking_status
_write_parking_status = mission_storage._write_parking_status
_default_trigger_handoff = mission_storage._default_trigger_handoff
_default_retry_ledger = mission_storage._default_retry_ledger
_normalize_retry_log_items = mission_storage._normalize_retry_log_items
_read_retry_ledger = mission_storage._read_retry_ledger
_write_retry_ledger = mission_storage._write_retry_ledger
_read_trigger_handoff = mission_storage._read_trigger_handoff
_write_trigger_handoff = mission_storage._write_trigger_handoff
_read_trigger_records = mission_storage._read_trigger_records
_write_mission_input = mission_storage._write_mission_input
_write_operator_save_artifact = mission_storage._write_operator_save_artifact


def _mission_root(mission_id: str) -> Path:
    _sync_mission_storage()
    return mission_storage._mission_root(mission_id)


def _workbench_root(mission_id: str) -> Path:
    _sync_mission_storage()
    return mission_storage._workbench_root(mission_id)


def _ensure_workbench_structure(mission_id: str) -> Path:
    _sync_mission_storage()
    return mission_storage._ensure_workbench_structure(mission_id)


def _mission_parking_path(mission_id: str, *, ensure: bool = False) -> Path:
    _sync_mission_storage()
    return mission_storage._mission_parking_path(mission_id, ensure=ensure)


def _read_parking_status(mission_id: str) -> dict[str, Any]:
    _sync_mission_storage()
    return mission_storage._read_parking_status(mission_id)


def _write_parking_status(
    mission_id: str,
    *,
    status: str,
    reason: str = "",
    parked_by: str = "operator",
    resume_hint: str = "",
) -> dict[str, Any]:
    _sync_mission_storage()
    return mission_storage._write_parking_status(
        mission_id,
        status=status,
        reason=reason,
        parked_by=parked_by,
        resume_hint=resume_hint,
    )


def _write_mission_input(mission: str, content: str) -> dict[str, Any]:
    _sync_mission_storage()
    return mission_storage._write_mission_input(mission, content)


def _write_operator_save_artifact(mission: str, text: str) -> dict[str, Any]:
    _sync_mission_storage()
    return mission_storage._write_operator_save_artifact(mission, text)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5051, debug=False)
