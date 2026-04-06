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


def _file_snapshot(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    snapshot: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        snapshot[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return snapshot


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


def _seed_expedition_state(
    root: Path,
    mission_id: str,
    *,
    objective: str,
    parked: bool = False,
    retry_used: int = 0,
    retry_total: int = 2,
) -> None:
    expedition_root = root / "expeditions" / "active" / mission_id
    notes_root = root / "workbench" / "missions" / mission_id / "notes"
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
            "expedition_activity": "paused" if parked else "running",
        },
    )
    _write_json(
        notes_root / "parking_status.json",
        {
            "mission_id": mission_id,
            "status": "parked" if parked else "active",
            "reason": "parked for operator review" if parked else "",
            "parked_at": "2026-04-05T12:00:30+00:00" if parked else "",
            "parked_by": "operator" if parked else "",
            "resume_hint": "resume after operator review" if parked else "",
            "updated_at": "2026-04-05T12:00:30+00:00",
        },
    )
    _write_json(
        notes_root / "retries.json",
        {
            "mission_id": mission_id,
            "retry_budget_total": retry_total,
            "retry_budget_used": retry_used,
            "last_retry_at": "2026-04-05T12:01:30+00:00" if retry_used else "",
            "last_failure_reason": "replacement helper returned the same failure" if retry_used else "",
            "retry_reasons": ["bounded refresh after helper returned partial evidence"] if retry_used else [],
            "stop_reason": "retry_budget_exhausted" if retry_used >= retry_total else "",
            "decision_log": [
                {
                    "decided_at": "2026-04-05T12:01:30+00:00",
                    "decision": "blocked",
                    "retry_reason": "bounded refresh after helper returned partial evidence",
                    "why_blocked": "blocked by exhausted retry budget",
                    "budget_total": retry_total,
                    "budget_used_before": retry_used,
                    "budget_used_after": retry_used,
                    "stop_condition": "retry_budget_exhausted",
                }
            ]
            if retry_used
            else [],
            "updated_at": "2026-04-05T12:01:30+00:00",
            "derived_only": True,
        },
    )
    _write_json(
        notes_root / "runner_returns" / "runner_001.json",
        {
            "mission_id": mission_id,
            "instance_id": "runner_001",
            "helper_type": "runner_helper_2b",
            "created_at": "2026-04-05T12:01:20+00:00",
            "summary": "Runner helper suggests a retry after reviewing the partial receipt.",
            "recommended_next_step": "retry with a narrower bounded helper pass",
            "derived_only": True,
            "path": f"workbench/missions/{mission_id}/notes/runner_returns/runner_001.json",
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


def _assert_only_allowed_surfaces(changed_paths: set[str], mission_id: str) -> None:
    allowed_prefixes = {
        f"workbench/missions/{mission_id}/notes/",
        "logs/topology/events.jsonl",
    }
    for path in changed_paths:
        _assert(any(path.startswith(prefix) for prefix in allowed_prefixes), f"unexpected write surface: {path}")
        _assert(not path.startswith("memory/collective/"), f"intervention wrote to collective: {path}")
        _assert(not path.startswith("memory/dispatch/approved/"), f"intervention wrote to dispatch approved: {path}")


def _seed_unsynced_runner_helper(root: Path, mission_id: str, *, instance_id: str = "runner_helper_unsynced_001") -> str:
    _write_json(
        root / "logs" / "support" / "orchestration" / "instances" / f"{instance_id}.json",
        {
            "helper_id": instance_id,
            "helper_type": "runner_helper_2b",
            "mission_id": mission_id,
            "created_at": "2026-04-05T12:05:00+00:00",
            "updated_at": "2026-04-05T12:05:02+00:00",
            "expires_at": "2026-04-05T12:25:00+00:00",
            "mandate_id": "mission_runner_mandate",
            "task_scope": "prepare a bounded mission receipt",
            "write_scope": ["logs/support/orchestration/", "logs/support/runs/"],
            "status": "complete",
            "requested_by": "mission_scout",
            "request_type": "spawn",
            "ttl_seconds": 1200,
            "return_lane": "logs/support/orchestration/",
            "task_plan": ["capture the helper outcome", "return the compact receipt"],
            "task_plan_count": 2,
            "note": "runner completed bounded task",
        },
    )
    _write_json(
        root / "logs" / "support" / "orchestration" / "artifacts" / f"{instance_id}.json",
        {
            "helper_id": instance_id,
            "helper_type": "runner_helper_2b",
            "status": "complete",
            "updated_at": "2026-04-05T12:05:02+00:00",
            "outputs_refs": [f"logs/support/runs/{instance_id}.json"],
        },
    )
    _write_json(
        root / "logs" / "support" / "runs" / f"{instance_id}.json",
        {
            "helper_id": instance_id,
            "mission_id": mission_id,
            "helper_type": "runner_helper_2b",
            "mandate_id": "mission_runner_mandate",
            "task_scope": "prepare a bounded mission receipt",
            "requested_by": "mission_scout",
            "created_at": "2026-04-05T12:05:00+00:00",
            "completed_at": "2026-04-05T12:05:02+00:00",
            "status": "complete",
            "reason": "completed 2 step(s)",
            "task_plan": ["capture the helper outcome", "return the compact receipt"],
            "step_transcript": [
                {"step_index": 1, "step": "capture the helper outcome", "status": "complete", "note": "step completed"},
                {"step_index": 2, "step": "return the compact receipt", "status": "complete", "note": "step completed"},
            ],
            "task_result": {"summary": "completed 2 step(s)", "step_count": 2},
            "outputs_refs": [f"logs/support/runs/{instance_id}.json"],
            "return_lane": "logs/support/orchestration/",
            "write_scope": ["logs/support/orchestration/", "logs/support/runs/"],
        },
    )
    return f"workbench/missions/{mission_id}/notes/runner_returns/{instance_id}.json"


def _test_allowed_resume_intervention() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="control_tower_resume_"))
    mission_id = "mission_resume_intervention"
    with _patched_roots(temp_root):
        _seed_expedition_state(temp_root, mission_id, objective="Resume a parked mission", parked=True)
        client = dashboard_api.app.test_client()

        before = _file_snapshot(temp_root)
        response = client.post(f"/api/expeditions/{mission_id}/interventions", json={"action": "resume_mission"})
        payload = response.get_json(silent=True) or {}
        after = _file_snapshot(temp_root)
        changed = {path for path in after if before.get(path) != after.get(path)}

        _assert(response.status_code == 200, f"resume intervention failed: {response.status_code} {payload}")
        _assert(payload.get("ok") is True, f"resume intervention should succeed: {payload}")
        intervention = payload.get("intervention") if isinstance(payload.get("intervention"), dict) else {}
        _assert(intervention.get("status") == "applied", f"resume intervention should be logged as applied: {payload}")
        item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
        parking_status = item.get("parking_status") if isinstance(item.get("parking_status"), dict) else {}
        _assert(parking_status.get("status") == "active", f"resume intervention should activate parking status: {payload}")
        _assert_only_allowed_surfaces(changed, mission_id)


