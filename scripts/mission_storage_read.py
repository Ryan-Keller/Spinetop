from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from state_machine import normalize_mission_id

import mission_storage_core as core


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
    path = core._mission_parking_path(mission)
    if not path.exists():
        return _default_parking_status(mission)
    payload = core._load_json(path)
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
        "retry_budget_total": core.RETRY_BUDGET_TOTAL,
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
    for entry in value[-core.RETRY_LOG_LIMIT:]:
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
    path = core._retry_ledger_path(mission)
    if not path.exists():
        return _default_retry_ledger(mission)
    payload = core._load_json(path)
    if not isinstance(payload, dict):
        return _default_retry_ledger(mission)
    record = _default_retry_ledger(mission)
    record["mission_id"] = str(payload.get("mission_id") or mission).strip() or mission
    try:
        budget_total = int(payload.get("retry_budget_total") or core.RETRY_BUDGET_TOTAL)
    except Exception:
        budget_total = core.RETRY_BUDGET_TOTAL
    if budget_total < 0:
        budget_total = core.RETRY_BUDGET_TOTAL
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


def _read_trigger_handoff(mission_id: str) -> dict[str, Any]:
    path = core._trigger_handoff_path(mission_id)
    if not path.exists():
        return _default_trigger_handoff(mission_id)
    payload = core._load_json(path)
    if not isinstance(payload, dict):
        return _default_trigger_handoff(mission_id)
    record = _default_trigger_handoff(mission_id)
    for key in record:
        if key == "derived_only":
            record[key] = bool(payload.get(key, True))
        else:
            record[key] = payload.get(key, record[key])
    return record


def _read_trigger_records(mission_id: str) -> list[dict[str, Any]]:
    directory = core._triggers_dir(mission_id)
    if not directory.exists():
        return []
    records: list[dict[str, Any]] = []
    paths = (
        path
        for path in directory.glob("*.json")
        if path.is_file() and path.name != core.TRIGGER_HANDOFF_FILENAME
    )
    for path in sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True):
        payload = core._load_json(path)
        if not isinstance(payload, dict):
            continue
        record = dict(payload)
        record["path"] = path.relative_to(core.ROOT).as_posix()
        records.append(record)
    return records


def _read_runner_returns(mission_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = core._runner_returns_dir(mission_id)
    if not root.exists():
        return rows
    for path in sorted(root.glob("*.json")):
        payload = core._load_json(path)
        if not isinstance(payload, dict):
            continue
        payload["path"] = path.relative_to(core.ROOT).as_posix()
        rows.append(payload)
    rows.sort(key=lambda item: str(item.get("created_at") or item.get("path") or ""), reverse=True)
    return rows


def _read_mirror_notes(mission_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = core._mirror_dir(mission_id)
    if not root.exists():
        return rows
    paths = (path for path in root.glob("*.json") if path.is_file())
    for path in sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True):
        payload = core._load_json(path)
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
        artifact_id = str(payload.get("artifact_id") or payload.get("note_id") or payload.get("reflection_id") or path.stem).strip()
        artifact_kind = str(payload.get("artifact_kind") or payload.get("kind") or "mirror_reflection").strip() or "mirror_reflection"
        rows.append({
            "artifact_id": artifact_id,
            "note_id": artifact_id,
            "role": str(payload.get("role") or payload.get("source") or "spinetop-mirror").strip() or "spinetop-mirror",
            "artifact_kind": artifact_kind,
            "kind": artifact_kind,
            "text": summary,
            "summary": summary,
            "created_at": str(payload.get("created_at") or payload.get("updated_at") or "").strip(),
            "path": path.relative_to(core.ROOT).as_posix(),
        })
    rows.sort(key=lambda item: str(item.get("created_at") or item.get("path") or ""), reverse=True)
    return rows


def _read_agent_runs(mission_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = core._agent_runs_dir(mission_id)
    if not root.exists():
        return rows
    paths = (path for path in root.glob("*.json") if path.is_file())
    for path in sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True):
        payload = core._load_json(path)
        if not isinstance(payload, dict):
            continue
        output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
        summary = str(payload.get("summary") or output.get("result") or payload.get("result") or "").strip()
        rows.append({
            "run_id": str(payload.get("run_id") or path.stem).strip(),
            "role": str(payload.get("role") or "").strip(),
            "role_label": str(payload.get("role_label") or "").strip(),
            "kind": str(payload.get("artifact_kind") or "agent_role_invocation").strip(),
            "summary": summary,
            "created_at": str(payload.get("created_at") or "").strip(),
            "path": path.relative_to(core.ROOT).as_posix(),
            "status": str(payload.get("status") or "").strip(),
            "trigger_reason": str(payload.get("trigger_reason") or "").strip(),
            "confidence": payload.get("confidence", output.get("confidence")),
            "next_step": str(payload.get("next_step") or output.get("next_step") or "").strip(),
        })
    return rows


def _workbench_files(mission_id: str) -> list[dict[str, Any]]:
    root = core._workbench_root(mission_id)
    if not root.exists():
        return []
    files: list[dict[str, Any]] = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            stat = path.stat()
        except Exception:
            continue
        rel = path.relative_to(root)
        folder = rel.parts[0] if rel.parts else "root"
        files.append({
            "path": path.relative_to(core.ROOT).as_posix(),
            "folder": folder,
            "name": path.name,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "bytes": stat.st_size,
            "bytes_label": core._format_bytes(stat.st_size),
        })
    return files[:200]


def _mission_inputs(mission_id: str) -> list[dict[str, Any]]:
    intake_dir = core._workbench_root(mission_id) / "intake"
    if not intake_dir.exists():
        return []
    inputs: list[dict[str, Any]] = []
    paths = (path for path in intake_dir.glob("*.json") if path.is_file())
    for path in sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True):
        payload = core._load_json(path)
        if not isinstance(payload, dict):
            continue
        inputs.append({
            "input_id": str(payload.get("input_id") or path.stem),
            "mission_id": str(payload.get("mission_id") or mission_id),
            "source_type": str(payload.get("source_type") or "user_provided"),
            "status": str(payload.get("status") or "unreviewed"),
            "content": str(payload.get("content") or ""),
            "created_at": str(payload.get("created_at") or ""),
            "path": path.relative_to(core.ROOT).as_posix(),
        })
    return inputs[:200]


def _read_archive_candidate_marker(mission_id: str) -> dict[str, Any]:
    path = core._archive_candidate_marker_path(mission_id)
    if not path.exists():
        return {}
    marker = core._load_json(path)
    return marker if isinstance(marker, dict) else {}
