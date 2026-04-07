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


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_expedition_state(root: Path, mission_id: str, *, objective: str, working_memory: dict[str, object] | None = None) -> None:
    expedition_root = root / "expeditions" / "active" / mission_id
    _write_json(
        expedition_root / "state.json",
        {
            "mission_id": mission_id,
            "current_state": "CLARIFICATION_NEEDED",
            "updated_at": "2026-04-05T12:00:00+00:00",
        },
    )
    _write_json(
        expedition_root / "mission_brief.json",
        {
            "mission_id": mission_id,
            "objective": objective,
            "task_text": objective,
            "created_at": "2026-04-05T11:59:00+00:00",
            "status": "active",
            "latest_run_id": "",
        },
    )
    _write_json(expedition_root / "artifact_index.json", {"mission_id": mission_id, "items": []})
    _write_json(
        expedition_root / "working_memory.json",
        {
            "mission_id": mission_id,
            "latest_summary": "The mission is waiting on a bounded unblock path.",
            "confirmed_facts": [],
            "open_questions": [],
            "deferred_questions": [],
            "updated_at": "2026-04-05T12:01:00+00:00",
            "operating_status": "blocked",
            "blocked_reason": "Need the operator to confirm the blocker before proceeding.",
            "can_continue_without_input": False,
            "crew_status": "active",
            "expedition_activity": "running",
            **(working_memory or {}),
        },
    )


