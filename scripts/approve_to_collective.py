from __future__ import annotations

import json
import sys

from governance_utils import (
    can_admit_to_collective,
    find_approved_petition,
    find_governance_decision_for_petition,
    read_nanny_state,
    read_return_all_state,
    resolve_related_petition_id,
)
from record_schemas import (
    build_collective_record_from_candidate,
    build_governance_decision_record,
    normalize_candidate_memory_record,
    utc_now_iso,
)
from memory_flow_utils import (
    ensure_in_dir,
    memory_dir,
    resolve_in_dir,
    safe_destination,
    write_json,
)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/approve_to_collective.py <candidate-json>", file=sys.stderr)
        return 1

    promotion = memory_dir("promotion")
    collective = memory_dir("collective")
    source = resolve_in_dir(sys.argv[1], promotion)

    if not source.exists():
        print(f"Missing file: {source}", file=sys.stderr)
        return 1

    try:
        ensure_in_dir(source, promotion)
        data = normalize_candidate_memory_record(json.loads(source.read_text(encoding="utf-8")), path=source, legacy_ok=True)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    related_petition_id = resolve_related_petition_id(data)
    if related_petition_id:
        data["related_petition_id"] = related_petition_id
    petition_path, petition = find_approved_petition(related_petition_id) if related_petition_id else (None, None)
    if not petition:
        data["governance_review_state"] = "deferred"
        data["governance_review_reason"] = f"missing approved dispatch petition {related_petition_id or '(none)'}"
        data["governance_review_timestamp"] = utc_now_iso()
        write_json(source, data)
        print(f"Deferred: {source} (missing approved dispatch petition)", file=sys.stderr)
        return 0

    decision_path, decision = find_governance_decision_for_petition(related_petition_id)
    if not decision:
        decision = build_governance_decision_record(
            petition_id=petition["petition_id"],
            petition_kind=str(petition.get("petition_kind") or "memory_admission"),
            decision_outcome="approve_collective",
            created_by=str(petition.get("created_by") or data.get("submitted_by") or "unknown"),
            summary=str(petition.get("summary") or data.get("summary") or "governance decision"),
            reason=str(petition.get("reason") or petition.get("summary") or "governance approval"),
            evidence_refs=list(petition.get("evidence_refs") or []),
            risk_level=str(petition.get("risk_level") or "medium"),
            requires_operator_review=False,
            review_state="final",
            operator_id=str(petition.get("operator_id") or data.get("submitted_by") or ""),
            source_host=str(petition.get("source_host") or ""),
            decision_notes="created by governed admission ritual",
            governance_notes=str(petition.get("governance_notes") or ""),
            legacy_compatibility=bool(data.get("legacy_compatibility", False)),
        )
        decision_path = (petition_path.parent if petition_path else (memory_dir("dispatch") / "approved")) / f"decision_{decision['decision_id']}.json"

    gate = can_admit_to_collective(
        data,
        petition,
        decision,
        return_all=read_return_all_state(),
        nanny=read_nanny_state(),
    )

    if not gate.allowed:
        data["governance_review_state"] = gate.status
        data["governance_review_reason"] = gate.reason
        data["governance_review_timestamp"] = utc_now_iso()
        write_json(source, data)
        print(f"Deferred: {source} ({gate.reason})")
        return 0

    try:
        collective_record = build_collective_record_from_candidate(
            data,
            governance_decision_id=str(decision["decision_id"]),
            related_petition_id=str(petition["petition_id"]),
            admitted_at=utc_now_iso(),
        )
    except Exception as exc:
        data["governance_review_state"] = "deferred"
        data["governance_review_reason"] = str(exc)
        data["governance_review_timestamp"] = utc_now_iso()
        write_json(source, data)
        print(f"Deferred: {source} ({exc})", file=sys.stderr)
        return 0

    collective_record["approval_timestamp"] = collective_record["admitted_at"]
    collective_record["governance_review_state"] = "approved"
    collective_record["governance_review_reason"] = gate.reason
    collective_record["admission_actor"] = "governed_admission_script"
    write_json(source, collective_record)

    destination = safe_destination(source, collective)
    source.replace(destination)

    decision["related_collective_id"] = collective_record["record_id"]
    write_json(decision_path, decision)
    print(f"Admitted: {source} -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
