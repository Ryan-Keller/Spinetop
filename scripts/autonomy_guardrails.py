from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from helper_model_runtime import load_helper_runtime_profile
from repo_paths import repo_root


ROOT = repo_root()
CONFIG_DIR = ROOT / "config"
ROLE_CARD_BY_ID = {
    "spinetop_expeditioner": CONFIG_DIR / "expeditioner_role.json",
    "spinetop-helper_2b": CONFIG_DIR / "helper_role.json",
    "spinetop-mirror": CONFIG_DIR / "mirror_role.json",
}
FORBIDDEN_WRITE_PREFIXES = (
    "memory/collective/",
    "memory/dispatch/approved/",
    "Honcho",
    "services/honcho/",
)
ROLE_ALLOWED_ACTIONS = {
    "spinetop_expeditioner": {
        "start_first_pass_expedition",
        "retry_expedition_refresh",
        "resume_expedition",
    },
}
ACTION_WRITE_TARGETS = {
    "start_first_pass_expedition": ["workbench/missions/", "logs/support/"],
    "retry_expedition_refresh": ["workbench/missions/", "logs/support/"],
    "resume_expedition": ["workbench/missions/"],
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _load_role_card(role_id: str) -> dict[str, Any]:
    path = ROLE_CARD_BY_ID.get(role_id)
    if path is None or not path.exists():
        return {}
    return _load_json(path)


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return items


def _contains_missing_artifact(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return any(
        token in normalized
        for token in (
            "missing artifact",
            "missing file",
            "missing receipt",
            "missing evidence bundle",
            "artifact missing",
        )
    )


def _check_result(name: str, ok: bool, *, code: str, reason: str = "", detail: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "code": code,
        "reason": reason.strip(),
        "detail": detail.strip(),
    }


def evaluate_autonomy_guardrails(
    *,
    mission_id: str,
    trigger_kind: str,
    target_role: str,
    allowed_action: str,
    policy_basis: str,
    trigger_reason: str,
    trigger_source: str,
    retry_budget_total: int,
    retry_budget_used: int,
    return_all_enabled: bool,
    nanny_cooling: bool,
    parked: bool,
    allow_while_parked: bool,
    counts_against_retry_budget: bool,
    summary: dict[str, Any] | None = None,
    working_memory: dict[str, Any] | None = None,
    write_targets: list[str] | None = None,
) -> dict[str, Any]:
    summary = summary if isinstance(summary, dict) else {}
    working_memory = working_memory if isinstance(working_memory, dict) else {}
    write_targets = list(write_targets or ACTION_WRITE_TARGETS.get(allowed_action) or [])

    checks: list[dict[str, Any]] = []
    checks.append(
        _check_result(
            "kill_switch",
            not (return_all_enabled or nanny_cooling),
            code="kill_switch_active",
            reason="blocked by kill-switch" if (return_all_enabled or nanny_cooling) else "",
            detail="return-all or nanny cooling is active" if (return_all_enabled or nanny_cooling) else "",
        )
    )
    checks.append(
        _check_result(
            "mission_parked",
            not (parked and not allow_while_parked),
            code="mission_parked",
            reason="blocked by parked mission" if (parked and not allow_while_parked) else "",
            detail="mission requires an explicit resume before autonomy can move" if (parked and not allow_while_parked) else "",
        )
    )

    role_card = _load_role_card(target_role)
    role_profile = None
    try:
        role_profile = load_helper_runtime_profile(target_role)
    except Exception:
        role_profile = None

    allowed_actions = ROLE_ALLOWED_ACTIONS.get(target_role, set())
    role_allowed = bool(target_role and allowed_action and allowed_action in allowed_actions)
    checks.append(
        _check_result(
            "role_action",
            role_allowed,
            code="role_boundary",
            reason="blocked by role boundary" if not role_allowed else "",
            detail=f"{target_role or 'unknown role'} may not perform {allowed_action or 'unknown action'}" if not role_allowed else "",
        )
    )

    retry_allowed = True
    if counts_against_retry_budget:
        retry_allowed = retry_budget_used < retry_budget_total
    checks.append(
        _check_result(
            "retry_budget",
            retry_allowed,
            code="retry_budget_exhausted",
            reason="blocked by exhausted retry budget" if not retry_allowed else "",
            detail=f"{retry_budget_used} used of {retry_budget_total}" if counts_against_retry_budget else "not counted against retry budget",
        )
    )

    trigger_policy_valid = bool(
        trigger_kind.strip() and allowed_action.strip() and policy_basis.strip() and trigger_reason.strip() and trigger_source.strip()
    )
    checks.append(
        _check_result(
            "trigger_policy",
            trigger_policy_valid,
            code="trigger_policy_invalid",
            reason="blocked by invalid trigger policy" if not trigger_policy_valid else "",
            detail="trigger kind, source, reason, action, and policy basis are all required" if not trigger_policy_valid else "",
        )
    )

    blocked_reason = str(summary.get("blocked_reason") or working_memory.get("blocked_reason") or "").strip()
    mission_sufficient = True
    sufficiency_reason = ""
    if _contains_missing_artifact(blocked_reason):
        mission_sufficient = False
        sufficiency_reason = "blocked by missing required artifact"
    elif allowed_action in {"start_first_pass_expedition", "resume_expedition"} and blocked_reason and not bool(summary.get("can_continue_without_input")):
        mission_sufficient = False
        sufficiency_reason = "blocked by insufficient mission context"
    checks.append(
        _check_result(
            "mission_sufficiency",
            mission_sufficient,
            code="mission_insufficient",
            reason=sufficiency_reason,
            detail=blocked_reason,
        )
    )

    may_not_write = _normalize_string_list(((role_card.get("memory_refs") or {}) if isinstance(role_card.get("memory_refs"), dict) else {}).get("may_not_write"))
    may_write_only = _normalize_string_list(((role_card.get("memory_refs") or {}) if isinstance(role_card.get("memory_refs"), dict) else {}).get("may_write_only"))
    if role_profile is not None:
        may_not_write.extend(_normalize_string_list(role_profile.authority_boundary.get("may_not")))
    normalized_targets = [str(target).strip().replace("\\", "/") for target in write_targets if str(target).strip()]
    forbidden_target = ""
    for target in normalized_targets:
        if any(target.startswith(prefix) or target == prefix.rstrip("/") for prefix in FORBIDDEN_WRITE_PREFIXES if prefix != "Honcho"):
            forbidden_target = target
            break
        if target == "Honcho" or target.startswith("Honcho/"):
            forbidden_target = target
            break
        if any(token in target for token in ("memory/collective", "memory/dispatch/approved", "services/honcho")):
            forbidden_target = target
            break
        if may_write_only and not any(target.startswith(scope.split(" ")[0]) for scope in may_write_only if scope.split(" ")[0]):
            forbidden_target = target
            break
        if any(token and token in target for token in may_not_write if "/" in token):
            forbidden_target = target
            break
    checks.append(
        _check_result(
            "write_target",
            not bool(forbidden_target),
            code="forbidden_write_target",
            reason="blocked by forbidden write target" if forbidden_target else "",
            detail=forbidden_target,
        )
    )

    failed = next((check for check in checks if not check["ok"]), None)
    status = "allowed" if failed is None else "blocked"
    status_reason = "" if failed is None else str(failed.get("reason") or "blocked by guardrail")
    return {
        "mission_id": mission_id,
        "status": status,
        "reason": status_reason,
        "checks": checks,
        "write_targets": normalized_targets,
        "target_role": target_role,
        "allowed_action": allowed_action,
        "trigger_kind": trigger_kind,
    }


def build_autonomy_status_view(
    *,
    mission_id: str,
    latest_trigger: dict[str, Any] | None,
    trigger_handoff: dict[str, Any] | None,
    retry_ledger: dict[str, Any] | None,
    parking_status: dict[str, Any] | None,
    mission_summary: dict[str, Any] | None,
    return_all_enabled: bool,
    nanny_cooling: bool,
) -> dict[str, Any]:
    latest_trigger = latest_trigger if isinstance(latest_trigger, dict) else {}
    trigger_handoff = trigger_handoff if isinstance(trigger_handoff, dict) else {}
    retry_ledger = retry_ledger if isinstance(retry_ledger, dict) else {}
    parking_status = parking_status if isinstance(parking_status, dict) else {}
    mission_summary = mission_summary if isinstance(mission_summary, dict) else {}

    decision_log = retry_ledger.get("decision_log")
    last_retry_decision = decision_log[-1] if isinstance(decision_log, list) and decision_log else {}
    latest_trigger_evaluation = (latest_trigger.get("evaluation") or {}) if isinstance(latest_trigger.get("evaluation"), dict) else {}
    last_allowed_reason = str(latest_trigger_evaluation.get("allowed_reason") or "").strip()
    last_trigger_blocked_reason = str(latest_trigger_evaluation.get("blocked_reason") or "").strip()
    last_trigger_reason = last_allowed_reason or last_trigger_blocked_reason
    last_blocked_reason = (
        str(last_trigger_blocked_reason or "").strip()
        or str(last_retry_decision.get("why_blocked") or "").strip()
        or str(mission_summary.get("blocked_reason") or "").strip()
        or str(parking_status.get("reason") or "").strip()
    )

    budget_total = int(retry_ledger.get("retry_budget_total") or 0)
    budget_used = int(retry_ledger.get("retry_budget_used") or 0)
    budget_remaining = max(0, budget_total - budget_used)
    status = "ready"
    if return_all_enabled or nanny_cooling:
        status = "blocked"
    elif str(parking_status.get("status") or "active") == "parked":
        status = "blocked"
    elif str(trigger_handoff.get("status") or "") == "blocked":
        status = "blocked"
    elif last_blocked_reason:
        status = "guarded"

    trigger_kind = str(latest_trigger.get("trigger_kind") or "none").strip() or "none"
    trigger_status = str(latest_trigger.get("status") or "idle").strip() or "idle"
    last_trigger_outcome = f"{trigger_status}: {trigger_kind}"
    if last_trigger_reason:
        last_trigger_outcome = f"{last_trigger_outcome} ({last_trigger_reason})"

    retry_budget_summary = f"{budget_used}/{budget_total} used, {budget_remaining} remaining"
    return {
        "mission_id": mission_id,
        "status": status,
        "autonomy_status": "blocked" if status == "blocked" else "guarded" if status == "guarded" else "ready",
        "last_trigger_outcome": last_trigger_outcome,
        "retry_budget_summary": retry_budget_summary,
        "last_blocked_reason": last_blocked_reason,
        "kill_switch_active": bool(return_all_enabled or nanny_cooling),
        "parked": str(parking_status.get("status") or "active") == "parked",
        "pending_action": str(trigger_handoff.get("allowed_action") or "").strip(),
        "pending_status": str(trigger_handoff.get("status") or "idle").strip() or "idle",
    }
