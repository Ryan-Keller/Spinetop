from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

import dashboard_api
import governance_utils
import state_machine


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _snapshot(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(p for p in root.rglob("*") if p.is_file())
    }


@contextmanager
def _patched_roots(temp_root: Path):
    expedition_root = temp_root / "expeditions" / "active"
    workbench_root = temp_root / "workbench" / "missions"
    support_orch_root = temp_root / "logs" / "support" / "orchestration"
    support_retrieval_root = temp_root / "logs" / "support" / "retrieval"
    memory_root = temp_root / "memory"
    governance_root = temp_root / "logs" / "governance"
    nanny_status_path = temp_root / "logs" / "nanny" / "item_world_status.json"
    patches = [
        (state_machine, "ROOT", temp_root),
        (state_machine, "EXPEDITIONS_ACTIVE_DIR", expedition_root),
        (dashboard_api, "ROOT", temp_root),
        (dashboard_api, "EXPEDITIONS_ACTIVE_DIR", expedition_root),
        (dashboard_api, "WORKBENCH_MISSIONS_DIR", workbench_root),
        (dashboard_api, "SUPPORT_ORCHESTRATION_DIR", support_orch_root),
        (dashboard_api, "SUPPORT_RETRIEVAL_DIR", support_retrieval_root),
        (dashboard_api, "SUPPORT_ORCHESTRATION_INSTANCES_DIR", support_orch_root / "instances"),
        (dashboard_api, "SUPPORT_RETRIEVAL_INSTANCES_DIR", support_retrieval_root / "instances"),
        (dashboard_api, "HERMES_RUNS_DIR", temp_root / "logs" / "hermes" / "runs"),
        (dashboard_api, "CLARIFICATION_PACKETS_DIR", temp_root / "logs" / "citadel" / "clarification_packets"),
        (dashboard_api, "MEMORY_DIR", memory_root),
        (dashboard_api, "DISPATCH_DIR", memory_root / "dispatch"),
        (dashboard_api, "GOVERNANCE_DIR", governance_root),
        (dashboard_api, "COMPACTOR_LOG_DIR", temp_root / "logs" / "compactor"),
        (dashboard_api, "ARCHIVE_DIR", memory_root / "archive"),
        (dashboard_api, "COMPACTED_DIR", memory_root / "compacted"),
        (dashboard_api, "PROMOTION_DIR", memory_root / "promotion"),
        (dashboard_api, "INBOX_DIR", memory_root / "inbox"),
        (dashboard_api, "EVENT_LOG", temp_root / "logs" / "topology" / "events.jsonl"),
        (governance_utils, "ROOT", temp_root),
        (governance_utils, "GOVERNANCE_DIR", governance_root),
        (governance_utils, "NANNY_STATUS_PATH", nanny_status_path),
        (governance_utils, "DISPATCH_DIR", memory_root / "dispatch"),
    ]
    originals = [(module, name, getattr(module, name)) for module, name, _ in patches]
    try:
        for module, name, value in patches:
            setattr(module, name, value)
        yield
    finally:
        for module, name, value in originals:
            setattr(module, name, value)


def _seed_mission(
    root: Path,
    mission_id: str,
    *,
    objective: str,
    current_state: str = "CLARIFICATION_NEEDED",
    created_at: str = "2026-03-20T12:00:00+00:00",
    updated_at: str = "2026-03-20T12:00:00+00:00",
    operating_status: str = "blocked",
    can_continue_without_input: bool = False,
    blocked_reason: str = "Need operator input before proceeding.",
    parked: bool = False,
    parked_at: str = "",
) -> None:
    expedition_root = root / "expeditions" / "active" / mission_id
    notes_root = root / "workbench" / "missions" / mission_id / "notes"
    _write_json(
        expedition_root / "state.json",
        {"mission_id": mission_id, "current_state": current_state, "updated_at": updated_at},
    )
    _write_json(
        expedition_root / "mission_brief.json",
        {
            "mission_id": mission_id,
            "objective": objective,
            "task_text": objective,
            "created_at": created_at,
            "status": "active",
            "latest_run_id": "",
        },
    )
    _write_json(expedition_root / "artifact_index.json", {"mission_id": mission_id, "items": []})
    _write_json(
        expedition_root / "working_memory.json",
        {
            "mission_id": mission_id,
            "latest_summary": f"Summary for {mission_id}",
            "confirmed_facts": [],
            "open_questions": [],
            "deferred_questions": [],
            "updated_at": updated_at,
            "operating_status": operating_status,
            "blocked_reason": blocked_reason,
            "can_continue_without_input": can_continue_without_input,
            "crew_status": "recalled" if parked else "active",
            "expedition_activity": "paused" if parked else "running",
            "last_operator_reply_at": updated_at,
        },
    )
    _write_json(
        notes_root / "parking_status.json",
        {
            "mission_id": mission_id,
            "status": "parked" if parked else "active",
            "reason": "parked for hygiene review" if parked else "",
            "parked_at": parked_at,
            "parked_by": "operator" if parked else "",
            "resume_hint": "resume if new evidence arrives" if parked else "",
            "updated_at": parked_at or updated_at,
        },
    )


