from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

import dashboard_api
import governance_utils
import prompt_translator
import state_machine


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@contextmanager
def _patched_attr(module: object, name: str, value: object):
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


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
        (prompt_translator, "ROOT", temp_root),
        (prompt_translator, "WORKBENCH_MISSIONS_DIR", workbench_root),
    ]
    originals = [(module, name, getattr(module, name)) for module, name, _ in patches]
    try:
        for module, name, value in patches:
            setattr(module, name, value)
        yield
    finally:
        for module, name, value in originals:
            setattr(module, name, value)


def _seed_mission(root: Path, mission_id: str) -> None:
    expedition_root = root / "expeditions" / "active" / mission_id
    notes_root = root / "workbench" / "missions" / mission_id / "notes"
    _write_json(
        expedition_root / "state.json",
        {
            "mission_id": mission_id,
            "current_state": "CLARIFICATION_NEEDED",
            "updated_at": "2026-04-07T01:00:00+00:00",
        },
    )
    _write_json(
        expedition_root / "mission_brief.json",
        {
            "mission_id": mission_id,
            "objective": "Expose a minimal expedition read model",
            "task_text": "Expose a minimal expedition read model",
            "created_at": "2026-04-07T00:59:00+00:00",
            "latest_run_id": "",
        },
    )
    _write_json(expedition_root / "artifact_index.json", {"mission_id": mission_id, "items": []})
    _write_json(
        expedition_root / "working_memory.json",
        {
            "mission_id": mission_id,
            "latest_summary": "Waiting on one operator confirmation before continuing.",
            "confirmed_facts": [],
            "open_questions": [],
            "deferred_questions": [],
            "updated_at": "2026-04-07T01:01:00+00:00",
            "operating_status": "blocked",
            "blocked_reason": "Need the operator to confirm the next bounded step.",
            "can_continue_without_input": False,
            "crew_status": "active",
            "expedition_activity": "running",
        },
    )
    _write_json(
        notes_root / "agent_runs" / "agent_run_002.json",
        {
            "run_id": "agent_run_002",
            "artifact_kind": "agent_role_invocation",
            "role": "spinetop-mirror",
            "role_label": "Mirror",
            "mission_id": mission_id,
            "created_at": "2026-04-07T01:03:00+00:00",
            "trigger_reason": "explicit_role_invocation",
            "status": "success",
            "summary": "Mirror reviewed the last bounded artifact.",
            "next_step": "Compare the review with the previous run.",
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
            "created_at": "2026-04-07T01:02:00+00:00",
            "trigger_reason": "explicit_role_invocation",
            "status": "success",
            "summary": "Expeditioner produced a bounded first pass.",
            "next_step": "Review the first pass.",
        },
    )
    _write_json(
        notes_root / "triggers" / "trigger_002.json",
        {
            "trigger_id": "trigger_002",
            "mission_id": mission_id,
            "created_at": "2026-04-07T01:05:00+00:00",
            "trigger_kind": "operator_refresh_requested",
            "reason": "operator asked for a bounded refresh",
            "target_role": "spinetop_expeditioner",
            "allowed_action": "retry_expedition_refresh",
            "status": "blocked",
            "evaluation": {"blocked_reason": "blocked by exhausted retry budget"},
        },
    )
    _write_json(
        notes_root / "triggers" / "trigger_001.json",
        {
            "trigger_id": "trigger_001",
            "mission_id": mission_id,
            "created_at": "2026-04-07T01:04:00+00:00",
            "trigger_kind": "mission_resumed",
            "reason": "mission explicitly resumed",
            "target_role": "spinetop_expeditioner",
            "allowed_action": "resume_expedition",
            "status": "applied",
        },
    )
    _write_json(
        notes_root / "triggers" / "pending_handoff.json",
        {
            "mission_id": mission_id,
            "trigger_id": "trigger_002",
            "target_role": "spinetop_expeditioner",
            "allowed_action": "retry_expedition_refresh",
            "status": "blocked",
            "reason": "operator asked for a bounded refresh",
            "policy_basis": "operator_requested_refresh",
            "updated_at": "2026-04-07T01:05:10+00:00",
            "derived_only": True,
        },
    )
    interventions_path = notes_root / "interventions" / "log.jsonl"
    interventions_path.parent.mkdir(parents=True, exist_ok=True)
    interventions_path.write_text(
        json.dumps(
            {
                "intervention_id": "intervention_001",
                "mission_id": mission_id,
                "action": "sync helper returns",
                "status": "applied",
                "reason": "operator requested a fresh timeline view",
                "created_at": "2026-04-07T01:06:00+00:00",
                "changed_paths": [f"workbench/missions/{mission_id}/notes/runner_returns/runner_001.json"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _write_json(
        notes_root / "retries.json",
        {
            "mission_id": mission_id,
            "retry_budget_total": 2,
            "retry_budget_used": 2,
            "last_retry_at": "2026-04-07T01:05:30+00:00",
            "last_failure_reason": "replacement helper returned the same failure",
            "stop_reason": "retry_budget_exhausted",
            "decision_log": [
                {
                    "decided_at": "2026-04-07T01:05:30+00:00",
                    "decision": "blocked",
                    "retry_reason": "bounded refresh after helper returned partial evidence",
                    "why_blocked": "blocked by exhausted retry budget",
                }
            ],
            "derived_only": True,
        },
    )


def _test_state_endpoint() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="tier1_state_api_"))
    mission_id = "mission_tier1_state"
    with _patched_roots(temp_root):
        _seed_mission(temp_root, mission_id)
        dashboard_api.app.config["TESTING"] = True
        with dashboard_api.app.test_client() as client:
            response = client.get(f"/api/expeditions/{mission_id}/state")
        body = response.get_json(silent=True) or {}
        item = body.get("item") if isinstance(body.get("item"), dict) else {}

        _assert(response.status_code == 200, f"state endpoint should succeed: {response.status_code} {body}")
        _assert(set(item.keys()) == {
            "mission_id",
            "objective",
            "current_state",
            "operator_posture",
            "autonomy_state",
            "blocked_reason",
            "latest_meaningful_activity",
            "recommended_next_step",
        }, f"state endpoint should stay minimal: {item}")
        _assert(item.get("mission_id") == mission_id, f"state endpoint should preserve mission id: {item}")
        _assert(item.get("blocked_reason") is None, f"blocked reason should stay absent when the existing read model says the mission can proceed: {item}")
        latest_activity = item.get("latest_meaningful_activity") if isinstance(item.get("latest_meaningful_activity"), dict) else {}
        _assert(latest_activity.get("kind") == "trigger_handoff", f"latest activity should reuse the existing latest meaningful activity ordering: {latest_activity}")


def _test_timeline_endpoint() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="tier1_timeline_api_"))
    mission_id = "mission_tier1_timeline"
    with _patched_roots(temp_root):
        _seed_mission(temp_root, mission_id)
        dashboard_api.app.config["TESTING"] = True
        with dashboard_api.app.test_client() as client:
            response = client.get(f"/api/expeditions/{mission_id}/timeline")
        body = response.get_json(silent=True) or {}
        item = body.get("item") if isinstance(body.get("item"), dict) else {}

        _assert(response.status_code == 200, f"timeline endpoint should succeed: {response.status_code} {body}")
        _assert(item.get("mission_id") == mission_id, f"timeline should preserve mission id: {item}")
        recent_runs = list(item.get("recent_agent_runs") or [])
        recent_triggers = list(item.get("recent_triggers") or [])
        recent_interventions = list(item.get("recent_interventions") or [])
        _assert(len(recent_runs) == 2, f"timeline should return recent agent runs: {item}")
        _assert(recent_runs[0].get("run_id") == "agent_run_002", f"agent runs should stay ordered newest first: {recent_runs}")
        _assert(recent_triggers[0].get("trigger_id") == "trigger_002", f"triggers should stay ordered newest first: {recent_triggers}")
        _assert(recent_interventions[0].get("intervention_id") == "intervention_001", f"interventions should be exposed minimally: {recent_interventions}")
        retries = item.get("retries_summary") if isinstance(item.get("retries_summary"), dict) else {}
        _assert(retries.get("retry_budget_used") == 2, f"retry summary should reuse retry ledger: {retries}")
        artifact_refs = list(item.get("artifact_refs") or [])
        _assert(any(ref.get("artifact_ref") == f"workbench/missions/{mission_id}/notes/agent_runs/agent_run_002.json" for ref in artifact_refs), f"timeline should expose minimal artifact refs: {artifact_refs}")


