from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

import dashboard_api
import state_machine


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@contextmanager
def _patched_roots(temp_root: Path):
    expedition_root = temp_root / "expeditions" / "active"
    workbench_root = temp_root / "workbench" / "missions"
    support_orch_root = temp_root / "logs" / "support" / "orchestration"
    support_retrieval_root = temp_root / "logs" / "support" / "retrieval"
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
        (dashboard_api, "MEMORY_DIR", temp_root / "memory"),
        (dashboard_api, "DISPATCH_DIR", temp_root / "memory" / "dispatch"),
        (dashboard_api, "GOVERNANCE_DIR", temp_root / "logs" / "governance"),
        (dashboard_api, "COMPACTOR_LOG_DIR", temp_root / "logs" / "compactor"),
        (dashboard_api, "ARCHIVE_DIR", temp_root / "memory" / "archive"),
        (dashboard_api, "COMPACTED_DIR", temp_root / "memory" / "compacted"),
        (dashboard_api, "PROMOTION_DIR", temp_root / "memory" / "promotion"),
        (dashboard_api, "INBOX_DIR", temp_root / "memory" / "inbox"),
        (dashboard_api, "EVENT_LOG", temp_root / "logs" / "topology" / "events.jsonl"),
    ]
    originals = [(module, name, getattr(module, name)) for module, name, _ in patches]
    try:
        for module, name, value in patches:
            setattr(module, name, value)
        yield
    finally:
        for module, name, value in originals:
            setattr(module, name, value)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    mission_id = "mission_20260405T143900Z_smoke"
    temp_root = Path(tempfile.mkdtemp(prefix="runner_return_smoke_"))

    expedition_dir = temp_root / "expeditions" / "active" / mission_id
    workbench_dir = temp_root / "workbench" / "missions" / mission_id
    _write_json(
        expedition_dir / "mission_brief.json",
        {
            "mission_id": mission_id,
            "objective": "runner return smoke",
            "task_text": "runner return smoke",
            "created_at": "2026-04-05T14:39:00Z",
            "latest_run_id": "",
        },
    )
    _write_json(
        expedition_dir / "state.json",
        {
            "mission_id": mission_id,
            "current_state": "EXPEDITION_ACTIVE",
            "updated_at": "2026-04-05T14:39:00Z",
        },
    )
    _write_json(
        expedition_dir / "artifact_index.json",
        {
            "mission_id": mission_id,
            "items": [],
        },
    )
    (workbench_dir / "notes").mkdir(parents=True, exist_ok=True)
    (workbench_dir / "notes" / "chat.jsonl").write_text("", encoding="utf-8")

    retrieval_id = "retrieval_helper_2b_20260405T143901Z_abcd1234"
    _write_json(
        temp_root / "logs" / "support" / "retrieval" / "instances" / f"{retrieval_id}.json",
        {
            "helper_id": retrieval_id,
            "helper_type": "retrieval_helper_2b",
            "mission_id": mission_id,
            "mandate_id": "mission_retrieval_mandate",
            "task_scope": "retrieve mission-local references",
            "created_at": "2026-04-05T14:39:01Z",
            "expires_at": "2026-04-05T14:49:01Z",
            "write_scope": ["logs/support/retrieval/"],
            "status": "complete",
            "requested_by": "mission_scout",
            "ttl_seconds": 900,
            "return_lane": "logs/support/retrieval/",
            "query_scope": "mission-local references",
            "read_scope": ["docs"],
            "result_status": "complete",
            "outputs_refs": [f"logs/support/retrieval/{retrieval_id}_result.json"],
        },
    )
    _write_json(
        temp_root / "logs" / "support" / "retrieval" / f"{retrieval_id}_result.json",
        {
            "helper_id": retrieval_id,
            "mission_id": mission_id,
            "query_scope": "mission-local references",
            "evidence_refs": ["docs/support_orchestration_contract_v1.md#L1"],
            "result_status": "complete",
            "notes": ["matched:docs/support_orchestration_contract_v1.md:1"],
        },
    )

    runner_id = "runner_helper_2b_20260405T143902Z_dcba4321"
    _write_json(
        temp_root / "logs" / "support" / "orchestration" / "instances" / f"{runner_id}.json",
        {
            "helper_id": runner_id,
            "helper_type": "runner_helper_2b",
            "mission_id": mission_id,
            "created_at": "2026-04-05T14:39:02Z",
            "expires_at": "2026-04-05T14:59:02Z",
            "mandate_id": "mission_runner_mandate",
            "task_scope": "prepare a bounded mission receipt",
            "write_scope": ["logs/support/orchestration/", "logs/support/runs/"],
            "status": "complete",
            "requested_by": "mission_scout",
            "request_type": "spawn",
            "ttl_seconds": 1200,
            "return_lane": "logs/support/orchestration/",
            "replaced_helper_id": "",
            "replacement_reason": "",
            "task_plan": ["capture the helper outcome", "return the compact receipt"],
            "task_plan_count": 2,
            "updated_at": "2026-04-05T14:39:03Z",
            "note": "runner completed bounded task",
        },
    )
    _write_json(
        temp_root / "logs" / "support" / "orchestration" / "artifacts" / f"{runner_id}.json",
        {
            "helper_id": runner_id,
            "helper_type": "runner_helper_2b",
            "status": "complete",
            "updated_at": "2026-04-05T14:39:03Z",
            "note": "runner completed bounded task",
            "outputs_refs": [f"logs/support/runs/{runner_id}.json"],
        },
    )
    _write_json(
        temp_root / "logs" / "support" / "runs" / f"{runner_id}.json",
        {
            "helper_id": runner_id,
            "mission_id": mission_id,
            "helper_type": "runner_helper_2b",
            "mandate_id": "mission_runner_mandate",
            "task_scope": "prepare a bounded mission receipt",
            "requested_by": "mission_scout",
            "created_at": "2026-04-05T14:39:02Z",
            "completed_at": "2026-04-05T14:39:03Z",
            "status": "complete",
            "reason": "completed 2 step(s)",
            "task_plan": ["capture the helper outcome", "return the compact receipt"],
            "step_transcript": [
                {"step_index": 1, "step": "capture the helper outcome", "status": "complete", "note": "step completed"},
                {"step_index": 2, "step": "return the compact receipt", "status": "complete", "note": "step completed"},
            ],
            "task_result": {"summary": "completed 2 step(s)", "step_count": 2},
            "outputs_refs": [f"logs/support/runs/{runner_id}.json"],
            "return_lane": "logs/support/orchestration/",
            "write_scope": ["logs/support/orchestration/", "logs/support/runs/"],
        },
    )

    returns_dir = temp_root / "workbench" / "missions" / mission_id / "notes" / "runner_returns"
    with _patched_roots(temp_root):
        client = dashboard_api.app.test_client()

        get_before = client.get(f"/api/expeditions/{mission_id}")
        _assert(get_before.status_code == 200, f"mission detail GET failed with {get_before.status_code}")
        get_before_payload = get_before.get_json() or {}
        _assert(not returns_dir.exists() or not list(returns_dir.glob('*.json')), "GET should not create runner return packets")
        item_before = get_before_payload.get("item") if isinstance(get_before_payload, dict) else None
        _assert(isinstance(item_before, dict), "mission detail payload missing item before sync")
        _assert(item_before.get("latest_runner_return") is None, "latest_runner_return should be empty before explicit sync")
        _assert(item_before.get("runner_return_count") == 0, "runner_return_count should be 0 before explicit sync")

        sync_res = client.post(f"/api/expeditions/{mission_id}/sync-runner-returns")
        _assert(sync_res.status_code == 200, f"sync POST failed with {sync_res.status_code}")
        sync_payload = sync_res.get_json() or {}
        sync = sync_payload.get("sync") if isinstance(sync_payload, dict) else None
        _assert(isinstance(sync, dict), "sync payload missing sync result")
        _assert(sync.get("created_count") == 2, f"expected 2 created packets, got {sync.get('created_count')}")

        packets = sorted(returns_dir.glob("*.json"))
        _assert(len(packets) == 2, f"expected 2 runner return packets, found {len(packets)}")

        get_after = client.get(f"/api/expeditions/{mission_id}")
        _assert(get_after.status_code == 200, f"mission detail GET after sync failed with {get_after.status_code}")
        get_after_payload = get_after.get_json() or {}
        item_after = get_after_payload.get("item") if isinstance(get_after_payload, dict) else None
        _assert(isinstance(item_after, dict), "mission detail payload missing item after sync")
        _assert(item_after.get("runner_return_count") == 2, "runner_return_count did not reflect synced packets")

        latest = item_after.get("latest_runner_return")
        _assert(isinstance(latest, dict), "latest_runner_return missing from mission detail after sync")
        _assert(str(latest.get("instance_id") or "") == runner_id, "latest runner return should come from the newer runner helper")
        _assert("completed 2 step(s)" in str(latest.get("summary") or ""), "runner summary did not propagate")

    print("runner_return_smoke_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
