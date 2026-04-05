from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from state_machine import (
    mission_manifest_path,
    normalize_mission_id,
    read_artifact_index,
    read_mission_brief,
    read_state,
)

KIND_PROFILE: dict[str, dict[str, str]] = {
    "mission_brief": {
        "artifact_stage": "intake",
        "problem_role": "source",
        "quality_signal": "validated",
        "reusability_class": "mission_local",
    },
    "state": {
        "artifact_stage": "review",
        "problem_role": "review_note",
        "quality_signal": "validated",
        "reusability_class": "mission_local",
    },
    "hermes_run": {
        "artifact_stage": "processing",
        "problem_role": "analysis",
        "quality_signal": "validated",
        "reusability_class": "review_only",
    },
    "clarification_packet": {
        "artifact_stage": "review",
        "problem_role": "decision_support",
        "quality_signal": "validated",
        "reusability_class": "review_only",
    },
    "draft": {
        "artifact_stage": "review",
        "problem_role": "candidate",
        "quality_signal": "provisional",
        "reusability_class": "single_use",
    },
    "raw_data": {
        "artifact_stage": "intake",
        "problem_role": "source",
        "quality_signal": "raw",
        "reusability_class": "cross_mission_candidate",
    },
    "idea": {
        "artifact_stage": "analysis",
        "problem_role": "analysis",
        "quality_signal": "provisional",
        "reusability_class": "mission_local",
    },
    "finding": {
        "artifact_stage": "analysis",
        "problem_role": "analysis",
        "quality_signal": "validated",
        "reusability_class": "reusable",
    },
    "classification": {
        "artifact_stage": "classification",
        "problem_role": "decision_support",
        "quality_signal": "validated",
        "reusability_class": "reusable",
    },
    "review_note": {
        "artifact_stage": "review",
        "problem_role": "review_note",
        "quality_signal": "provisional",
        "reusability_class": "review_only",
    },
}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_digest(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _artifact_id(kind: str, path: str, created_at: str) -> str:
    seed = f"{kind}|{path}|{created_at}"
    return f"artifact_{_short_digest(seed)}"


def _artifact_meta(kind: str) -> dict[str, str]:
    return KIND_PROFILE.get(
        kind,
        {
            "artifact_stage": "review",
            "problem_role": "derived",
            "quality_signal": "provisional",
            "reusability_class": "mission_local",
        },
    )


def _latest_hermes_run_id(items: list[dict[str, Any]]) -> str:
    for item in reversed(items):
        if str(item.get("kind") or "").strip() != "hermes_run":
            continue
        path_text = _text(item.get("path"))
        if not path_text:
            continue
        stem = Path(path_text).stem
        if "_" in stem:
            return stem.rsplit("_", 1)[0]
        return stem
    return ""


def _created_at_seed(existing: dict[str, Any] | None, brief: dict[str, Any] | None, items: list[dict[str, Any]]) -> str:
    if isinstance(existing, dict) and _text(existing.get("created_at")):
        return _text(existing.get("created_at"))
    if isinstance(brief, dict) and _text(brief.get("created_at")):
        return _text(brief.get("created_at"))
    for item in items:
        created_at = _text(item.get("created_at"))
        if created_at:
            return created_at
    return iso_now()


def _derive_status(current_state: str, artifact_refs: list[dict[str, Any]]) -> str:
    kinds = {str(item.get("artifact_kind") or "").strip() for item in artifact_refs}
    if current_state == "MISSION_CLOSED":
        return "complete"
    if current_state == "ARCHIVE_REVIEW":
        return "archived"
    if "clarification_packet" in kinds or current_state in {"CLARIFICATION_NEEDED", "CITADEL_REVIEW_LOOP"}:
        return "needs_review"
    if "draft" in kinds or current_state in {"PACKAGE_READY", "BRIDGE_CONSIDERATION"}:
        return "ready_for_review"
    return "active"


def _derive_counts(artifact_refs: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    by_stage: dict[str, int] = {}
    by_problem_role: dict[str, int] = {}
    for item in artifact_refs:
        kind = _text(item.get("artifact_kind"))
        stage = _text(item.get("artifact_stage"))
        role = _text(item.get("problem_role"))
        if kind:
            by_kind[kind] = by_kind.get(kind, 0) + 1
        if stage:
            by_stage[stage] = by_stage.get(stage, 0) + 1
        if role:
            by_problem_role[role] = by_problem_role.get(role, 0) + 1
    return {
        "total": len(artifact_refs),
        "by_kind": by_kind,
        "by_stage": by_stage,
        "by_problem_role": by_problem_role,
    }


def _derive_priority_views(artifact_refs: list[dict[str, Any]], current_state: str) -> list[dict[str, Any]]:
    by_kind = {item.get("artifact_kind"): item.get("artifact_id") for item in artifact_refs}
    views: list[dict[str, Any]] = []
    review_ids = [
        item["artifact_id"]
        for item in artifact_refs
        if item.get("artifact_kind") in {"clarification_packet", "draft"}
    ]
    if review_ids or current_state in {"CLARIFICATION_NEEDED", "CITADEL_REVIEW_LOOP", "PACKAGE_READY", "BRIDGE_CONSIDERATION"}:
        views.append({
            "view_id": "view_review",
            "title": "What Needs Review",
            "focus": "what_needs_review",
            "artifact_ids": review_ids,
            "signal": "clarification_needed" if "clarification_packet" in by_kind else "review_ready",
        })

    reusable_ids = [
        item["artifact_id"]
        for item in artifact_refs
        if item.get("artifact_kind") in {"finding", "classification"}
    ]
    if reusable_ids:
        views.append({
            "view_id": "view_reuse",
            "title": "Reusable Findings",
            "focus": "what_is_reusable",
            "artifact_ids": reusable_ids,
            "signal": "candidate_for_promotion",
        })
    return views


def _derive_mission_signals(artifact_refs: list[dict[str, Any]], current_state: str) -> list[dict[str, str]]:
    kinds = {str(item.get("artifact_kind") or "").strip() for item in artifact_refs}
    signals: list[dict[str, str]] = []
    if "clarification_packet" in kinds or current_state == "CLARIFICATION_NEEDED":
        signals.append({
            "signal": "clarification_needed",
            "impact": "high",
            "reason": "The mission still needs missing context or operator review.",
        })
    if "draft" in kinds:
        signals.append({
            "signal": "code_generated",
            "impact": "medium",
            "reason": "The mission produced a draft artifact that can be reviewed manually.",
        })
    if {"finding", "classification"} & kinds:
        signals.append({
            "signal": "candidate_for_promotion",
            "impact": "medium",
            "reason": "The mission produced reusable analytical material.",
        })
    if current_state in {"PACKAGE_READY", "BRIDGE_CONSIDERATION"}:
        signals.append({
            "signal": "review_ready",
            "impact": "medium",
            "reason": "The mission is ready for operator review.",
        })
    return signals


def _derive_open_questions(artifact_refs: list[dict[str, Any]]) -> list[dict[str, str]]:
    kinds = {str(item.get("artifact_kind") or "").strip() for item in artifact_refs}
    questions: list[dict[str, str]] = []
    if "clarification_packet" in kinds:
        questions.append({
            "question": "Which missing context should be supplied before the next run?",
            "impact": "high",
            "source": "clarification packet",
        })
    if "draft" in kinds:
        questions.append({
            "question": "Should the draft be reviewed and submitted or revised first?",
            "impact": "medium",
            "source": "draft",
        })
    if "finding" in kinds and "classification" not in kinds:
        questions.append({
            "question": "Which findings should be promoted into a classification record?",
            "impact": "medium",
            "source": "finding",
        })
    return questions


def _derive_recommended_next_step(status: str, artifact_refs: list[dict[str, Any]]) -> str:
    kinds = {str(item.get("artifact_kind") or "").strip() for item in artifact_refs}
    if "clarification_packet" in kinds or status == "needs_review":
        return "clarify"
    if "draft" in kinds or status == "ready_for_review":
        return "review"
    if {"finding", "classification"} & kinds:
        return "classify"
    if status == "complete":
        return "archive"
    return "none"


def _derive_summary(mission_id: str, task_text: str, total: int, status: str, signal_count: int) -> str:
    task_clause = f"for '{task_text}'" if task_text else "with no mission brief"
    return f"Mission {mission_id} {task_clause} produced {total} artifacts, status {status}, and {signal_count} signal(s)."


def build_mission_manifest(mission_id: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    index = read_artifact_index(mission)
    items = list(index.get("items") or [])
    brief = read_mission_brief(mission)
    state = read_state(mission)

    latest_run_id = ""
    if isinstance(brief, dict):
        latest_run_id = _text(brief.get("latest_run_id"))
    if not latest_run_id:
        latest_run_id = _latest_hermes_run_id(items)

    artifact_refs: list[dict[str, Any]] = []
    for item in items:
        kind = _text(item.get("kind"))
        path = _text(item.get("path"))
        created_at = _text(item.get("created_at"))
        if not kind or not path or not created_at:
            continue
        artifact_refs.append({
            "artifact_id": _artifact_id(kind, path, created_at),
            "artifact_kind": kind,
            "artifact_stage": _artifact_meta(kind)["artifact_stage"],
            "problem_role": _artifact_meta(kind)["problem_role"],
            "quality_signal": _artifact_meta(kind)["quality_signal"],
            "reusability_class": _artifact_meta(kind)["reusability_class"],
            "path": path,
        })

    status = _derive_status(_text(state.get("current_state")), artifact_refs)
    signals = _derive_mission_signals(artifact_refs, _text(state.get("current_state")))
    task_text = _text(brief.get("task_text")) if isinstance(brief, dict) else ""
    summary = _derive_summary(mission, task_text, len(artifact_refs), status, len(signals))
    created_at = _created_at_seed(_load_json(mission_manifest_path(mission)), brief, items)
    updated_at = iso_now()

    manifest_seed = f"{mission}|{latest_run_id}|{updated_at}|{len(artifact_refs)}"
    manifest_id = f"manifest_{mission}_{latest_run_id or 'no_run'}_{_short_digest(manifest_seed)}"

    manifest = {
        "manifest_id": manifest_id,
        "mission_id": mission,
        "run_id": latest_run_id,
        "status": status,
        "summary": summary,
        "artifact_counts": _derive_counts(artifact_refs),
        "artifact_refs": artifact_refs,
        "priority_views": _derive_priority_views(artifact_refs, _text(state.get("current_state"))),
        "mission_signals": signals,
        "open_questions": _derive_open_questions(artifact_refs),
        "recommended_next_step": _derive_recommended_next_step(status, artifact_refs),
        "created_at": created_at,
        "updated_at": updated_at,
    }
    return manifest


def write_mission_manifest(mission_id: str) -> tuple[Path, dict[str, Any]]:
    mission = normalize_mission_id(mission_id)
    path = mission_manifest_path(mission)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_mission_manifest(mission)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh a mission-local artifact manifest from artifact_index.json.")
    parser.add_argument("mission_id", help="Mission container ID")
    args = parser.parse_args()
    path, _ = write_mission_manifest(args.mission_id)
    print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
