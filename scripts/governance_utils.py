from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repo_paths import repo_root


ROOT = repo_root()
GOVERNANCE_DIR = ROOT / "logs" / "governance"
NANNY_STATUS_PATH = ROOT / "logs" / "nanny" / "item_world_status.json"
DISPATCH_DIR = ROOT / "memory" / "dispatch"


@dataclass(frozen=True)
class GovernanceGate:
    allowed: bool
    status: str
    reason: str


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def read_return_all_state() -> dict[str, Any]:
    payload = _load_json(GOVERNANCE_DIR / "return_all.json")
    return {
        "ok": True,
        "enabled": bool(payload.get("enabled", False)),
        "issued_by": str(payload.get("issued_by") or ""),
        "issued_at": str(payload.get("issued_at") or ""),
        "reason": str(payload.get("reason") or ""),
        "allow_custodial_bypass": bool(payload.get("allow_custodial_bypass", False)),
    }


def read_nanny_state() -> dict[str, Any]:
    payload = _load_json(NANNY_STATUS_PATH)
    temperature = str(payload.get("temperature") or "cool")
    cooldown = int(payload.get("global_cooldown_seconds") or 0)
    recommended_actions = payload.get("recommended_actions")
    if not isinstance(recommended_actions, list):
        recommended_actions = []
    return {
        "ok": True,
        "temperature": temperature,
        "global_cooldown_seconds": cooldown,
        "cooldown_active": cooldown > 0,
        "recommended_actions": recommended_actions,
    }


def maybe_allow_custodial_bypass(
    spawn_authority: str,
    dispatch_mode: str,
    entry_class: str,
    return_all: dict[str, Any] | None = None,
) -> bool:
    return_all = return_all or read_return_all_state()
    return (
        return_all.get("enabled")
        and return_all.get("allow_custodial_bypass")
        and spawn_authority == "custodial"
        and dispatch_mode == "rapid"
        and entry_class in {"self_heal", "repair"}
    )


def _nanny_is_cooling(nanny: dict[str, Any]) -> bool:
    return str(nanny.get("temperature") or "cool") in {"warm", "hot"} or int(
        nanny.get("global_cooldown_seconds") or 0
    ) > 0


def _has_governance_trail(record: dict[str, Any]) -> bool:
    related_petition_id = str(record.get("related_petition_id") or "").strip()
    governance_ref = str(record.get("governance_approval_ref") or "").strip()
    governance_decision_id = str(record.get("governance_decision_id") or "").strip()
    approval_timestamp = str(record.get("approval_timestamp") or "").strip()
    return bool(related_petition_id or governance_ref or governance_decision_id or approval_timestamp)


def _has_new_governance_markers(record: dict[str, Any]) -> bool:
    return any(
        str(record.get(field) or "").strip()
        for field in (
            "candidate_id",
            "related_petition_id",
            "governance_decision_id",
            "governance_review_state",
            "governance_review_reason",
            "governance_review_timestamp",
            "governance_approval_ref",
        )
    )


def _is_legacy_collective_record(record: dict[str, Any]) -> bool:
    return not _has_new_governance_markers(record)


def _resolve_related_petition_id(record: dict[str, Any]) -> str:
    related_petition_id = str(record.get("related_petition_id") or "").strip()
    if related_petition_id:
        return related_petition_id
    governance_ref = str(record.get("governance_approval_ref") or "").strip()
    if governance_ref.startswith("dispatch:"):
        return governance_ref.removeprefix("dispatch:").strip()
    if governance_ref:
        return governance_ref
    return ""


def _find_petition(petition_id: str) -> tuple[str | None, Path | None, dict[str, Any] | None]:
    if not petition_id:
        return None, None, None
    for status in ("approved", "pending", "deferred", "rejected"):
        folder = DISPATCH_DIR / status
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.json")):
            payload = _load_json(path)
            if str(payload.get("record_type") or "").strip() != "dispatch_petition":
                continue
            if str(payload.get("petition_id") or "").strip() == petition_id:
                return status, path, payload
    return None, None, None


def _find_governance_decision(decision_id: str | None = None, petition_id: str | None = None) -> tuple[Path | None, dict[str, Any] | None]:
    for status in ("approved", "deferred", "rejected"):
        folder = DISPATCH_DIR / status
        if not folder.exists():
            continue
        for path in sorted(folder.glob("decision_*.json")):
            payload = _load_json(path)
            if str(payload.get("record_type") or "").strip() != "governance_decision":
                continue
            if decision_id and str(payload.get("decision_id") or "").strip() == decision_id:
                return path, payload
            if petition_id and str(payload.get("petition_id") or "").strip() == petition_id:
                return path, payload
    return None, None


def find_approved_petition(petition_id: str) -> tuple[Path | None, dict[str, Any] | None]:
    status, path, payload = _find_petition(petition_id)
    if status == "approved":
        return path, payload
    return None, None