def _test_blocked_retry_intervention() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="control_tower_retry_blocked_"))
    mission_id = "mission_retry_intervention"
    with _patched_roots(temp_root):
        _seed_expedition_state(
            temp_root,
            mission_id,
            objective="Retry should stay bounded when budget is exhausted",
            retry_used=2,
            retry_total=2,
        )
        client = dashboard_api.app.test_client()

        before = _file_snapshot(temp_root)
        response = client.post(
            f"/api/expeditions/{mission_id}/interventions",
            json={"action": "retry_bounded_action", "reason": "operator requested one more bounded retry"},
        )
        payload = response.get_json(silent=True) or {}
        after = _file_snapshot(temp_root)
        changed = {path for path in after if before.get(path) != after.get(path)}

        _assert(response.status_code == 409, f"blocked retry should return conflict: {response.status_code} {payload}")
        _assert(payload.get("ok") is False and payload.get("blocked") is True, f"blocked retry payload should be explicit: {payload}")
        _assert(payload.get("error") == "blocked by exhausted retry budget", f"blocked retry reason missing: {payload}")
        intervention = payload.get("intervention") if isinstance(payload.get("intervention"), dict) else {}
        _assert(intervention.get("status") == "blocked", f"blocked retry should be logged as blocked: {payload}")
        _assert_only_allowed_surfaces(changed, mission_id)


