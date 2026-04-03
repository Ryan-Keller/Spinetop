from __future__ import annotations

import sys

from create_dispatch_petition import create_dispatch_petition_from_fields
from record_schemas import build_candidate_memory_record, utc_now_iso
from memory_flow_utils import (
    ensure_in_dir,
    memory_dir,
    resolve_in_dir,
    safe_destination,
    validate_file,
    write_json,
)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/promote_to_promotion.py <inbox-json>", file=sys.stderr)
        return 1

    inbox = memory_dir("inbox")
    promotion = memory_dir("promotion")
    source = resolve_in_dir(sys.argv[1], inbox)

    if not source.exists():
        print(f"Missing file: {source}", file=sys.stderr)
        return 1

    try:
        ensure_in_dir(source, inbox)
        data = validate_file(source)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if data.get("promotion_candidate") is not True:
        print(f"ERROR: promotion_candidate must be true to promote: {source}", file=sys.stderr)
        return 1

    try:
        candidate = build_candidate_memory_record(
            source_record=data,
            source_record_ref=f"memory/inbox/{source.name}",
            submitted_by=str(data.get("agent_id") or data.get("expert_name") or "unknown"),
            source_workspace=str(data.get("workspace") or "spinetop"),
            summary=str(data.get("summary") or ""),
            key_findings=list(data.get("key_findings") or []),
            recommended_action=str(data.get("recommended_action") or "pending_review"),
            confidence=float(data.get("confidence") or 0.0),
        )
    except Exception as exc:
        data["governance_review_state"] = "deferred"
        data["governance_review_reason"] = str(exc)
        data["governance_review_timestamp"] = utc_now_iso()
        write_json(source, data)
        print(f"Deferred: {source} ({exc})", file=sys.stderr)
        return 0

    try:
        _, petition_path, petition_id = create_dispatch_petition_from_fields(
            status="pending",
            agent_id=str(data.get("agent_id") or "unknown"),
            workspace=str(data.get("workspace") or "unknown"),
            task=str(data.get("task") or ""),
            summary=str(data.get("summary") or ""),
            petition_kind="memory_admission",
            reason=str(data.get("summary") or data.get("task") or ""),
            evidence_refs=[f"memory/inbox/{source.name}", candidate["record_id"]],
            requested_action="admit_to_collective",
            risk_level="medium",
            related_record_id=candidate["record_id"],
            related_petition_id="",
            ask_count=1,
            spawn_authority="emissary",
            dispatch_mode="normal",
            operator_id="",
            entry_class="normal",
        )
    except Exception as exc:
        data["governance_review_state"] = "deferred"
        data["governance_review_reason"] = str(exc)
        data["governance_review_timestamp"] = utc_now_iso()
        write_json(source, data)
        print(f"Deferred: {source} ({exc})", file=sys.stderr)
        return 0

    candidate["related_petition_id"] = petition_id
    candidate["governance_review_state"] = petition_path.parent.name
    candidate["governance_review_reason"] = "dispatch petition created for review"
    candidate["promotion_timestamp"] = utc_now_iso()
    write_json(source, candidate)

    destination = safe_destination(source, promotion)
    source.replace(destination)
    print(f"Promoted: {source} -> {destination}")
    print(f"Dispatch petition: {petition_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