def _test_queue_classification_and_summary() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="queue_hygiene_"))
    with _patched_roots(temp_root):
        _seed_mission(
            temp_root,
            "mission_alpha_primary",
            objective="Investigate release regression",
            current_state="EXPEDITION_ACTIVE",
            created_at="2026-04-04T12:00:00+00:00",
            updated_at="2026-04-05T11:00:00+00:00",
            operating_status="proceeding_with_assumptions",
            can_continue_without_input=True,
            blocked_reason="",
        )
        _seed_mission(
            temp_root,
            "mission_alpha_old",
            objective="Investigate release regression",
            created_at="2026-03-01T12:00:00+00:00",
            updated_at="2026-03-05T12:00:00+00:00",
        )
        _seed_mission(
            temp_root,
            "mission_parked_old",
            objective="Temporary smoke validation",
            current_state="MISSION_CLOSED",
            created_at="2026-03-01T12:00:00+00:00",
            updated_at="2026-03-10T12:00:00+00:00",
            operating_status="idle",
            can_continue_without_input=True,
            blocked_reason="",
            parked=True,
            parked_at="2026-03-10T12:00:00+00:00",
        )
        _seed_mission(
            temp_root,
            "mission_review_ready",
            objective="Package the review draft",
            current_state="PACKAGE_READY",
            created_at="2026-04-04T12:00:00+00:00",
            updated_at="2026-04-05T09:30:00+00:00",
            operating_status="ready_for_review",
            can_continue_without_input=True,
            blocked_reason="",
        )

        items, grouped_counts = dashboard_api._list_expeditions()
        by_id = {item["mission_id"]: item for item in items}
        queue_summary = grouped_counts.get("queue_summary") if isinstance(grouped_counts, dict) else {}

        _assert(queue_summary.get("total_queued") == 4, f"expected four queued missions: {queue_summary}")
        _assert(queue_summary.get("duplicate_candidates") == 1, f"expected one duplicate follower: {queue_summary}")
        _assert(queue_summary.get("stale_candidates") >= 2, f"expected stale candidates to surface: {queue_summary}")
        _assert(queue_summary.get("review_ready") == 1, f"expected one review-ready mission: {queue_summary}")
        _assert(queue_summary.get("archive_close_candidates") == 2, f"expected archive candidates to surface: {queue_summary}")

        duplicate_item = by_id["mission_alpha_old"]
        duplicate_hygiene = duplicate_item.get("queue_hygiene") if isinstance(duplicate_item.get("queue_hygiene"), dict) else {}
        _assert(duplicate_hygiene.get("duplicate_candidate") is True, f"duplicate should be classified: {duplicate_item}")
        _assert(duplicate_hygiene.get("superseded_by_newer_similar") is True, f"older duplicate should be superseded: {duplicate_item}")
        _assert(duplicate_hygiene.get("recommended_action") == "archive candidate", f"older duplicate should be archive candidate: {duplicate_item}")

        parked_item = by_id["mission_parked_old"]
        parked_hygiene = parked_item.get("queue_hygiene") if isinstance(parked_item.get("queue_hygiene"), dict) else {}
        _assert(parked_hygiene.get("archive_candidate") is True, f"long-parked mission should be archive candidate: {parked_item}")
        _assert(parked_hygiene.get("junk_pattern") is True, f"test-like objective should be detected: {parked_item}")

        review_item = by_id["mission_review_ready"]
        _assert(review_item.get("recommended_queue_action") == "inspect before action", f"review-ready missions should not be auto-parked: {review_item}")


