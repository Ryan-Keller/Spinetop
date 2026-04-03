from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from record_schemas import (
    normalize_candidate_memory_record,
    normalize_governance_decision_record,
    normalize_collective_memory_record,
    validate_candidate_memory_record,
    validate_governance_decision_record,
    validate_collective_memory_record,
)
from repo_paths import repo_root


ROOT = repo_root()
PROMOTION_DIR = ROOT / "memory" / "promotion"
COLLECTIVE_DIR = ROOT / "memory" / "collective"
DECISION_DIR = ROOT / "memory" / "dispatch" / "approved"


@dataclass(frozen=True)
class CheckResult:
    path: Path
    layer: str
    status: str
    detail: str


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _first_text(data: dict[str, Any], *fields: str) -> str:
    for field in fields:
        value = data.get(field)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return ""


def _has_nonempty_list(data: dict[str, Any], field: str) -> bool:
    value = data.get(field)
    if not isinstance(value, list):
        return False
    return any(isinstance(item, str) and item.strip() for item in value)


def classify_governance_decision_legacy(payload: dict[str, Any], path: Path) -> tuple[str, str]:
    summary = _first_text(payload, "summary", "task", "title")
    if not summary:
        return "operator_review_needed", "missing summary; cannot safely classify the decision"

    petition_id = _first_text(payload, "petition_id", "related_petition_id", "linked_petition_id")
    if not petition_id:
        return "operator_review_needed", "missing petition linkage; cannot anchor the decision"

    decision_outcome = _first_text(payload, "decision_outcome")
    status = _first_text(payload, "status", "review_state")
    legacy_signals = [
        bool(_first_text(payload, "decision_id")),
        bool(_first_text(payload, "governance_decision_ref")),
        bool(_first_text(payload, "approved_at")),
        bool(_first_text(payload, "approved_by")),
        bool(_first_text(payload, "approval_timestamp")),
        bool(_first_text(payload, "approval_reason")),
        bool(_first_text(payload, "deferred_at")),
        bool(_first_text(payload, "rejected_at")),
        bool(_first_text(payload, "governance_review_state")),
        bool(payload.get("legacy_compatibility") is True),
    ]
    has_legacy_signal = any(legacy_signals)

    if decision_outcome and has_legacy_signal:
        return "legacy", "legacy decision-shaped record can be normalized without inventing truth"

    if status in {"approved", "deferred", "rejected", "pending"} and has_legacy_signal:
        return "legacy", "legacy approval status can be mapped into decision outcome"

    if has_legacy_signal:
        return "grandfatherable", "legacy markers exist, but the record is too thin for safe normalization"

    return "operator_review_needed", "no explicit governance trail or legacy marker"


def classify_collective_legacy(payload: dict[str, Any], path: Path) -> tuple[str, str]:
    summary = _first_text(payload, "summary", "task")
    if not summary:
        return "operator_review_needed", "missing summary; cannot safely grandfather or normalize"

    if not _has_nonempty_list(payload, "key_findings"):
        return "operator_review_needed", "empty key_findings must not be fabricated"

    record_id = _first_text(payload, "record_id")
    created_at = _first_text(payload, "created_at", "timestamp_created", "promotion_timestamp", "approval_timestamp")
    if not record_id and not created_at:
        return "operator_review_needed", "weak identity: no record_id and no stable timestamp lineage"

    governance_ref = _first_text(payload, "governance_approval_ref", "related_petition_id")
    if governance_ref:
        return "normalizable", "explicit governance trail exists; envelope fields can be normalized without inventing content"

    legacy_markers = any(
        [
            payload.get("promotion_candidate") is True,
            payload.get("legacy_compatibility") is True,
            bool(_first_text(payload, "approval_timestamp")),
            bool(_first_text(payload, "timestamp_created")),
            bool(_first_text(payload, "source")),
            bool(_first_text(payload, "agent_id")),
            bool(_first_text(payload, "session_id")),
            bool(_first_text(payload, "expert_name")),
        ]
    )
    if legacy_markers:
        return "grandfatherable", "legacy-shaped record may remain historical, but it must stay explicitly marked legacy"

    return "operator_review_needed", "no explicit governance trail or legacy marker"