def _test_invoke_role_endpoint_shape() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="tier1_invoke_role_api_"))
    mission_id = "mission_tier1_invoke_role"
    with _patched_roots(temp_root):
        _seed_mission(temp_root, mission_id)
        dashboard_api.app.config["TESTING"] = True

        def _fake_invoke_role(role_id: str, mission: str, input_payload: dict[str, object]) -> dict[str, object]:
            _assert(role_id == "spinetop-mirror", f"route should pass the requested role through: {role_id}")
            _assert(mission == mission_id, f"route should normalize and preserve mission id: {mission}")
            _assert(input_payload == {"trigger_reason": "api_smoke"}, f"route should preserve input payload: {input_payload}")
            return {
                "ok": True,
                "status": "success",
                "role": role_id,
                "mission_id": mission,
                "artifact_path": f"workbench/missions/{mission}/notes/agent_runs/agent_run_fake.json",
                "output": {
                    "role": role_id,
                    "mission_id": mission,
                    "result": "Mirror finished the bounded review.",
                    "confidence": 0.74,
                    "next_step": "Compare the review against the mission brief.",
                    "derived_only": True,
                },
                "record": {
                    "runtime_active": True,
                },
            }

        with _patched_attr(dashboard_api, "invoke_role", _fake_invoke_role):
            with dashboard_api.app.test_client() as client:
                response = client.post(
                    f"/api/expeditions/{mission_id}/invoke-role",
                    json={
                        "role_id": "spinetop-mirror",
                        "input_payload": {"trigger_reason": "api_smoke"},
                    },
                )
        body = response.get_json(silent=True) or {}

        _assert(response.status_code == 200, f"invoke-role endpoint should succeed: {response.status_code} {body}")
        _assert(set(body.keys()) == {"ok", "mission_id", "role", "status", "runtime_active", "artifact_path", "output"}, f"invoke-role response should stay minimal and consistent: {body}")
        _assert(body.get("runtime_active") is True, f"invoke-role should surface runtime activity at the top level: {body}")
        _assert(body.get("artifact_path") == f"workbench/missions/{mission_id}/notes/agent_runs/agent_run_fake.json", f"invoke-role should expose artifact path directly: {body}")
        _assert("invocation" not in body and "item" not in body, f"invoke-role should not return the full mission payload: {body}")


def main() -> int:
    _test_state_endpoint()
    _test_timeline_endpoint()
    _test_invoke_role_endpoint_shape()
    print("expedition_tier1_api_smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