def _test_sync_helper_returns_logs_created_paths() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="control_tower_sync_helper_returns_"))
    mission_id = "mission_sync_helper_returns"
    with _patched_roots(temp_root):
        _seed_expedition_state(temp_root, mission_id, objective="Sync mission-local helper returns into notes")
        expected_runner_return_path = _seed_unsynced_runner_helper(temp_root, mission_id)
        client = dashboard_api.app.test_client()

        before = _file_snapshot(temp_root)
        response = client.post(
            f"/api/expeditions/{mission_id}/interventions",
            json={"action": "sync_helper_returns", "reason": "operator requested helper return sync"},
        )
        payload = response.get_json(silent=True) or {}
        after = _file_snapshot(temp_root)
        changed = {path for path in after if before.get(path) != after.get(path)}

        _assert(response.status_code == 200, f"sync helper returns should succeed: {response.status_code} {payload}")
        _assert(payload.get("ok") is True, f"sync helper returns payload should be ok: {payload}")
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        sync = result.get("sync") if isinstance(result.get("sync"), dict) else {}
        _assert(sync.get("created_count") == 1, f"sync should report one created packet: {payload}")
        _assert(sync.get("created_instance_ids") == ["runner_helper_unsynced_001"], f"created instance ids should match seeded helper: {payload}")
        created = sync.get("created") if isinstance(sync.get("created"), list) else []
        _assert(created == [{"instance_id": "runner_helper_unsynced_001", "path": expected_runner_return_path}], f"created payload should include instance id and path: {payload}")
        _assert(expected_runner_return_path in changed, f"sync should create runner return packet on disk: {changed}")
        intervention = payload.get("intervention") if isinstance(payload.get("intervention"), dict) else {}
        _assert(intervention.get("status") == "applied", f"sync helper returns should be logged as applied: {payload}")
        _assert(intervention.get("changed_paths") == [expected_runner_return_path], f"intervention log should record created runner return path: {payload}")
        log_rows = dashboard_api._read_operator_interventions(mission_id)
        _assert(log_rows and log_rows[0].get("changed_paths") == [expected_runner_return_path], f"persisted intervention log should record created runner return path: {log_rows}")
        _assert_only_allowed_surfaces(changed, mission_id)


def _test_refresh_assumptions_logs_ledger_path() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="control_tower_refresh_assumptions_"))
    mission_id = "mission_refresh_assumptions"
    with _patched_roots(temp_root):
        _seed_expedition_state(temp_root, mission_id, objective="Refresh mission-local assumptions")
        client = dashboard_api.app.test_client()

        before = _file_snapshot(temp_root)
        response = client.post(
            f"/api/expeditions/{mission_id}/interventions",
            json={"action": "refresh_assumptions", "reason": "operator requested assumption refresh"},
        )
        payload = response.get_json(silent=True) or {}
        after = _file_snapshot(temp_root)
        changed = {path for path in after if before.get(path) != after.get(path)}

        _assert(response.status_code == 200, f"refresh assumptions should succeed: {response.status_code} {payload}")
        _assert(payload.get("ok") is True, f"refresh assumptions payload should be ok: {payload}")
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        refresh = result.get("refresh") if isinstance(result.get("refresh"), dict) else {}
        ledger_path = str(refresh.get("ledger_path") or "").strip()
        _assert(bool(ledger_path), f"refresh assumptions should return ledger path: {payload}")
        _assert(ledger_path in changed, f"refresh assumptions should write the ledger on disk: {changed}")
        intervention = payload.get("intervention") if isinstance(payload.get("intervention"), dict) else {}
        _assert(intervention.get("status") == "applied", f"refresh assumptions should be logged as applied: {payload}")
        _assert(intervention.get("changed_paths") == [ledger_path], f"intervention log should record assumption ledger path: {payload}")
        log_rows = dashboard_api._read_operator_interventions(mission_id)
        _assert(log_rows and log_rows[0].get("changed_paths") == [ledger_path], f"persisted intervention log should record assumption ledger path: {log_rows}")
        _assert_only_allowed_surfaces(changed, mission_id)


def _test_clear_stale_handoff_is_mission_local() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="control_tower_clear_handoff_"))
    mission_id = "mission_clear_handoff"
    with _patched_roots(temp_root):
        _seed_expedition_state(temp_root, mission_id, objective="Clear a stale blocked handoff")
        client = dashboard_api.app.test_client()

        before = _file_snapshot(temp_root)
        response = client.post(
            f"/api/expeditions/{mission_id}/interventions",
            json={"action": "clear_stale_pending_handoff", "reason": "blocked handoff is stale after operator review"},
        )
        payload = response.get_json(silent=True) or {}
        after = _file_snapshot(temp_root)
        changed = {path for path in after if before.get(path) != after.get(path)}

        _assert(response.status_code == 200, f"clear handoff should succeed: {response.status_code} {payload}")
        _assert(payload.get("ok") is True, f"clear handoff payload should be ok: {payload}")
        handoff = ((payload.get("result") or {}) if isinstance(payload.get("result"), dict) else {}).get("handoff")
        _assert(isinstance(handoff, dict) and handoff.get("status") == "idle", f"handoff should be cleared back to idle: {payload}")
        _assert_only_allowed_surfaces(changed, mission_id)


def main() -> int:
    _test_allowed_resume_intervention()
    _test_blocked_retry_intervention()
    _test_sync_helper_returns_logs_created_paths()
    _test_refresh_assumptions_logs_ledger_path()
    _test_clear_stale_handoff_is_mission_local()
    print("control_tower_interventions_smoke_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