def check_promotion_file(path: Path) -> CheckResult:
    try:
        payload = load_json(path)
    except Exception as exc:
        return CheckResult(path, "promotion", "invalid", f"malformed json: {exc}")

    try:
        validate_candidate_memory_record(normalize_candidate_memory_record(payload, path=path, legacy_ok=False), path=path)
        return CheckResult(path, "promotion", "strict", "candidate_memory contract satisfied")
    except Exception as strict_exc:
        try:
            normalize_candidate_memory_record(payload, path=path, legacy_ok=True)
            return CheckResult(path, "promotion", "legacy", f"legacy-compatible but not strict: {strict_exc}")
        except Exception as legacy_exc:
            return CheckResult(path, "promotion", "invalid", f"{legacy_exc}")


def check_collective_file(path: Path) -> CheckResult:
    try:
        payload = load_json(path)
    except Exception as exc:
        return CheckResult(path, "collective", "invalid", f"malformed json: {exc}")

    try:
        validate_collective_memory_record(normalize_collective_memory_record(payload, path=path, legacy_ok=False), path=path)
        return CheckResult(path, "collective", "strict", "collective_memory contract satisfied")
    except Exception as strict_exc:
        status, detail = classify_collective_legacy(payload, path)
        return CheckResult(path, "collective", status, detail or f"legacy-compatible but not strict: {strict_exc}")


def check_decision_file(path: Path) -> CheckResult:
    try:
        payload = load_json(path)
    except Exception as exc:
        return CheckResult(path, "decision", "invalid", f"malformed json: {exc}")

    try:
        validate_governance_decision_record(normalize_governance_decision_record(payload, path=path, legacy_ok=False), path=path)
        return CheckResult(path, "decision", "strict", "governance_decision contract satisfied")
    except Exception as strict_exc:
        try:
            normalize_governance_decision_record(payload, path=path, legacy_ok=True)
        except Exception as legacy_exc:
            return CheckResult(path, "decision", "operator_review_needed", f"{legacy_exc}")
        status, detail = classify_governance_decision_legacy(payload, path)
        return CheckResult(path, "decision", status, detail or f"legacy-compatible but not strict: {strict_exc}")


def scan_dir(directory: Path, checker, pattern: str = "*.json") -> list[CheckResult]:
    if not directory.exists():
        return []
    rows: list[CheckResult] = []
    for path in sorted(directory.glob(pattern)):
        rows.append(checker(path))
    return rows


def print_results(title: str, results: list[CheckResult]) -> Counter[str]:
    counts = Counter(item.status for item in results)

    print(f"[{title}]")
    if not results:
        print("  no files found")
        return counts

    for item in results:
        print(f"  - {item.status.upper()}: {item.path.name} :: {item.detail}")
    summary = " ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    print(f"  summary: {summary or 'none'}")
    return counts


def main() -> int:
    promotion_results = scan_dir(PROMOTION_DIR, check_promotion_file)
    collective_results = scan_dir(COLLECTIVE_DIR, check_collective_file)
    decision_results = scan_dir(DECISION_DIR, check_decision_file, "decision_*.json")

    print("Spinetop memory migration check")
    print("")
    promo_counts = print_results("promotion", promotion_results)
    print("")
    coll_counts = print_results("collective", collective_results)
    print("")
    decision_counts = print_results("governance_decision", decision_results)
    print("")

    totals = promo_counts + coll_counts + decision_counts

    overall = " ".join(f"{key}={value}" for key, value in sorted(totals.items()))
    print(f"Overall: {overall or 'none'}")
    blocking = (
        totals.get("legacy", 0)
        or totals.get("invalid", 0)
        or totals.get("normalizable", 0)
        or totals.get("grandfatherable", 0)
        or totals.get("operator_review_needed", 0)
    )
    return 0 if not blocking else 2


if __name__ == "__main__":
    raise SystemExit(main())