def find_governance_decision_for_petition(petition_id: str) -> tuple[Path | None, dict[str, Any] | None]:
    return _find_governance_decision(petition_id=petition_id)


def can_create_dispatch(
    *,
    spawn_authority: str,
    dispatch_mode: str,
    entry_class: str,
    return_all: dict[str, Any] | None = None,
    nanny: dict[str, Any] | None = None,
) -> GovernanceGate:
    return_all = return_all or read_return_all_state()
    nanny = nanny or read_nanny_state()

    if return_all.get("enabled") and not maybe_allow_custodial_bypass(
        spawn_authority, dispatch_mode, entry_class, return_all
    ):
        return GovernanceGate(False, "deferred", "return_all active")

    if _nanny_is_cooling(nanny):
        temperature = str(nanny.get("temperature") or "cool")
        cooldown = int(nanny.get("global_cooldown_seconds") or 0)
        return GovernanceGate(False, "deferred", f"nanny {temperature} or cooldown {cooldown}s active")

    return GovernanceGate(True, "allowed", "dispatch permitted")


def can_promote_to_collective(
    record: dict[str, Any],
    *,
    return_all: dict[str, Any] | None = None,
    nanny: dict[str, Any] | None = None,
) -> GovernanceGate:
    return_all = return_all or read_return_all_state()
    nanny = nanny or read_nanny_state()

    if record.get("promotion_candidate") is not True:
        return GovernanceGate(False, "blocked", "promotion_candidate is not true")

    if return_all.get("enabled"):
        return GovernanceGate(False, "deferred", "return_all active")

    if _nanny_is_cooling(nanny):
        temperature = str(nanny.get("temperature") or "cool")
        cooldown = int(nanny.get("global_cooldown_seconds") or 0)
        return GovernanceGate(False, "deferred", f"nanny {temperature} or cooldown {cooldown}s active")

    related_petition_id = _resolve_related_petition_id(record)
    if not related_petition_id:
        return GovernanceGate(False, "deferred", "missing related_petition_id governance trail")

    status, _, petition = _find_petition(related_petition_id)
    if not petition:
        return GovernanceGate(False, "deferred", f"missing dispatch petition {related_petition_id}")
    if status != "approved":
        return GovernanceGate(False, "deferred", f"dispatch petition {related_petition_id} not approved")

    return GovernanceGate(True, "allowed", f"dispatch petition {related_petition_id} approved")


def can_admit_to_collective(
    candidate: dict[str, Any],
    petition: dict[str, Any],
    decision: dict[str, Any],
    *,
    return_all: dict[str, Any] | None = None,
    nanny: dict[str, Any] | None = None,
) -> GovernanceGate:
    return_all = return_all or read_return_all_state()
    nanny = nanny or read_nanny_state()

    if candidate.get("promotion_candidate") is not True:
        return GovernanceGate(False, "blocked", "promotion_candidate is not true")

    if return_all.get("enabled"):
        return GovernanceGate(False, "deferred", "return_all active")

    if _nanny_is_cooling(nanny):
        temperature = str(nanny.get("temperature") or "cool")
        cooldown = int(nanny.get("global_cooldown_seconds") or 0)
        return GovernanceGate(False, "deferred", f"nanny {temperature} or cooldown {cooldown}s active")

    candidate_petition_id = str(candidate.get("related_petition_id") or "").strip()
    petition_id = str(petition.get("petition_id") or "").strip()
    if not candidate_petition_id:
        return GovernanceGate(False, "deferred", "candidate missing related_petition_id")
    if not petition_id:
        return GovernanceGate(False, "deferred", "petition missing petition_id")
    if candidate_petition_id != petition_id:
        return GovernanceGate(False, "deferred", "candidate petition mismatch")
    if str(petition.get("record_type") or "").strip() != "dispatch_petition":
        return GovernanceGate(False, "deferred", "petition record_type must be dispatch_petition")
    if str(petition.get("status") or "").strip() != "approved":
        return GovernanceGate(False, "deferred", f"dispatch petition {petition_id} not approved")

    if str(decision.get("record_type") or "").strip() != "governance_decision":
        return GovernanceGate(False, "deferred", "decision record_type must be governance_decision")
    if str(decision.get("petition_id") or "").strip() != petition_id:
        return GovernanceGate(False, "deferred", "decision petition mismatch")
    if str(decision.get("decision_outcome") or "").strip() != "approve_collective":
        return GovernanceGate(False, "deferred", "decision does not approve collective")
    if str(decision.get("review_state") or "").strip() != "final":
        return GovernanceGate(False, "deferred", "decision is not final")
    if str(decision.get("related_collective_id") or "").strip():
        return GovernanceGate(False, "blocked", "decision already linked to collective")

    return GovernanceGate(True, "allowed", f"dispatch petition {petition_id} approved with governance decision {decision.get('decision_id')}")