def _test_control_tower_summary() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="control_tower_summary_"))
    mission_id = "mission_control_tower"
    with _patched_roots(temp_root):
        _seed_expedition_state(temp_root, mission_id, objective="Summarize operator-facing control tower state")

        notes_root = temp_root / "workbench" / "missions" / mission_id / "notes"
        _write_json(
            notes_root / "triggers" / "trigger_001.json",
            {
                "trigger_id": "trigger_001",
                "mission_id": mission_id,
                "created_at": "2026-04-05T12:02:00+00:00",
                "trigger_kind": "operator_refresh_requested",
                "reason": "operator asked for one bounded refresh",
                "source": "operator",
                "target_role": "spinetop_expeditioner",
                "allowed_action": "retry_expedition_refresh",
                "policy_basis": "operator_requested_refresh",
                "status": "blocked",
                "derived_only": True,
                "evaluation": {
                    "allowed": False,
                    "blocked_reason": "blocked by exhausted retry budget",
                },
            },
        )
        _write_json(
            notes_root / "triggers" / "pending_handoff.json",
            {
                "mission_id": mission_id,
                "trigger_id": "trigger_001",
                "target_role": "spinetop_expeditioner",
                "allowed_action": "retry_expedition_refresh",
                "status": "blocked",
                "reason": "operator asked for one bounded refresh",
                "policy_basis": "operator_requested_refresh",
                "updated_at": "2026-04-05T12:02:05+00:00",
                "derived_only": True,
            },
        )
        _write_json(
            notes_root / "retries.json",
            {
                "mission_id": mission_id,
                "retry_budget_total": 2,
                "retry_budget_used": 2,
                "last_retry_at": "2026-04-05T12:01:30+00:00",
                "last_failure_reason": "replacement helper returned the same failure",
                "retry_reasons": ["bounded refresh after helper returned partial evidence"],
                "stop_reason": "retry_budget_exhausted",
                "decision_log": [
                    {
                        "decided_at": "2026-04-05T12:01:30+00:00",
                        "decision": "blocked",
                        "retry_reason": "bounded refresh after helper returned partial evidence",
                        "why_blocked": "blocked by exhausted retry budget",
                        "budget_total": 2,
                        "budget_used_before": 2,
                        "budget_used_after": 2,
                        "stop_condition": "retry_budget_exhausted",
                    }
                ],
                "updated_at": "2026-04-05T12:01:30+00:00",
                "derived_only": True,
            },
        )
        _write_json(
            notes_root / "assumptions" / "ledger.json",
            {
                "mission_id": mission_id,
                "derived_only": True,
                "updated_at": "2026-04-05T12:01:45+00:00",
                "entries": [
                    {
                        "assumption_id": "assumption_1",
                        "mission_id": mission_id,
                        "text": "The helper receipt is still current enough to reason about.",
                        "reason": "Carried forward until the operator confirms whether it is stale.",
                        "status": "active",
                        "created_at": "2026-04-05T12:01:40+00:00",
                        "updated_at": "2026-04-05T12:01:45+00:00",
                        "confirmation": {"operator_status": "unreviewed"},
                    }
                ],
            },
        )
        _write_json(
            notes_root / "runner_returns" / "runner_synced.json",
            {
                "mission_id": mission_id,
                "instance_id": "runner_synced",
                "helper_type": "runner_helper_2b",
                "created_at": "2026-04-05T12:01:20+00:00",
                "summary": "Runner helper suggests a retry after reviewing the partial receipt.",
                "open_questions": ["Should we try one more bounded refresh with a narrower scope?"],
                "recommended_next_step": "retry with a narrower bounded helper pass",
                "derived_only": True,
                "path": "workbench/missions/mission_control_tower/notes/runner_returns/runner_synced.json",
            },
        )
        _write_json(
            notes_root / "mirror" / "mirror_note_001.json",
            {
                "note_id": "mirror_note_001",
                "kind": "mirror_reflection",
                "role": "spinetop-mirror",
                "summary": "Mirror notes repeated blocker language across the latest helper receipts.",
                "created_at": "2026-04-05T12:03:00+00:00",
            },
        )
        _write_json(
            notes_root / "agent_runs" / "agent_run_001.json",
            {
                "run_id": "agent_run_001",
                "artifact_kind": "agent_role_invocation",
                "role": "spinetop_expeditioner",
                "role_label": "Expeditioner",
                "mission_id": mission_id,
                "created_at": "2026-04-05T12:00:30+00:00",
                "trigger_reason": "explicit_role_invocation",
                "status": "success",
                "summary": "Expeditioner completed a bounded manual pass.",
                "confidence": 0.81,
                "next_step": "Review the bounded result.",
                "derived_only": True,
            },
        )
        _write_json(
            notes_root / "agent_runs" / "agent_run_002.json",
            {
                "run_id": "agent_run_002",
                "artifact_kind": "agent_role_invocation",
                "role": "spinetop_mirror",
                "role_label": "Mirror",
                "mission_id": mission_id,
                "created_at": "2026-04-05T12:00:40+00:00",
                "trigger_reason": "explicit_role_invocation",
                "status": "success",
                "summary": "Mirror completed a bounded manual review.",
                "confidence": 0.78,
                "next_step": "Compare the review with the runner receipt.",
                "derived_only": True,
            },
        )

        retrieval_instance_id = "helper_unsynced"
        _write_json(
            temp_root / "logs" / "support" / "retrieval" / "instances" / f"{retrieval_instance_id}.json",
            {
                "helper_id": retrieval_instance_id,
                "helper_type": "retrieval_helper_2b",
                "mission_id": mission_id,
                "status": "partial",
                "query_scope": "latest blocker context",
                "outputs_refs": [f"logs/support/retrieval/{retrieval_instance_id}_result.json"],
            },
        )
        _write_json(
            temp_root / "logs" / "support" / "retrieval" / f"{retrieval_instance_id}_result.json",
            {
                "mission_id": mission_id,
                "result_status": "partial",
                "summary": "Partial retrieval output is ready to sync into the mission-local return lane.",
                "query_scope": "latest blocker context",
            },
        )

        detail = dashboard_api._build_expedition_detail(mission_id)
        summary = detail.get("control_tower_summary") if isinstance(detail.get("control_tower_summary"), dict) else {}
        actions = list(summary.get("safe_operator_actions") or [])
        visibility = summary.get("execution_visibility") if isinstance(summary.get("execution_visibility"), dict) else {}
        visibility_lines = list(visibility.get("summary_lines") or [])

        _assert(summary.get("autonomy_state") == "blocked", f"expected blocked autonomy state: {summary}")
        _assert(summary.get("retry_budget") == 2, f"retry budget should surface: {summary}")
        _assert(summary.get("retry_used") == 2, f"retry used should surface: {summary}")
        _assert(summary.get("last_retry_reason") == "bounded refresh after helper returned partial evidence", f"last retry reason missing: {summary}")
        _assert(summary.get("last_blocked_reason") == "blocked by exhausted retry budget", f"last blocked reason missing: {summary}")
        _assert(isinstance(summary.get("active_role_handoff"), dict), f"active handoff should be present: {summary}")
        _assert((summary.get("active_role_handoff") or {}).get("allowed_action") == "retry_expedition_refresh", f"expected retry handoff: {summary}")
        _assert((summary.get("latest_role_activity") or {}).get("kind") == "mirror_note", f"latest role activity should prefer newest mirror note: {summary}")
        _assert(summary.get("operator_attention_reason") == "blocked by exhausted retry budget", f"operator attention reason should be readable: {summary}")
        _assert(visibility.get("recent_runs_window") == 10, f"recent run window should be capped and visible: {visibility}")
        _assert(visibility.get("active_execution_now") is False, f"blocked handoff should not look like an active run: {visibility}")
        _assert(visibility.get("recent_successful_run_count") == 2, f"recent successful runs should be counted: {visibility}")
        _assert(visibility.get("recent_successful_manual_run_count") == 2, f"manual invoke successes should be counted separately: {visibility}")
        _assert(
            "No active runs right now." in visibility_lines,
            f"visibility lines should say when nothing is active: {visibility}",
        )
        _assert(
            "2 recent successful manual runs occurred (last 10 runs max)." in visibility_lines,
            f"visibility lines should mention successful manual runs: {visibility}",
        )
        _assert(
            "Latest successful role activity came from operator invoke-role (Mirror)." in visibility_lines,
            f"visibility lines should explain manual invoke provenance: {visibility}",
        )
        _assert(
            "Autonomy is blocked: blocked by exhausted retry budget." in visibility_lines,
            f"non-governance blocks should stay distinct from governance blocks: {visibility}",
        )
        _assert("refresh assumptions" in actions, f"assumptions refresh should be suggested: {summary}")
        _assert("sync helper returns" in actions, f"helper sync should be suggested when unsynced receipts exist: {summary}")
        _assert("answer blocker" in actions, f"blocked missions should suggest answering blocker: {summary}")
        _assert("inspect mirror note" in actions, f"mirror note inspection should be suggested: {summary}")


