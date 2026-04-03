from __future__ import annotations

import argparse
import hashlib
import json
import socket
from pathlib import Path
from typing import Any

from governance_utils import can_create_dispatch, read_nanny_state, read_return_all_state
from record_schemas import build_dispatch_petition_record, utc_now_iso
from repo_paths import repo_root


ROOT = repo_root()
DISPATCH_DIR = ROOT / "memory" / "dispatch"


def build_petition_id(agent_id: str, workspace: str, task: str, summary: str, stamp: str) -> str:
    seed = f"{agent_id}|{workspace}|{task}|{summary}|{stamp}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6]
    return f"{agent_id}_{stamp}_{digest}"


def _normalize_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def build_petition_payload(
    *,
    status: str,
    agent_id: str,
    workspace: str,
    task: str,
    summary: str,
    petition_kind: str = "memory_admission",
    reason: str = "",
    evidence_refs: list[str] | None = None,
    requested_action: str = "admit_to_collective",
    risk_level: str = "medium",
    related_record_id: str = "",
    related_petition_id: str = "",
    cooldown_observed: int | None = None,
    governance_notes: str = "",
    ask_count: int = 1,
    spawn_authority: str = "emissary",
    dispatch_mode: str = "normal",
    operator_id: str = "",
    entry_class: str = "normal",
) -> tuple[dict[str, Any], Path, str]:
    status = status.strip().lower()
    if status not in {"pending", "approved", "deferred", "rejected"}:
        raise ValueError(f"Unsupported petition status: {status}")

    target_dir = DISPATCH_DIR / status
    target_dir.mkdir(parents=True, exist_ok=True)

    stamp = utc_now_iso().replace("-", "").replace(":", "").replace("+00:00", "Z")
    petition_id = build_petition_id(agent_id, workspace, task, summary, stamp)
    record_name = f"dispatch_{petition_id}_{status}.json"
    now_iso = utc_now_iso()
    source_host = socket.gethostname()
    ask_count = max(1, int(ask_count))

    return_all = read_return_all_state()
    nanny = read_nanny_state()
    gate = can_create_dispatch(
        spawn_authority=spawn_authority,
        dispatch_mode=dispatch_mode,
        entry_class=entry_class,
        return_all=return_all,
        nanny=nanny,
    )

    if not gate.allowed:
        status = "deferred"
        target_dir = DISPATCH_DIR / status
        target_dir.mkdir(parents=True, exist_ok=True)
        record_name = f"dispatch_{petition_id}_{status}.json"

    requires_operator_approval = ask_count > 1 or not gate.allowed
    if not reason:
        reason = task or summary
    if not petition_kind:
        petition_kind = "memory_admission" if entry_class == "normal" else {
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
    if not related_record_id:
        related_record_id = task or summary

    payload = build_dispatch_petition_record(
        petition_id=petition_id,
        created_by=agent_id,
        workspace=workspace,
        status=status,
        petition_kind=petition_kind,
        summary=summary,
        reason=reason,
        evidence_refs=evidence_refs or [],
        requested_action=requested_action,
        risk_level=risk_level,
        requires_operator_approval=requires_operator_approval,
        entry_class=entry_class,
        related_record_id=related_record_id,
        related_petition_id=related_petition_id,
        cooldown_observed=cooldown_observed,
        governance_notes=governance_notes,
        operator_id=operator_id,
        source_host=source_host,
        base_record={
            "agent_id": agent_id,
            "task": task,
            "summary": summary,
            "confidence": 0.5,
            "promotion_candidate": False,
            "payload_type": "pattern",
            "urgency": "normal",
            "requires_emissary": True,
            "ask_count": ask_count,
            "spawn_authority": spawn_authority,
            "dispatch_mode": dispatch_mode,
            "operator_id": operator_id,
            "governance_status": gate.status,
            "governance_reason": gate.reason,
            "nanny_temperature": nanny.get("temperature", "cool"),
            "nanny_cooldown_seconds": nanny.get("global_cooldown_seconds", 0),
        },
    )
    payload["record_name"] = record_name
    path = target_dir / record_name
    return payload, path, petition_id


def create_dispatch_petition_from_fields(
    *,
    status: str,
    agent_id: str,
    workspace: str,
    task: str,
    summary: str,
    petition_kind: str = "memory_admission",
    reason: str = "",
    evidence_refs: list[str] | None = None,
    requested_action: str = "admit_to_collective",
    risk_level: str = "medium",
    related_record_id: str = "",
    related_petition_id: str = "",
    cooldown_observed: int | None = None,
    governance_notes: str = "",
    ask_count: int = 1,
    spawn_authority: str = "emissary",
    dispatch_mode: str = "normal",
    operator_id: str = "",
    entry_class: str = "normal",
) -> tuple[dict[str, Any], Path, str]:
    payload, path, petition_id = build_petition_payload(
        status=status,
        agent_id=_normalize_text(agent_id, "unknown"),
        workspace=_normalize_text(workspace, "unknown"),
        task=_normalize_text(task),
        summary=_normalize_text(summary),
        petition_kind=_normalize_text(petition_kind, "memory_admission"),
        reason=_normalize_text(reason),
        evidence_refs=evidence_refs,
        requested_action=_normalize_text(requested_action, "admit_to_collective"),
        risk_level=_normalize_text(risk_level, "medium"),
        related_record_id=_normalize_text(related_record_id),
        related_petition_id=_normalize_text(related_petition_id),
        cooldown_observed=cooldown_observed,
        governance_notes=_normalize_text(governance_notes),
        ask_count=ask_count,
        spawn_authority=spawn_authority,
        dispatch_mode=dispatch_mode,
        operator_id=_normalize_text(operator_id),
        entry_class=_normalize_text(entry_class, "normal"),
    )
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload, path, petition_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("status", choices=["pending", "approved", "deferred", "rejected"])
    parser.add_argument("agent_id")
    parser.add_argument("workspace")
    parser.add_argument("task")
    parser.add_argument("summary")
    parser.add_argument("--ask-count", type=int, default=1)
    parser.add_argument("--spawn-authority", default="emissary", choices=["operator", "custodial", "emissary"])
    parser.add_argument("--dispatch-mode", default="normal", choices=["normal", "rapid"])
    parser.add_argument("--operator-id", default="")
    parser.add_argument("--petition-kind", default="memory_admission", choices=["memory_admission", "anomaly_review", "repair_request", "operator_review", "self_heal_request"])
    parser.add_argument("--reason", default="")
    parser.add_argument("--requested-action", default="admit_to_collective", choices=["admit_to_collective", "operator_review", "repair", "defer", "reject"])
    parser.add_argument("--risk-level", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--related-record-id", default="")
    parser.add_argument("--related-petition-id", default="")
    parser.add_argument("--cooldown-observed", type=int, default=None)
    parser.add_argument("--governance-notes", default="")
    parser.add_argument("--evidence-ref", action="append", dest="evidence_refs", default=[])
    parser.add_argument(
        "--entry-class",
        default="normal",
        choices=["normal", "self_heal", "repair", "anomaly_review"],
    )
    args = parser.parse_args()

    _, path, _ = create_dispatch_petition_from_fields(
        status=args.status,
        agent_id=args.agent_id,
        workspace=args.workspace,
        task=args.task,
        summary=args.summary,
        petition_kind=args.petition_kind,
        reason=args.reason,
        evidence_refs=args.evidence_refs,
        requested_action=args.requested_action,
        risk_level=args.risk_level,
        related_record_id=args.related_record_id,
        related_petition_id=args.related_petition_id,
        cooldown_observed=args.cooldown_observed,
        governance_notes=args.governance_notes,
        ask_count=args.ask_count,
        spawn_authority=args.spawn_authority,
        dispatch_mode=args.dispatch_mode,
        operator_id=args.operator_id,
        entry_class=args.entry_class,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