def can_bridge_to_honcho(
    record: dict[str, Any],
    *,
    return_all: dict[str, Any] | None = None,
    nanny: dict[str, Any] | None = None,
) -> GovernanceGate:
    return_all = return_all or read_return_all_state()
    nanny = nanny or read_nanny_state()

    if return_all.get("enabled"):
        return GovernanceGate(False, "paused", "return_all active")

    if _nanny_is_cooling(nanny):
        temperature = str(nanny.get("temperature") or "cool")
        cooldown = int(nanny.get("global_cooldown_seconds") or 0)
        return GovernanceGate(False, "paused", f"nanny {temperature} or cooldown {cooldown}s active")

    if str(record.get("record_type") or "").strip() != "collective_memory":
        return GovernanceGate(False, "deferred", "record_type must be collective_memory")

    record_id = str(record.get("record_id") or "").strip()
    collective_record_id = str(record.get("collective_record_id") or "").strip()
    candidate_id = str(record.get("candidate_id") or "").strip()
    related_petition_id = str(record.get("related_petition_id") or "").strip()
    governance_decision_id = str(record.get("governance_decision_id") or "").strip()
    governance_approval_ref = str(record.get("governance_approval_ref") or "").strip()
    admitted_at = str(record.get("admitted_at") or "").strip()
    admission_actor = str(record.get("admission_actor") or "").strip()
    governance_review_state = str(record.get("governance_review_state") or "").strip()
    legacy_compatibility = bool(record.get("legacy_compatibility") is True)

    full_lineage = bool(record_id and collective_record_id and candidate_id and related_petition_id and governance_decision_id)

    if not full_lineage:
        if legacy_compatibility and str(record.get("approval_timestamp") or "").strip() and governance_approval_ref.startswith("legacy:"):
            return GovernanceGate(True, "allowed", "explicitly grandfathered legacy collective record")
        return GovernanceGate(False, "deferred", "missing full collective lineage")

    if collective_record_id != record_id:
        return GovernanceGate(False, "deferred", "collective_record_id does not match record_id")

    if governance_approval_ref != f"decision:{governance_decision_id}":
        return GovernanceGate(False, "deferred", "governance_approval_ref does not match decision")
    if not admitted_at:
        return GovernanceGate(False, "deferred", "missing admitted_at")
    if not admission_actor:
        return GovernanceGate(False, "deferred", "missing admission_actor")
    if governance_review_state != "approved":
        return GovernanceGate(False, "deferred", "collective not marked approved")
    if not _has_governance_trail(record):
        return GovernanceGate(False, "deferred", "missing governance trail")

    status, _, petition = _find_petition(related_petition_id)
    if not petition:
        return GovernanceGate(False, "deferred", f"missing dispatch petition {related_petition_id}")
    if status != "approved":
        return GovernanceGate(False, "deferred", f"dispatch petition {related_petition_id} not approved")

    decision_path, decision = _find_governance_decision(decision_id=governance_decision_id, petition_id=related_petition_id)
    if not decision:
        return GovernanceGate(False, "deferred", f"missing governance decision {governance_decision_id}")
    if str(decision.get("record_type") or "").strip() != "governance_decision":
        return GovernanceGate(False, "deferred", "governance decision record_type invalid")
    if str(decision.get("petition_id") or "").strip() != related_petition_id:
        return GovernanceGate(False, "deferred", "governance decision petition mismatch")
    if str(decision.get("decision_outcome") or "").strip() != "approve_collective":
        return GovernanceGate(False, "deferred", "governance decision does not approve collective")
    if str(decision.get("review_state") or "").strip() != "final":
        return GovernanceGate(False, "deferred", "governance decision not final")
    decision_collective_id = str(decision.get("related_collective_id") or "").strip()
    if not legacy_compatibility and decision_collective_id != record_id:
        return GovernanceGate(False, "deferred", "governance decision not linked to this collective")
    if legacy_compatibility and decision_collective_id and decision_collective_id != record_id:
        return GovernanceGate(False, "deferred", "governance decision linked to a different collective")

    return GovernanceGate(True, "allowed", f"collective {record_id} approved with decision {governance_decision_id}")


def should_require_operator_review(
    *,
    return_all: dict[str, Any] | None = None,
    nanny: dict[str, Any] | None = None,
    record: dict[str, Any] | None = None,
) -> bool:
    return_all = return_all or read_return_all_state()
    nanny = nanny or read_nanny_state()

    if return_all.get("enabled"):
        return True
    if _nanny_is_cooling(nanny):
        return True
    if record is not None and not _has_governance_trail(record):
        return True
    return False


def resolve_related_petition_id(record: dict[str, Any]) -> str:
    return _resolve_related_petition_id(record)