def _test_parked_mission_visibility() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="control_tower_parked_"))
    mission_id = "mission_parked_visibility"
    with _patched_roots(temp_root):
        _seed_expedition_state(
            temp_root,
            mission_id,
            objective="Show that autonomy is blocked by a parked mission",
            working_memory={
                "blocked_reason": "Mission is parked pending explicit operator resume.",
                "can_continue_without_input": False,
                "operator_posture": "parked",
            },
        )
        notes_root = temp_root / "workbench" / "missions" / mission_id / "notes"
        _write_json(
            notes_root / "parking_status.json",
            {
                "mission_id": mission_id,
                "status": "parked",
                "reason": "mission parked by operator while waiting on governance-safe review",
                "parked_at": "2026-04-05T12:04:00+00:00",
                "parked_by": "operator",
                "resume_hint": "Resume only when the operator wants autonomy reconsidered.",
                "updated_at": "2026-04-05T12:04:00+00:00",
            },
        )
        _write_json(
            notes_root / "agent_runs" / "agent_run_001.json",
            {
                "run_id": "agent_run_001",
                "artifact_kind": "agent_role_invocation",
                "role": "spinetop_expeditioner",
                "role_label": "Expeditioner",
                "mission_id": mission_id,
                "created_at": "2026-04-05T12:03:30+00:00",
                "trigger_reason": "explicit_role_invocation",
                "status": "success",
                "summary": "Expeditioner completed a manual checkpoint before parking.",
                "confidence": 0.82,
                "next_step": "Leave the mission parked until explicitly resumed.",
                "derived_only": True,
            },
        )

        detail = dashboard_api._build_expedition_detail(mission_id)
        summary = detail.get("control_tower_summary") if isinstance(detail.get("control_tower_summary"), dict) else {}
        visibility = summary.get("execution_visibility") if isinstance(summary.get("execution_visibility"), dict) else {}
        visibility_lines = list(visibility.get("summary_lines") or [])

        _assert(summary.get("autonomy_state") == "blocked", f"parked mission should block autonomy: {summary}")
        _assert(visibility.get("autonomy_governance_blocked") is True, f"parked mission should be treated as governance-blocked visibility: {visibility}")
        _assert(visibility.get("governance_block_reason") == "mission_parked", f"parked reason should be explicit: {visibility}")
        _assert(
            "Autonomy blocked because mission is parked." in visibility_lines,
            f"parked autonomy block should be called out plainly: {visibility}",
        )


def _test_get_detail_is_read_only() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="control_tower_read_only_"))
    mission_id = "mission_read_only"
    with _patched_roots(temp_root):
        _seed_expedition_state(
            temp_root,
            mission_id,
            objective="Ensure mission detail GET does not create workbench state",
            working_memory={"blocked_reason": "", "can_continue_without_input": True, "operating_status": "low_confidence_continue"},
        )
        dashboard_api.app.config["TESTING"] = True
        workbench_root = temp_root / "workbench" / "missions" / mission_id
        _assert(not workbench_root.exists(), "test setup should start without a workbench mission directory")

        with dashboard_api.app.test_client() as client:
            response = client.get(f"/api/expeditions/{mission_id}")
        body = response.get_json(silent=True) or {}

        _assert(response.status_code == 200, f"mission detail GET should succeed: {response.status_code} {body}")
        _assert(body.get("ok") is True, f"mission detail GET should return ok payload: {body}")
        _assert(not workbench_root.exists(), "mission detail GET must not create mission-local workbench folders")
        item = body.get("item") if isinstance(body.get("item"), dict) else {}
        summary = item.get("control_tower_summary") if isinstance(item.get("control_tower_summary"), dict) else {}
        _assert("safe_operator_actions" in summary, f"control tower summary should still be present on read-only GET: {item}")


def main() -> int:
    _test_control_tower_summary()
    _test_parked_mission_visibility()
    _test_get_detail_is_read_only()
    print("control tower summary smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
