from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from state_machine import normalize_mission_id

import mission_storage_core as core
import mission_storage_read as read_ops


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
    existing = read_ops._read_parking_status(mission)
    record = {
        "mission_id": mission,
        "status": normalized_status,
        "reason": str(reason).strip(),
        "parked_at": str(existing.get("parked_at") or "") if normalized_status == "parked" else "",
        "parked_by": str(parked_by).strip() or "operator",
        "resume_hint": str(resume_hint).strip(),
        "updated_at": core.iso_now(),
    }
    if normalized_status == "parked" and not record["parked_at"]:
        record["parked_at"] = record["updated_at"]
    if normalized_status != "parked":
        record["parked_by"] = ""
    core._write_json(core._mission_parking_path(mission, ensure=True), record)
    return record


def _write_retry_ledger(mission_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    record = read_ops._default_retry_ledger(mission)
    record.update(payload)
    record["mission_id"] = mission
    try:
        record["retry_budget_total"] = max(0, int(record.get("retry_budget_total") or core.RETRY_BUDGET_TOTAL))
    except Exception:
        record["retry_budget_total"] = core.RETRY_BUDGET_TOTAL
    try:
        record["retry_budget_used"] = max(0, int(record.get("retry_budget_used") or 0))
    except Exception:
        record["retry_budget_used"] = 0
    record["retry_budget_used"] = min(record["retry_budget_used"], record["retry_budget_total"])
    record["retry_reasons"] = [str(item).strip() for item in record.get("retry_reasons", []) if str(item).strip()][:20]
    record["decision_log"] = read_ops._normalize_retry_log_items(record.get("decision_log"))
    record["updated_at"] = str(record.get("updated_at") or core.iso_now())
    record["derived_only"] = True
    core._write_json(core._retry_ledger_path(mission, ensure=True), record)
    return record


def _write_trigger_handoff(mission_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    record = read_ops._default_trigger_handoff(mission_id)
    record.update(payload)
    record["mission_id"] = normalize_mission_id(mission_id)
    record["updated_at"] = str(record.get("updated_at") or core.iso_now())
    record["derived_only"] = True
    core._write_json(core._trigger_handoff_path(mission_id, ensure=True), record)
    return record


def _write_operator_save_artifact(mission_id: str, text: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    text_value = str(text or "")
    if not text_value.strip():
        raise ValueError("save detected but no content remained after `save:`; nothing was written")
    created_at = core.iso_now()
    artifact_id = (
        f"operator_save_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_"
        f"{core._short_digest(f'{mission}|{text_value}|{created_at}')}"
    )
    artifact_path = core._mirror_dir(mission, ensure=True) / f"{artifact_id}.json"
    record = {
        "artifact_id": artifact_id,
        "artifact_kind": "operator_save",
        "source": "operator",
        "text": text_value,
        "created_at": created_at,
        "mission_id": mission,
        "derived_only": False,
    }
    core._write_json(artifact_path, record)
    return {
        **record,
        "path": artifact_path.relative_to(core.ROOT).as_posix(),
    }


def write_operator_save_artifact(mission_id: str, text: str) -> str:
    artifact = _write_operator_save_artifact(mission_id, text)
    return str(artifact.get("path") or "").strip()


def _write_mission_input(mission: str, content: str) -> dict[str, Any]:
    created_at = core.iso_now()
    input_id = f"input_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{core._short_digest(f'{mission}|{content}|{created_at}')}"
    intake_dir = core._ensure_workbench_structure(mission) / "intake"
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
    core._write_json(input_path, record)
    return {
        **record,
        "path": input_path.relative_to(core.ROOT).as_posix(),
    }
