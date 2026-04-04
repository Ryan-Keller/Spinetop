from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from create_dispatch_petition import build_petition_payload, create_dispatch_petition_from_fields
from governance_utils import can_create_dispatch, read_nanny_state, read_return_all_state
from record_schemas import PETITION_KINDS, REQUESTED_ACTIONS
from repo_paths import repo_root
from support_validation import require_object, require_string


ROOT = repo_root()
DRAFTS_DIR = ROOT / "memory" / "drafts"
DISPATCH_PENDING_DIR = ROOT / "memory" / "dispatch" / "pending"


class DraftReviewError(ValueError):
    pass


def _path_hint(path: Path | None) -> str:
    return f" ({path})" if path else ""


def _is_under(path: Path, root: Path) -> bool:
    path = path.resolve()
    root = root.resolve()
    return path == root or root in path.parents


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DraftReviewError(f"Missing file{_path_hint(path)}") from exc
    except json.JSONDecodeError as exc:
        raise DraftReviewError(f"Malformed JSON{_path_hint(path)}: {exc}") from exc


def _resolve_draft_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        path = candidate.resolve()
    else:
        normalized = value.replace("\\", "/")
        if normalized.startswith("memory/drafts/"):
            path = (ROOT / candidate).resolve()
        else:
            path = (DRAFTS_DIR / candidate).resolve()
    if not _is_under(path, DRAFTS_DIR):
        raise DraftReviewError(f"Draft must stay inside memory/drafts/{_path_hint(path)}")
    return path


def _require_number(data: dict[str, Any], field: str, *, path: Path | None = None) -> float:
    value = data.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DraftReviewError(f"Field '{field}' must be numeric{_path_hint(path)}")
    return float(value)


def _require_list_of_strings(data: dict[str, Any], field: str, *, path: Path | None = None) -> list[str]:
    value = data.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        raise DraftReviewError(f"Field '{field}' must be a list{_path_hint(path)}")
    out: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            raise DraftReviewError(f"Field '{field}' item {idx} must be a string{_path_hint(path)}")
        text = item.strip()
        if not text:
            raise DraftReviewError(f"Field '{field}' item {idx} must not be empty{_path_hint(path)}")
        out.append(text)
    return out


def validate_draft_petition(data: Any, *, path: Path | None = None) -> dict[str, Any]:
    record = require_object(data, path=path, error_cls=DraftReviewError)

    petition_id = require_string(record, "petition_id", path=path, error_cls=DraftReviewError)
    if not petition_id.startswith("draft_"):
        raise DraftReviewError(f"Draft petition_id must start with draft_{_path_hint(path)}")

    created_by = require_string(record, "created_by", path=path, error_cls=DraftReviewError)
    mode = require_string(record, "mode", path=path, error_cls=DraftReviewError)
    status = require_string(record, "status", path=path, error_cls=DraftReviewError)
    if status != "draft":
        raise DraftReviewError(f"Draft status must be draft{_path_hint(path)}")
    summary = require_string(record, "summary", path=path, error_cls=DraftReviewError)
    requested_action = require_string(record, "requested_action", path=path, error_cls=DraftReviewError)
    if requested_action not in REQUESTED_ACTIONS:
        raise DraftReviewError(f"requested_action must be one of {sorted(REQUESTED_ACTIONS)}{_path_hint(path)}")
    source_run_id = require_string(record, "source_run_id", path=path, error_cls=DraftReviewError)
    confidence = _require_number(record, "confidence", path=path)
    evidence_refs = _require_list_of_strings(record, "evidence_refs", path=path)

    petition_kind = str(record.get("petition_kind") or "").strip()
    petition_type = str(record.get("petition_type") or "").strip()
    if petition_kind and petition_type and petition_kind != petition_type:
        raise DraftReviewError(f"petition_kind and petition_type must match when both are present{_path_hint(path)}")
    if not petition_kind:
        petition_kind = petition_type
    if petition_kind not in PETITION_KINDS:
        raise DraftReviewError(f"petition_kind must be one of {sorted(PETITION_KINDS)}{_path_hint(path)}")

    normalized = dict(record)
    normalized["petition_id"] = petition_id
    normalized["created_by"] = created_by
    normalized["mode"] = mode
    normalized["status"] = status
    normalized["summary"] = summary
    normalized["petition_kind"] = petition_kind
    normalized["petition_type"] = petition_kind
    normalized["requested_action"] = requested_action
    normalized["source_run_id"] = source_run_id
    normalized["confidence"] = confidence
    normalized["evidence_refs"] = evidence_refs
    normalized["notes"] = str(record.get("notes") or "").strip()
    normalized["low_priority"] = bool(record.get("low_priority") is True)
    normalized["workspace"] = str(record.get("workspace") or "spinetop").strip() or "spinetop"
    normalized["agent_id"] = str(record.get("agent_id") or created_by).strip() or created_by
    return normalized


