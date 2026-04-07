from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

import dashboard_api
import governance_utils
import item_world_nanny
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
    operator_learning_path = temp_root / "workbench" / "system" / "operator_learning" / "nanny_pattern_memory.json"
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
        (item_world_nanny, "ROOT", temp_root),
        (item_world_nanny, "EVENT_LOG", temp_root / "logs" / "topology" / "events.jsonl"),
        (item_world_nanny, "DISPATCH_DIR", memory_root / "dispatch"),
        (item_world_nanny, "STATUS_PATH", nanny_status_path),
        (item_world_nanny, "EXPEDITIONS_ACTIVE_DIR", expedition_root),
        (item_world_nanny, "WORKBENCH_MISSIONS_DIR", workbench_root),
        (item_world_nanny, "OPERATOR_LEARNING_PATH", operator_learning_path),
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
    updated_at: str,
    blocked_reason: str = "",
    open_questions: list[str] | None = None,
    blocking_questions: list[str] | None = None,
    can_continue_without_input: bool = False,
    parked: bool = False,
    retry_stop_conditions: list[str] | None = None,
    retry_budget_used: int = 0,
) -> None:
    expedition_root = root / "expeditions" / "active" / mission_id
    workbench_root = root / "workbench" / "missions" / mission_id
    notes_root = workbench_root / "notes"
    intake_root = workbench_root / "intake"
    _write_json(
        expedition_root / "state.json",
        {"mission_id": mission_id, "current_state": "EXPEDITION_ACTIVE", "updated_at": updated_at},
    )
    _write_json(
        expedition_root / "mission_brief.json",
        {
            "mission_id": mission_id,
            "objective": objective,
            "task_text": objective,
            "created_at": updated_at,
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
            "open_questions": open_questions or [],
            "blocking_questions": blocking_questions or [],
            "updated_at": updated_at,
            "operating_status": "blocked" if (blocked_reason or open_questions or blocking_questions) else "proceeding_with_assumptions",
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
            "reason": "parked for later review" if parked else "",
            "parked_at": updated_at if parked else "",
            "parked_by": "operator" if parked else "",
            "resume_hint": "resume when ready" if parked else "",
            "updated_at": updated_at,
        },
    )
    _write_json(
        notes_root / "retries.json",
        {
            "mission_id": mission_id,
            "retry_budget_used": retry_budget_used,
            "decision_log": [
                {
                    "status": "blocked",
                    "stop_condition": stop_condition,
                    "reason": f"stop because {stop_condition}",
                    "blocked_reason": f"blocked by {stop_condition}",
                }
                for stop_condition in (retry_stop_conditions or [])
            ],
        },
    )
    intake_root.mkdir(parents=True, exist_ok=True)


def _test_compute_status_detects_signals_without_mutation() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="nanny_signals_compute_"))
    with _patched_roots(temp_root):
        _seed_mission(
            temp_root,
            "mission_dup_primary",
            objective="Investigate release regression",
            updated_at="2026-04-05T10:00:00+00:00",
            can_continue_without_input=True,
        )
        _seed_mission(
            temp_root,
            "mission_dup_old",
            objective="Investigate release regression",
            updated_at="2026-03-20T10:00:00+00:00",
            blocked_reason="Need operator input before proceeding.",
            open_questions=["status?"],
        )
        _seed_mission(
            temp_root,
            "mission_junk",
            objective="Temporary smoke validation",
            updated_at="2026-03-15T10:00:00+00:00",
            blocked_reason="Need operator input before proceeding.",
            open_questions=["help?"],
        )
        _seed_mission(
            temp_root,
            "mission_retry_loop",
            objective="Recover helper output",
            updated_at="2026-04-05T09:30:00+00:00",
            blocked_reason="retry blocked by repeated failure",
            retry_stop_conditions=["repeated_same_failure_without_new_evidence", "exhausted_retry_budget"],
            retry_budget_used=2,
        )
        _seed_mission(
            temp_root,
            "mission_poor_intake",
            objective="Help",
            updated_at="2026-04-05T09:00:00+00:00",
            blocking_questions=["what next"],
        )
        _seed_mission(
            temp_root,
            "mission_parked_revival",
            objective="Prepare ship checklist",
            updated_at="2026-04-05T08:30:00+00:00",
            can_continue_without_input=True,
            parked=True,
        )

        before = _snapshot(temp_root)
        status = item_world_nanny.compute_status()
        after = _snapshot(temp_root)
        titles = {str(item.get("title") or "") for item in status.get("system_signals", []) if isinstance(item, dict)}

        _assert(before == after, "compute_status must stay read-only")
        _assert("Queue overloaded" in titles, f"queue pressure signal missing: {status}")
        _assert("Retry loop risk" in titles, f"retry loop signal missing: {status}")
        _assert("Poor intake quality" in titles, f"intake quality signal missing: {status}")
        _assert(
            "Repeated junk blockers detected" in titles or "Weak blocker questions detected" in titles,
            f"blocker quality signal missing: {status}",
        )
        _assert("Revive eligible missions" not in titles, f"parked missions should be excluded from system signals: {status}")
        _assert(
            "revive eligible missions" not in [str(action).lower() for action in status.get("recommended_actions", [])],
            f"parked missions should not drive recommended actions: {status}",
        )
        _assert(status.get("recommended_actions"), f"recommended actions should be present: {status}")


def _test_run_once_writes_learning_only_to_allowed_lane() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="nanny_signals_write_"))
    with _patched_roots(temp_root):
        _seed_mission(
            temp_root,
            "mission_writer",
            objective="Temporary smoke validation",
            updated_at="2026-03-15T10:00:00+00:00",
            blocked_reason="Need operator input before proceeding.",
            open_questions=["help?"],
        )
        item_world_nanny.run_once()

        status_path = temp_root / "logs" / "nanny" / "item_world_status.json"
        learning_path = temp_root / "workbench" / "system" / "operator_learning" / "nanny_pattern_memory.json"
        collective_root = temp_root / "memory" / "collective"

        _assert(status_path.exists(), "nanny status file should be written")
        _assert(learning_path.exists(), "operator learning summary should be written")
        _assert(not collective_root.exists(), "nanny must not write to collective memory")


def _test_api_status_is_read_only_and_surfaces_signals() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="nanny_signals_api_"))
    with _patched_roots(temp_root):
        _seed_mission(
            temp_root,
            "mission_api",
            objective="Help",
            updated_at="2026-04-05T09:00:00+00:00",
            blocking_questions=["what next"],
        )
        item_world_nanny.run_once()
        dashboard_api.app.config["TESTING"] = True

        before = _snapshot(temp_root)
        with dashboard_api.app.test_client() as client:
            response = client.get("/api/status")
        after = _snapshot(temp_root)
        body = response.get_json(silent=True) or {}
        nanny = body.get("nanny") if isinstance(body.get("nanny"), dict) else {}

        _assert(response.status_code == 200, f"status GET should succeed: {response.status_code} {body}")
        _assert(before == after, "api/status must not mutate backend state")
        _assert(isinstance(nanny.get("system_signals"), list), f"system signals should be exposed on api/status: {body}")


def main() -> int:
    _test_compute_status_detects_signals_without_mutation()
    _test_run_once_writes_learning_only_to_allowed_lane()
    _test_api_status_is_read_only_and_surfaces_signals()
    print("nanny system signals smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
