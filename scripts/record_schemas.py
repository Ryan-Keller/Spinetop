from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DISPATCH_STATUSES = {"pending", "approved", "deferred", "rejected"}
PETITION_KINDS = {
    "memory_admission",
    "anomaly_review",
    "repair_request",
    "operator_review",
    "self_heal_request",
}
REQUESTED_ACTIONS = {"admit_to_collective", "operator_review", "repair", "defer", "reject"}
RISK_LEVELS = {"low", "medium", "high"}
ENTRY_CLASSES = {"normal", "repair", "self_heal", "anomaly_review"}
DECISION_OUTCOMES = {"approve_collective", "defer", "reject", "operator_review"}
REVIEW_STATES = {"pending", "final", "amended", "superseded"}


class SchemaError(ValueError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _path_hint(path: Path | None) -> str:
    return f" ({path})" if path else ""


def _obj(data: Any, path: Path | None = None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SchemaError(f"JSON root must be an object{_path_hint(path)}")
    return dict(data)


def _s(data: dict[str, Any], field: str, *, path: Path | None = None, default: str = "", allow_empty: bool = True) -> str:
    value = data.get(field)
    if value is None:
        return default
    if not isinstance(value, str):
        raise SchemaError(f"Field '{field}' must be a string{_path_hint(path)}")
    text = value.strip()
    if not text and not allow_empty:
        raise SchemaError(f"Field '{field}' must not be empty{_path_hint(path)}")
    return text or default


def _b(data: dict[str, Any], field: str, *, path: Path | None = None, default: bool = False) -> bool:
    value = data.get(field)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise SchemaError(f"Field '{field}' must be a boolean{_path_hint(path)}")
    return value


def _n(data: dict[str, Any], field: str, *, path: Path | None = None, default: float = 0.0) -> float:
    value = data.get(field)
    if value is None:
        return default
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise SchemaError(f"Field '{field}' must be numeric{_path_hint(path)}")
    return float(value)


def _li(data: dict[str, Any], field: str, *, path: Path | None = None, allow_empty: bool = True) -> list[str]:
    value = data.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        raise SchemaError(f"Field '{field}' must be a list{_path_hint(path)}")
    out: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            raise SchemaError(f"Field '{field}' item {idx} must be a string{_path_hint(path)}")
        text = item.strip()
        if not text:
            raise SchemaError(f"Field '{field}' item {idx} must not be empty{_path_hint(path)}")
        out.append(text)
    if not out and not allow_empty:
        raise SchemaError(f"Field '{field}' must not be empty{_path_hint(path)}")
    return out


def _ts(
    value: Any,
    field: str,
    *,
    path: Path | None = None,
    default: str = "",
    allow_naive: bool = False,
) -> str:
    if value is None:
        if default:
            return default
        raise SchemaError(f"Field '{field}' is required{_path_hint(path)}")
    if not isinstance(value, str):
        raise SchemaError(f"Field '{field}' must be a string{_path_hint(path)}")
    text = value.strip()
    if not text:
        if default:
            return default
        raise SchemaError(f"Field '{field}' must not be empty{_path_hint(path)}")
    raw = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise SchemaError(f"Field '{field}' must be ISO-8601{_path_hint(path)}: {exc}") from exc
    if parsed.tzinfo is None:
        if not allow_naive:
            raise SchemaError(f"Field '{field}' must include a timezone{_path_hint(path)}")
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _build_id(prefix: str, seed_parts: list[str]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha1("|".join(seed_parts).encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{stamp}_{digest}"


def _legacy_id(path: Path | None, prefix: str) -> str:
    return f"legacy:{path.name}" if path else _build_id(prefix, [utc_now_iso()])


def _pick(data: dict[str, Any], *fields: str, default: str = "") -> str:
    for field in fields:
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _pick_list(data: dict[str, Any], *fields: str) -> list[str]:
    for field in fields:
        value = data.get(field)
        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def validate_governance_decision_record(data: Any, *, path: Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else None
    record = _obj(data, path)
    if record.get("record_type") != "governance_decision":
        raise SchemaError(f"record_type must be governance_decision{_path_hint(path)}")
    _s(record, "decision_id", path=path, allow_empty=False)
    _ts(record.get("created_at"), "created_at", path=path)
    _s(record, "created_by", path=path, allow_empty=False)
    _s(record, "petition_id", path=path, allow_empty=False)
    if record.get("petition_kind") not in PETITION_KINDS:
        raise SchemaError(f"Field 'petition_kind' must be one of {sorted(PETITION_KINDS)}{_path_hint(path)}")
    if record.get("decision_outcome") not in DECISION_OUTCOMES:
        raise SchemaError(f"Field 'decision_outcome' must be one of {sorted(DECISION_OUTCOMES)}{_path_hint(path)}")
    _s(record, "summary", path=path, allow_empty=False)
    _s(record, "reason", path=path, allow_empty=False)
    _li(record, "evidence_refs", path=path, allow_empty=True)
    if record.get("review_state") not in REVIEW_STATES:
        raise SchemaError(f"Field 'review_state' must be one of {sorted(REVIEW_STATES)}{_path_hint(path)}")
    if record.get("risk_level") not in RISK_LEVELS:
        raise SchemaError(f"Field 'risk_level' must be one of {sorted(RISK_LEVELS)}{_path_hint(path)}")
    if "requires_operator_review" not in record:
        raise SchemaError(f"Field 'requires_operator_review' is required{_path_hint(path)}")
    _b(record, "requires_operator_review", path=path)
    return record


def normalize_governance_decision_record(data: Any, *, path: Path | None = None, legacy_ok: bool = True) -> dict[str, Any]:
    path = Path(path) if path else None
    record = _obj(data, path)
    if record.get("record_type") not in {None, "", "governance_decision"} and not legacy_ok:
        raise SchemaError(f"record_type must be governance_decision{_path_hint(path)}")

    record["record_type"] = "governance_decision"
    decision_id = _pick(record, "decision_id", default="")
    if not decision_id and legacy_ok:
        decision_id = _legacy_id(path, "dec")
    record["decision_id"] = decision_id
    created_at_value = record.get("created_at") or record.get("decision_at") or record.get("approved_at") or record.get("approval_timestamp")
    if not created_at_value and legacy_ok:
        created_at_value = utc_now_iso()
    record["created_at"] = _ts(
        created_at_value,
        "created_at",
        path=path,
        default="",
        allow_naive=legacy_ok,
    )
    created_by = _pick(record, "created_by", "approved_by", "operator_id", "agent_id", "expert_name", default="")
    if not created_by and legacy_ok:
        created_by = "unknown"
    record["created_by"] = created_by
    petition_id = _pick(record, "petition_id", "related_petition_id", "linked_petition_id", default="")
    record["petition_id"] = petition_id
    petition_kind = _pick(record, "petition_kind", "entry_class", default="")
    if not petition_kind and legacy_ok:
        petition_kind = "memory_admission"
    record["petition_kind"] = petition_kind
    decision_outcome = _pick(record, "decision_outcome", default="")
    if not decision_outcome and legacy_ok:
        legacy_status = _pick(record, "status", "review_state", default="")
        if legacy_status == "approved" or _pick(record, "approved_at", default=""):
            decision_outcome = "approve_collective"
        elif legacy_status == "deferred" or _pick(record, "deferred_at", default=""):
            decision_outcome = "defer"
        elif legacy_status == "rejected" or _pick(record, "rejected_at", default=""):
            decision_outcome = "reject"
        elif legacy_status == "pending":
            decision_outcome = "operator_review"
    record["decision_outcome"] = decision_outcome
    summary = _pick(record, "summary", "task", "title", default="")
    if not summary and legacy_ok:
        summary = "governance decision"
    record["summary"] = summary
    reason = _pick(record, "reason", "approval_reason", "governance_notes", default="")
    if not reason and legacy_ok:
        reason = summary or "governance decision"
    record["reason"] = reason
    record["evidence_refs"] = _li({"evidence_refs": record.get("evidence_refs") or []}, "evidence_refs", path=path, allow_empty=True)
    review_state = _pick(record, "review_state", default="")
    if not review_state and legacy_ok:
        review_state = "final" if record["decision_outcome"] in {"approve_collective", "defer", "reject"} else "pending"
    record["review_state"] = review_state
    risk_level = _pick(record, "risk_level", default="")
    if not risk_level and legacy_ok:
        risk_level = "medium"
    record["risk_level"] = risk_level
    if "requires_operator_review" in record:
        record["requires_operator_review"] = _b(record, "requires_operator_review", path=path)
    elif legacy_ok:
        record["requires_operator_review"] = record["decision_outcome"] in {"defer", "operator_review"}
    record["governance_decision_ref"] = _pick(record, "governance_decision_ref", default="")
    record["related_collective_id"] = _pick(record, "related_collective_id", default="")
    record["decision_notes"] = _pick(record, "decision_notes", default="")
    record["governance_notes"] = _pick(record, "governance_notes", default="")
    record["operator_id"] = _pick(record, "operator_id", default="")
    record["source_host"] = _pick(record, "source_host", default="unknown")
    record["legacy_compatibility"] = _b(record, "legacy_compatibility", path=path, default=False)
    return validate_governance_decision_record(record, path=path)


def validate_candidate_memory_record(data: Any, *, path: Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else None
    record = _obj(data, path)
    if record.get("record_type") != "candidate_memory":
        raise SchemaError(f"record_type must be candidate_memory{_path_hint(path)}")
    _s(record, "record_id", path=path, allow_empty=False)
    _ts(record.get("created_at"), "created_at", path=path)
    _s(record, "source_workspace", path=path, allow_empty=False)
    _s(record, "submitted_by", path=path, allow_empty=False)
    _s(record, "summary", path=path, allow_empty=False)
    _li(record, "key_findings", path=path, allow_empty=True)
    _s(record, "recommended_action", path=path, allow_empty=False)
    _n(record, "confidence", path=path)
    if record.get("promotion_candidate") is not True:
        raise SchemaError(f"promotion_candidate must be true{_path_hint(path)}")
    return record


def normalize_candidate_memory_record(data: Any, *, path: Path | None = None, legacy_ok: bool = True) -> dict[str, Any]:
    path = Path(path) if path else None
    record = _obj(data, path)
    if record.get("record_type") not in {None, "", "candidate_memory"} and not legacy_ok:
        raise SchemaError(f"record_type must be candidate_memory{_path_hint(path)}")
    record["record_type"] = "candidate_memory"
    record["created_at"] = _ts(
        record.get("created_at") or record.get("timestamp_created") or record.get("promotion_timestamp"),
        "created_at",
        path=path,
        default=utc_now_iso(),
        allow_naive=legacy_ok,
    )
    record["source_workspace"] = _pick(record, "source_workspace", "workspace", default="spinetop")
    record["submitted_by"] = _pick(record, "submitted_by", "agent_id", "expert_name", default="unknown")
    record["summary"] = _pick(record, "summary", "task", default="candidate memory")
    record["key_findings"] = _li({"key_findings": record.get("key_findings") or []}, "key_findings", path=path, allow_empty=True)
    record["recommended_action"] = _pick(record, "recommended_action", default="pending_review")
    record["confidence"] = _n(record, "confidence", path=path, default=0.0)
    record["promotion_candidate"] = _b(record, "promotion_candidate", path=path, default=True)
    record["source_record_ref"] = _pick(record, "source_record_ref", "record_name", default=(path.name if path else ""))
    record["related_petition_id"] = _pick(record, "related_petition_id", default="")
    record["archival_status"] = _pick(record, "archival_status", default="active")
    record["legacy_compatibility"] = _b(record, "legacy_compatibility", path=path, default=False)
    record["tags"] = _pick_list(record, "tags")
    if not record.get("record_id"):
        record["record_id"] = _build_id(
            "mem",
            [
                record["created_at"],
                record["source_workspace"],
                record["submitted_by"],
                record["summary"],
                record["source_record_ref"],
            ],
        )
    return validate_candidate_memory_record(record, path=path)


def build_candidate_memory_record(
    *,
    source_record: dict[str, Any],
    source_record_ref: str,
    submitted_by: str,
    source_workspace: str,
    summary: str,
    key_findings: list[str],
    recommended_action: str,
    confidence: float,
    record_id: str | None = None,
    created_at: str | None = None,
    related_petition_id: str = "",
    tags: list[str] | None = None,
    archival_status: str = "active",
    legacy_compatibility: bool = False,
) -> dict[str, Any]:
    record = dict(source_record)
    record.update(
        {
            "record_type": "candidate_memory",
            "created_at": created_at or utc_now_iso(),
            "source_workspace": source_workspace.strip() or "spinetop",
            "submitted_by": submitted_by.strip() or "unknown",
            "summary": summary.strip(),
            "key_findings": [item.strip() for item in key_findings if isinstance(item, str) and item.strip()],
            "recommended_action": recommended_action.strip() or "pending_review",
            "confidence": float(confidence),
            "promotion_candidate": True,
            "source_record_ref": source_record_ref.strip(),
            "related_petition_id": related_petition_id.strip(),
            "archival_status": archival_status.strip() or "active",
            "legacy_compatibility": bool(legacy_compatibility),
        }
    )
    if tags is not None:
        record["tags"] = [item.strip() for item in tags if isinstance(item, str) and item.strip()]
    if record_id:
        record["record_id"] = record_id.strip()
    return validate_candidate_memory_record(record)


def _dispatch_defaults(record: dict[str, Any]) -> tuple[str, str, str, str]:
    entry_class = _pick(record, "entry_class", default="normal")
    if entry_class == "artifact_return":
        entry_class = "normal"
    petition_kind = _pick(record, "petition_kind", default="")
    requested_action = _pick(record, "requested_action", default="")
    risk_level = _pick(record, "risk_level", default="")
    if not petition_kind:
        petition_kind = {
            "repair": "repair_request",
            "self_heal": "self_heal_request",
            "anomaly_review": "anomaly_review",
        }.get(entry_class, "memory_admission")
    if not requested_action:
        requested_action = {
            "repair_request": "repair",
            "self_heal_request": "repair",
            "anomaly_review": "operator_review",
        }.get(petition_kind, "admit_to_collective")
    if not risk_level:
        risk_level = "high" if petition_kind in {"anomaly_review", "repair_request"} else "medium"
    if entry_class not in ENTRY_CLASSES:
        entry_class = {
            "repair_request": "repair",
            "self_heal_request": "self_heal",
            "anomaly_review": "anomaly_review",
        }.get(petition_kind, "normal")
    return petition_kind, requested_action, risk_level, entry_class


def validate_dispatch_petition_record(data: Any, *, path: Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else None
    record = _obj(data, path)
    if record.get("record_type") != "dispatch_petition":
        raise SchemaError(f"record_type must be dispatch_petition{_path_hint(path)}")
    _s(record, "petition_id", path=path, allow_empty=False)
    _ts(record.get("created_at"), "created_at", path=path)
    _s(record, "created_by", path=path, allow_empty=False)
    _s(record, "workspace", path=path, allow_empty=False)
    if record.get("status") not in DISPATCH_STATUSES:
        raise SchemaError(f"Field 'status' must be one of {sorted(DISPATCH_STATUSES)}{_path_hint(path)}")
    if record.get("petition_kind") not in PETITION_KINDS:
        raise SchemaError(f"Field 'petition_kind' must be one of {sorted(PETITION_KINDS)}{_path_hint(path)}")
    _s(record, "summary", path=path, allow_empty=False)
    _s(record, "reason", path=path, allow_empty=False)
    _li(record, "evidence_refs", path=path, allow_empty=True)
    if record.get("requested_action") not in REQUESTED_ACTIONS:
        raise SchemaError(f"Field 'requested_action' must be one of {sorted(REQUESTED_ACTIONS)}{_path_hint(path)}")
    if record.get("risk_level") not in RISK_LEVELS:
        raise SchemaError(f"Field 'risk_level' must be one of {sorted(RISK_LEVELS)}{_path_hint(path)}")
    _b(record, "requires_operator_approval", path=path)
    if record.get("entry_class") not in ENTRY_CLASSES:
        raise SchemaError(f"Field 'entry_class' must be one of {sorted(ENTRY_CLASSES)}{_path_hint(path)}")
    return record


def normalize_dispatch_petition_record(data: Any, *, path: Path | None = None, legacy_ok: bool = True) -> dict[str, Any]:
    path = Path(path) if path else None
    record = _obj(data, path)
    if record.get("record_type") not in {None, "", "dispatch_petition"} and not legacy_ok:
        raise SchemaError(f"record_type must be dispatch_petition{_path_hint(path)}")

    record["record_type"] = "dispatch_petition"
    record["petition_id"] = _pick(record, "petition_id", default=_legacy_id(path, "dispatch"))
    record["created_at"] = _ts(
        record.get("created_at") or record.get("timestamp_created"),
        "created_at",
        path=path,
        default=utc_now_iso(),
        allow_naive=legacy_ok,
    )
    record["created_by"] = _pick(record, "created_by", "agent_id", default="unknown")
    record["workspace"] = _pick(record, "workspace", default="spinetop")
    record["status"] = _pick(record, "status", "petition_status", default=(path.parent.name if path and path.parent.name in DISPATCH_STATUSES else "pending"))
    record["petition_kind"], record["requested_action"], record["risk_level"], record["entry_class"] = _dispatch_defaults(record)
    record["summary"] = _pick(record, "summary", "task", default="")
    record["reason"] = _pick(record, "reason", default=record["summary"] or record["petition_kind"])
    record["evidence_refs"] = _li({"evidence_refs": record.get("evidence_refs") or []}, "evidence_refs", path=path, allow_empty=True)
    record["requires_operator_approval"] = _b(record, "requires_operator_approval", path=path, default=record["requested_action"] != "admit_to_collective")
    record["related_record_id"] = _pick(record, "related_record_id", default="")
    record["related_petition_id"] = _pick(record, "related_petition_id", default="")
    cooldown = record.get("cooldown_observed")
    if cooldown is not None and (not isinstance(cooldown, (int, float)) or isinstance(cooldown, bool)):
        raise SchemaError(f"Field 'cooldown_observed' must be numeric{_path_hint(path)}")
    if cooldown is not None:
        record["cooldown_observed"] = int(cooldown)
    record["governance_notes"] = _pick(record, "governance_notes", default="")
    record["operator_id"] = _pick(record, "operator_id", default="")
    record["source_host"] = _pick(record, "source_host", default="unknown")
    record["status_updated_at"] = _ts(
        record.get("status_updated_at") or record["created_at"],
        "status_updated_at",
        path=path,
        default=record["created_at"],
        allow_naive=legacy_ok,
    )
    record["ask_count"] = int(record.get("ask_count") or 1)
    record["spawn_authority"] = _pick(record, "spawn_authority", default="emissary")
    record["dispatch_mode"] = _pick(record, "dispatch_mode", default="normal")
    record["confidence"] = _n(record, "confidence", path=path, default=0.0)
    record["promotion_candidate"] = _b(record, "promotion_candidate", path=path, default=False)
    record["payload_type"] = _pick(record, "payload_type", default="pattern")
    record["urgency"] = _pick(record, "urgency", default="normal")
    record["requires_emissary"] = _b(record, "requires_emissary", path=path, default=True)
    record["nanny_temperature"] = _pick(record, "nanny_temperature", default="cool")
    record["nanny_cooldown_seconds"] = int(record.get("nanny_cooldown_seconds") or 0)
    record["record_name"] = _pick(record, "record_name", default=f"dispatch_{record['petition_id']}_{record['status']}.json")
    record["petition_status"] = record["status"]
    return validate_dispatch_petition_record(record, path=path)


def build_dispatch_petition_record(
    *,
    petition_id: str,
    created_by: str,
    workspace: str,
    status: str,
    petition_kind: str,
    summary: str,
    reason: str,
    evidence_refs: list[str] | None,
    requested_action: str,
    risk_level: str,
    requires_operator_approval: bool,
    entry_class: str,
    related_record_id: str = "",
    related_petition_id: str = "",
    cooldown_observed: int | None = None,
    governance_notes: str = "",
    operator_id: str = "",
    source_host: str = "unknown",
    base_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = dict(base_record or {})
    record.update(
        {
            "petition_id": petition_id.strip(),
            "record_type": "dispatch_petition",
            "created_at": utc_now_iso(),
            "created_by": created_by.strip() or "unknown",
            "workspace": workspace.strip() or "spinetop",
            "status": status.strip(),
            "petition_kind": petition_kind.strip(),
            "summary": summary.strip(),
            "reason": reason.strip(),
            "evidence_refs": [item.strip() for item in (evidence_refs or []) if isinstance(item, str) and item.strip()],
            "requested_action": requested_action.strip(),
            "risk_level": risk_level.strip(),
            "requires_operator_approval": bool(requires_operator_approval),
            "entry_class": entry_class.strip(),
            "status_updated_at": utc_now_iso(),
            "confidence": float(record.get("confidence") or 0.0),
            "promotion_candidate": bool(record.get("promotion_candidate", False)),
            "payload_type": _pick(record, "payload_type", default="pattern"),
            "urgency": _pick(record, "urgency", default="normal"),
            "requires_emissary": _b(record, "requires_emissary", default=True),
            "ask_count": int(record.get("ask_count") or 1),
            "spawn_authority": _pick(record, "spawn_authority", default="emissary"),
            "dispatch_mode": _pick(record, "dispatch_mode", default="normal"),
            "operator_id": operator_id.strip(),
            "source_host": source_host.strip() or "unknown",
            "related_record_id": related_record_id.strip(),
            "related_petition_id": related_petition_id.strip(),
            "governance_notes": governance_notes.strip(),
            "nanny_temperature": _pick(record, "nanny_temperature", default="cool"),
            "nanny_cooldown_seconds": int(record.get("nanny_cooldown_seconds") or 0),
            "record_name": record.get("record_name") or f"dispatch_{petition_id.strip()}_{status.strip()}.json",
        }
    )
    if cooldown_observed is not None:
        record["cooldown_observed"] = int(cooldown_observed)
    return validate_dispatch_petition_record(record)


def validate_collective_memory_record(data: Any, *, path: Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else None
    record = _obj(data, path)
    if record.get("record_type") != "collective_memory":
        raise SchemaError(f"record_type must be collective_memory{_path_hint(path)}")
    _s(record, "record_id", path=path, allow_empty=False)
    _ts(record.get("created_at"), "created_at", path=path)
    _ts(record.get("admitted_at"), "admitted_at", path=path)
    _s(record, "source_workspace", path=path, allow_empty=False)
    _s(record, "submitted_by", path=path, allow_empty=False)
    _s(record, "candidate_id", path=path, allow_empty=False)
    _s(record, "governance_approval_ref", path=path, allow_empty=False)
    _s(record, "related_petition_id", path=path, allow_empty=False)
    _s(record, "governance_decision_id", path=path, allow_empty=False)
    _s(record, "summary", path=path, allow_empty=False)
    _li(record, "key_findings", path=path, allow_empty=False)
    _s(record, "recommended_action", path=path, allow_empty=False)
    _n(record, "confidence", path=path)
    if record.get("durability_class") not in {"working_truth", "stable_truth", "temporary_truth"}:
        raise SchemaError(f"Field 'durability_class' must be one of ['stable_truth', 'temporary_truth', 'working_truth']{_path_hint(path)}")
    return record


def normalize_collective_memory_record(data: Any, *, path: Path | None = None, legacy_ok: bool = True) -> dict[str, Any]:
    path = Path(path) if path else None
    record = _obj(data, path)
    if record.get("record_type") not in {None, "", "collective_memory"} and not legacy_ok:
        raise SchemaError(f"record_type must be collective_memory{_path_hint(path)}")
    record["record_type"] = "collective_memory"
    record["created_at"] = _ts(
        record.get("created_at") or record.get("timestamp_created") or record.get("promotion_timestamp"),
        "created_at",
        path=path,
        default=utc_now_iso(),
        allow_naive=legacy_ok,
    )
    record["admitted_at"] = _ts(
        record.get("admitted_at") or record.get("approval_timestamp"),
        "admitted_at",
        path=path,
        default=utc_now_iso(),
        allow_naive=legacy_ok,
    )
    record["source_workspace"] = _pick(record, "source_workspace", "workspace", default="spinetop")
    record["submitted_by"] = _pick(record, "submitted_by", "agent_id", "expert_name", default="unknown")
    record["candidate_id"] = _pick(record, "candidate_id", default="")
    record["summary"] = _pick(record, "summary", "task", default="")
    record["key_findings"] = _li({"key_findings": record.get("key_findings") or []}, "key_findings", path=path, allow_empty=False)
    record["recommended_action"] = _pick(record, "recommended_action", default="review")
    record["confidence"] = _n(record, "confidence", path=path, default=0.0)
    record["durability_class"] = _pick(record, "durability_class", default="")
    if not record["durability_class"] and legacy_ok:
        record["durability_class"] = "stable_truth" if record["confidence"] >= 0.9 else "working_truth" if record["confidence"] >= 0.7 else "temporary_truth"
    record["governance_approval_ref"] = _pick(record, "governance_approval_ref", default="")
    if not record["governance_approval_ref"] and legacy_ok:
        related = _pick(record, "related_petition_id", default="")
        if related:
            record["governance_approval_ref"] = f"dispatch:{related}"
        elif _pick(record, "approval_timestamp", default=""):
            record["governance_approval_ref"] = f"legacy:{record.get('record_id') or (path.name if path else 'collective')}"
    record["related_petition_id"] = _pick(record, "related_petition_id", default="")
    record["governance_decision_id"] = _pick(record, "governance_decision_id", default="")
    record["source_record_ref"] = _pick(record, "source_record_ref", default=(path.name if path else ""))
    record["tags"] = _pick_list(record, "tags")
    record["archival_status"] = _pick(record, "archival_status", default="active")
    record["legacy_compatibility"] = _b(record, "legacy_compatibility", path=path, default=False)
    record["compaction_parent_ref"] = _pick(record, "compaction_parent_ref", default="")
    if not record.get("record_id"):
        record["record_id"] = _build_id(
            "mem",
            [record["created_at"], record["source_workspace"], record["submitted_by"], record["summary"], record["source_record_ref"]],
        )
    return validate_collective_memory_record(record, path=path)


def build_governance_decision_record(
    *,
    petition_id: str,
    petition_kind: str,
    decision_outcome: str,
    created_by: str,
    summary: str,
    reason: str,
    evidence_refs: list[str] | None,
    risk_level: str,
    requires_operator_review: bool,
    decision_id: str | None = None,
    created_at: str | None = None,
    review_state: str = "final",
    related_collective_id: str = "",
    decision_notes: str = "",
    governance_notes: str = "",
    operator_id: str = "",
    source_host: str = "unknown",
    legacy_compatibility: bool = False,
) -> dict[str, Any]:
    record = {
        "record_type": "governance_decision",
        "decision_id": decision_id.strip() if decision_id else "",
        "created_at": created_at or utc_now_iso(),
        "created_by": created_by.strip() or "unknown",
        "petition_id": petition_id.strip(),
        "petition_kind": petition_kind.strip(),
        "decision_outcome": decision_outcome.strip(),
        "summary": summary.strip(),
        "reason": reason.strip(),
        "evidence_refs": [item.strip() for item in (evidence_refs or []) if isinstance(item, str) and item.strip()],
        "review_state": review_state.strip(),
        "risk_level": risk_level.strip(),
        "requires_operator_review": bool(requires_operator_review),
        "related_collective_id": related_collective_id.strip(),
        "decision_notes": decision_notes.strip(),
        "governance_notes": governance_notes.strip(),
        "operator_id": operator_id.strip(),
        "source_host": source_host.strip() or "unknown",
        "legacy_compatibility": bool(legacy_compatibility),
    }
    if not record["decision_id"]:
        record["decision_id"] = _build_id("dec", [record["petition_id"], record["decision_outcome"], record["created_by"], record["summary"], record["created_at"]])
    return validate_governance_decision_record(record)


def build_collective_record_from_candidate(
    candidate_record: dict[str, Any],
    *,
    governance_decision_id: str,
    related_petition_id: str = "",
    admitted_at: str | None = None,
    durability_class: str | None = None,
    compaction_parent_ref: str = "",
) -> dict[str, Any]:
    candidate = normalize_candidate_memory_record(candidate_record, legacy_ok=True)
    related_petition_id = related_petition_id.strip() or candidate.get("related_petition_id", "")
    governance_decision_id = governance_decision_id.strip()
    candidate_id = str(candidate.get("record_id") or "").strip()
    record = dict(candidate)
    record.update(
        {
            "record_type": "collective_memory",
            "created_at": candidate["created_at"],
            "admitted_at": admitted_at or utc_now_iso(),
            "source_workspace": candidate["source_workspace"],
            "submitted_by": candidate["submitted_by"],
            "candidate_id": candidate_id,
            "governance_approval_ref": f"decision:{governance_decision_id}",
            "related_petition_id": related_petition_id,
            "governance_decision_id": governance_decision_id,
            "summary": candidate["summary"],
            "key_findings": list(candidate["key_findings"]),
            "recommended_action": candidate["recommended_action"],
            "confidence": float(candidate["confidence"]),
            "source_record_ref": candidate.get("source_record_ref", ""),
            "archival_status": candidate.get("archival_status", "active"),
            "legacy_compatibility": bool(candidate.get("legacy_compatibility", False)),
            "compaction_parent_ref": compaction_parent_ref.strip() or candidate.get("compaction_parent_ref", ""),
        }
    )
    if durability_class:
        record["durability_class"] = durability_class.strip()
    else:
        record["durability_class"] = "stable_truth" if record["confidence"] >= 0.9 else "working_truth" if record["confidence"] >= 0.7 else "temporary_truth"
    return validate_collective_memory_record(record)


def validate_operational_classification_record(data: Any, *, path: Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else None
    record = _obj(data, path)
    if record.get("record_type") != "operational_classification":
        raise SchemaError(f"record_type must be operational_classification{_path_hint(path)}")
    _s(record, "classification_id", path=path, allow_empty=False)
    _ts(record.get("created_at"), "created_at", path=path)
    _s(record, "classified_by", path=path, allow_empty=False)
    if record.get("classification_kind") not in CLASSIFICATION_KINDS:
        raise SchemaError(f"Field 'classification_kind' must be one of {sorted(CLASSIFICATION_KINDS)}{_path_hint(path)}")
    _s(record, "title", path=path, allow_empty=False)
    if record.get("affected_system") not in AFFECTED_SYSTEMS:
        raise SchemaError(f"Field 'affected_system' must be one of {sorted(AFFECTED_SYSTEMS)}{_path_hint(path)}")
    if record.get("severity") not in SEVERITIES:
        raise SchemaError(f"Field 'severity' must be one of {sorted(SEVERITIES)}{_path_hint(path)}")
    if record.get("boundedness") not in BOUNDEDNESS:
        raise SchemaError(f"Field 'boundedness' must be one of {sorted(BOUNDEDNESS)}{_path_hint(path)}")
    _s(record, "evidence_summary", path=path, allow_empty=False)
    if record.get("recommended_next_step") not in NEXT_STEPS:
        raise SchemaError(f"Field 'recommended_next_step' must be one of {sorted(NEXT_STEPS)}{_path_hint(path)}")
    if record.get("repairability") not in REPAIRABILITY:
        raise SchemaError(f"Field 'repairability' must be one of {sorted(REPAIRABILITY)}{_path_hint(path)}")
    _b(record, "return_all_active", path=path)
    return record


def normalize_operational_classification_record(data: Any, *, path: Path | None = None, legacy_ok: bool = True) -> dict[str, Any]:
    path = Path(path) if path else None
    record = _obj(data, path)
    if record.get("record_type") not in {None, "", "operational_classification"} and not legacy_ok:
        raise SchemaError(f"record_type must be operational_classification{_path_hint(path)}")
    record["record_type"] = "operational_classification"
    record["classification_id"] = _pick(record, "classification_id", default=_legacy_id(path, "cls"))
    record["created_at"] = _ts(record.get("created_at"), "created_at", path=path, default=utc_now_iso(), allow_naive=legacy_ok)
    record["classified_by"] = _pick(record, "classified_by", default="unknown")
    record["classification_kind"] = _pick(record, "classification_kind", default="anomaly")
    record["title"] = _pick(record, "title", default="")
    record["affected_system"] = _pick(record, "affected_system", default="unknown")
    record["severity"] = _pick(record, "severity", default="medium")
    record["boundedness"] = _pick(record, "boundedness", default="ambiguous")
    record["evidence_summary"] = _pick(record, "evidence_summary", default="")
    record["recommended_next_step"] = _pick(record, "recommended_next_step", default="operator_review")
    record["repairability"] = _pick(record, "repairability", default="unclear")
    record["linked_petition_id"] = _pick(record, "linked_petition_id", default="")
    record["linked_record_id"] = _pick(record, "linked_record_id", default="")
    record["cooldown_context"] = _pick(record, "cooldown_context", default="")
    record["return_all_active"] = _b(record, "return_all_active", path=path, default=False)
    record["notes"] = _pick(record, "notes", default="")
    record["source_host"] = _pick(record, "source_host", default="")
    record["workspace"] = _pick(record, "workspace", default="")
    return validate_operational_classification_record(record, path=path)


def build_operational_classification_record(
    *,
    classification_id: str,
    classified_by: str,
    classification_kind: str,
    title: str,
    affected_system: str,
    severity: str,
    boundedness: str,
    evidence_summary: str,
    recommended_next_step: str,
    repairability: str,
    linked_petition_id: str = "",
    linked_record_id: str = "",
    cooldown_context: str = "",
    return_all_active: bool = False,
    notes: str = "",
    source_host: str = "",
    workspace: str = "",
) -> dict[str, Any]:
    record = {
        "classification_id": classification_id.strip(),
        "record_type": "operational_classification",
        "created_at": utc_now_iso(),
        "classified_by": classified_by.strip() or "unknown",
        "classification_kind": classification_kind.strip(),
        "title": title.strip(),
        "affected_system": affected_system.strip(),
        "severity": severity.strip(),
        "boundedness": boundedness.strip(),
        "evidence_summary": evidence_summary.strip(),
        "recommended_next_step": recommended_next_step.strip(),
        "repairability": repairability.strip(),
        "linked_petition_id": linked_petition_id.strip(),
        "linked_record_id": linked_record_id.strip(),
        "cooldown_context": cooldown_context.strip(),
        "return_all_active": bool(return_all_active),
        "notes": notes.strip(),
        "source_host": source_host.strip(),
        "workspace": workspace.strip(),
    }
    if not record["linked_petition_id"]:
        record.pop("linked_petition_id")
    if not record["linked_record_id"]:
        record.pop("linked_record_id")
    if not record["cooldown_context"]:
        record.pop("cooldown_context")
    if not record["notes"]:
        record.pop("notes")
    if not record["source_host"]:
        record.pop("source_host")
    if not record["workspace"]:
        record.pop("workspace")
    return validate_operational_classification_record(record)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _check(kind: str, path: Path, legacy_ok: bool) -> int:
    payload = load_json(path)
    if kind == "dispatch":
        record = normalize_dispatch_petition_record(payload, path=path, legacy_ok=legacy_ok)
        print(f"OK dispatch_petition petition_id={record['petition_id']}")
    elif kind == "decision":
        record = normalize_governance_decision_record(payload, path=path, legacy_ok=legacy_ok)
        print(f"OK governance_decision decision_id={record['decision_id']}")
    elif kind == "collective":
        record = normalize_collective_memory_record(payload, path=path, legacy_ok=legacy_ok)
        print(f"OK collective_memory record_id={record['record_id']}")
    elif kind == "candidate":
        record = normalize_candidate_memory_record(payload, path=path, legacy_ok=legacy_ok)
        print(f"OK candidate_memory record_id={record['record_id']}")
    elif kind == "classification":
        record = normalize_operational_classification_record(payload, path=path, legacy_ok=legacy_ok)
        print(f"OK operational_classification classification_id={record['classification_id']}")
    else:
        raise SchemaError(f"Unsupported kind: {kind}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Spinetop record schemas")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Validate a single JSON record")
    check.add_argument("kind", choices=["dispatch", "decision", "collective", "candidate", "classification"])
    check.add_argument("path", type=Path)
    check.add_argument("--strict", action="store_true", help="Reject legacy fallback")
    args = parser.parse_args()
    try:
        return _check(args.kind, args.path, legacy_ok=not args.strict)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