def _entry_class_for_petition_kind(petition_kind: str) -> str:
    return {
        "repair_request": "repair",
        "self_heal_request": "self_heal",
        "anomaly_review": "anomaly_review",
    }.get(petition_kind, "normal")


def build_submission_args(draft: dict[str, Any]) -> dict[str, Any]:
    entry_class = _entry_class_for_petition_kind(str(draft["petition_kind"]))
    risk_level = "high" if draft["petition_kind"] in {"anomaly_review", "repair_request"} else "medium"
    return {
        "status": "pending",
        "agent_id": draft["agent_id"],
        "workspace": draft["workspace"],
        "task": draft["summary"],
        "summary": draft["summary"],
        "petition_kind": draft["petition_kind"],
        "reason": draft["summary"],
        "evidence_refs": list(draft["evidence_refs"]),
        "requested_action": draft["requested_action"],
        "risk_level": risk_level,
        "related_record_id": draft["source_run_id"],
        "related_petition_id": "",
        "cooldown_observed": None,
        "governance_notes": "",
        "ask_count": 1,
        "spawn_authority": "operator",
        "dispatch_mode": "normal",
        "operator_id": "",
        "entry_class": entry_class,
        "petition_id": draft["petition_id"],
    }


def build_review_payload(
    draft: dict[str, Any],
    *,
    draft_path: Path,
    return_all: dict[str, Any],
    nanny: dict[str, Any],
) -> dict[str, Any]:
    submission_args = build_submission_args(draft)
    gate = can_create_dispatch(
        spawn_authority=submission_args["spawn_authority"],
        dispatch_mode=submission_args["dispatch_mode"],
        entry_class=submission_args["entry_class"],
        return_all=return_all,
        nanny=nanny,
    )
    preview = {
        "draft_path": str(draft_path),
        "draft": draft,
        "submission_allowed": gate.allowed,
        "submission_gate": {
            "status": gate.status,
            "reason": gate.reason,
        },
    }
    if gate.allowed:
        payload, path, petition_id, _, _ = build_petition_payload(**submission_args)
        preview["dispatch_preview"] = payload
        preview["dispatch_path"] = str(path)
        preview["dispatch_petition_id"] = petition_id
    else:
        preview["dispatch_preview"] = submission_args
        preview["dispatch_path"] = str(DISPATCH_PENDING_DIR / f"dispatch_{draft['petition_id']}_pending.json")
        preview["dispatch_petition_id"] = draft["petition_id"]
    return preview


def review(draft_path: Path) -> int:
    draft = validate_draft_petition(_load_json(draft_path), path=draft_path)
    preview = build_review_payload(
        draft,
        draft_path=draft_path,
        return_all=read_return_all_state(),
        nanny=read_nanny_state(),
    )
    print(json.dumps(preview, indent=2, ensure_ascii=False))
    return 0


def submit(draft_path: Path) -> int:
    draft = validate_draft_petition(_load_json(draft_path), path=draft_path)
    submission_args = build_submission_args(draft)
    gate = can_create_dispatch(
        spawn_authority=submission_args["spawn_authority"],
        dispatch_mode=submission_args["dispatch_mode"],
        entry_class=submission_args["entry_class"],
        return_all=read_return_all_state(),
        nanny=read_nanny_state(),
    )
    if not gate.allowed:
        raise DraftReviewError(f"Submission blocked: {gate.reason}")

    target_path = DISPATCH_PENDING_DIR / f"dispatch_{draft['petition_id']}_pending.json"
    if target_path.exists():
        raise DraftReviewError(f"Target dispatch petition already exists: {target_path}")

    _, path, petition_id = create_dispatch_petition_from_fields(**submission_args)
    print(json.dumps({"submitted": True, "petition_id": petition_id, "path": str(path)}, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Review and submit a draft petition through governed dispatch creation.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    review_parser = subparsers.add_parser("review", help="Validate and preview a draft petition.")
    review_parser.add_argument("draft_json", help="Draft filename under memory/drafts/")

    submit_parser = subparsers.add_parser("submit", help="Submit a draft petition through governed dispatch creation.")
    submit_parser.add_argument("draft_json", help="Draft filename under memory/drafts/")

    args = parser.parse_args()

    draft_path = _resolve_draft_path(args.draft_json)
    try:
        if not draft_path.exists():
            raise DraftReviewError(f"Missing draft file: {draft_path}")
        if args.command == "review":
            return review(draft_path)
        if args.command == "submit":
            return submit(draft_path)
    except DraftReviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
