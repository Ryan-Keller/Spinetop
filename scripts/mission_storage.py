from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from state_machine import mission_manifest_path, normalize_mission_id

ROOT = Path(__file__).resolve().parents[1]
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
RETRY_BUDGET_TOTAL = 2
RETRY_LOG_LIMIT = 40


def configure_root(root: Path) -> None:
    global ROOT, EXPEDITIONS_ACTIVE_DIR, WORKBENCH_MISSIONS_DIR
    ROOT = Path(root)
    EXPEDITIONS_ACTIVE_DIR = ROOT / "expeditions" / "active"
    WORKBENCH_MISSIONS_DIR = ROOT / "workbench" / "missions"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_digest(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6]


def _format_bytes(value: int) -> str:
    size = max(0, int(value or 0))
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(size)
    unit = units[0]
    for candidate in units:
        unit = candidate
        if amount < 1024 or candidate == units[-1]:
            break
        amount /= 1024.0
    if unit == "B":
        return f"{int(amount)} {unit}"
    return f"{amount:.1f} {unit}"


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
            "path": path.relative_to(ROOT).as_posix(),
        })
    rows.sort(key=lambda item: str(item.get("created_at") or item.get("path") or ""), reverse=True)
    return rows


def _write_operator_save_artifact(mission_id: str, text: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    text_value = str(text or "")
    if not text_value.strip():
        raise ValueError("save detected but no content remained after `save:`; nothing was written")
    created_at = iso_now()
    artifact_id = (
        f"operator_save_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_"
        f"{_short_digest(f'{mission}|{text_value}|{created_at}')}"
    )
    artifact_path = _mirror_dir(mission, ensure=True) / f"{artifact_id}.json"
    record = {
        "artifact_id": artifact_id,
        "artifact_kind": "operator_save",
        "source": "operator",
        "text": text_value,
        "created_at": created_at,
        "mission_id": mission,
        "derived_only": False,
    }
    _write_json(artifact_path, record)
    return {
        **record,
        "path": artifact_path.relative_to(ROOT).as_posix(),
    }


def write_operator_save_artifact(mission_id: str, text: str) -> str:
    artifact = _write_operator_save_artifact(mission_id, text)
    return str(artifact.get("path") or "").strip()


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