def _test_parked_missions_do_not_affect_active_duplicate_grouping() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="queue_hygiene_parked_isolation_"))
    with _patched_roots(temp_root):
        _seed_mission(
            temp_root,
            "mission_active_primary",
            objective="Prepare ship checklist",
            current_state="EXPEDITION_ACTIVE",
            created_at="2026-04-05T10:00:00+00:00",
            updated_at="2026-04-05T10:00:00+00:00",
            operating_status="proceeding_with_assumptions",
            can_continue_without_input=True,
            blocked_reason="",
        )
        _seed_mission(
            temp_root,
            "mission_parked_same_objective",
            objective="Prepare ship checklist",
            current_state="MISSION_CLOSED",
            created_at="2026-04-01T10:00:00+00:00",
            updated_at="2026-04-04T10:00:00+00:00",
            operating_status="idle",
            can_continue_without_input=True,
            blocked_reason="",
            parked=True,
            parked_at="2026-04-04T10:00:00+00:00",
        )

        items, _ = dashboard_api._list_expeditions()
        by_id = {item["mission_id"]: item for item in items}
        active_item = by_id["mission_active_primary"]
        parked_item = by_id["mission_parked_same_objective"]

        _assert(active_item.get("duplicate_count") == 1, f"active mission should ignore parked duplicate grouping: {active_item}")
        _assert(active_item.get("is_duplicate_candidate") is False, f"active mission should not be marked duplicate by parked mission: {active_item}")
        _assert(parked_item.get("duplicate_count") == 1, f"parked mission should stay isolated from active duplicate grouping: {parked_item}")
    return None


def _test_expeditions_list_is_read_only() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="queue_hygiene_read_only_"))
    with _patched_roots(temp_root):
        _seed_mission(
            temp_root,
            "mission_read_only",
            objective="Investigate release regression",
            current_state="EXPEDITION_ACTIVE",
            created_at="2026-04-04T12:00:00+00:00",
            updated_at="2026-04-05T11:00:00+00:00",
            operating_status="proceeding_with_assumptions",
            can_continue_without_input=True,
            blocked_reason="",
        )
        dashboard_api.app.config["TESTING"] = True
        before = _snapshot(temp_root)
        with dashboard_api.app.test_client() as client:
            response = client.get("/api/expeditions")
        after = _snapshot(temp_root)
        body = response.get_json(silent=True) or {}

        _assert(response.status_code == 200, f"list GET should succeed: {response.status_code} {body}")
        _assert(body.get("ok") is True, f"list GET should return ok payload: {body}")
        _assert(before == after, "queue list GET must not mutate expedition or workbench files")


def _test_mark_archive_candidate_stays_mission_local() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="queue_hygiene_archive_"))
    mission_id = "mission_archive_candidate"
    with _patched_roots(temp_root):
        _seed_mission(
            temp_root,
            mission_id,
            objective="Temporary smoke validation",
            current_state="MISSION_CLOSED",
            created_at="2026-03-01T12:00:00+00:00",
            updated_at="2026-03-10T12:00:00+00:00",
            operating_status="idle",
            can_continue_without_input=True,
            blocked_reason="",
            parked=True,
            parked_at="2026-03-10T12:00:00+00:00",
        )
        dashboard_api.app.config["TESTING"] = True
        with dashboard_api.app.test_client() as client:
            response = client.post(
                f"/api/expeditions/{mission_id}/interventions",
                json={"action": "mark_archive_candidate"},
            )
        body = response.get_json(silent=True) or {}
        item = body.get("item") if isinstance(body.get("item"), dict) else {}
        intervention = body.get("intervention") if isinstance(body.get("intervention"), dict) else {}
        changed_paths = set(str(path) for path in intervention.get("changed_paths", []))

        _assert(response.status_code == 200, f"archive candidate action should succeed: {response.status_code} {body}")
        _assert(body.get("ok") is True, f"archive candidate action should be ok: {body}")
        _assert("workbench/missions/mission_archive_candidate/notes/interventions/archive_candidate.json" in changed_paths, f"marker path missing: {changed_paths}")
        _assert("memory/collective/" not in " ".join(changed_paths), f"archive candidate action must not touch truth lanes: {changed_paths}")
        _assert(item.get("queue_hygiene", {}).get("archive_candidate") is True, f"archive candidate classification should remain visible: {item}")


def main() -> int:
    _test_queue_classification_and_summary()
    _test_parked_missions_do_not_affect_active_duplicate_grouping()
    _test_expeditions_list_is_read_only()
    _test_mark_archive_candidate_stays_mission_local()
    print("expedition queue hygiene smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
