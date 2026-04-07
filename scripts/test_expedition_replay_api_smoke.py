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
            "updated_at": "2026-04-07T02:00:00+00:00",
        },
    )
    _write_json(
        expedition_root / "mission_brief.json",
        {
            "mission_id": mission_id,
            "objective": "Replay mission-local truth without mutation",
            "task_text": "Replay mission-local truth without mutation",
            "created_at": "2026-04-07T01:59:00+00:00",
            "latest_run_id": "",
        },
    )
    _write_json(expedition_root / "artifact_index.json", {"mission_id": mission_id, "items": []})
    _write_json(
        expedition_root / "working_memory.json",
        {
            "mission_id": mission_id,
            "latest_summary": "Signals are blocked and contradictory but mission truth is stable.",
            "confirmed_facts": [],
            "open_questions": [],
            "deferred_questions": [],
            "updated_at": "2026-04-07T02:06:30+00:00",
            "operating_status": "blocked",
            "blocked_reason": "Need one operator clarification before the next bounded step.",
            "can_continue_without_input": False,
            "crew_status": "active",
            "expedition_activity": "running",
            "last_operator_reply_at": "2020-01-01T00:00:00+00:00",
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
            "created_at": "2026-04-07T02:01:00+00:00",
            "trigger_reason": "explicit_role_invocation",
            "status": "success",
            "summary": "Expeditioner produced the bounded first pass.",
            "next_step": "Review the first pass.",
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
            "created_at": "2026-04-07T02:02:00+00:00",
            "trigger_reason": "explicit_role_invocation",
            "status": "success",
            "summary": "Mirror reviewed the bounded first pass.",
            "next_step": "Inspect the contradiction note.",
        },
    )
    _write_json(
        notes_root / "triggers" / "trigger_001.json",
        {
            "trigger_id": "trigger_001",
            "mission_id": mission_id,
            "created_at": "2026-04-07T02:03:00+00:00",
            "trigger_kind": "mission_resumed",
            "reason": "mission explicitly resumed",
            "target_role": "spinetop_expeditioner",
            "allowed_action": "resume_expedition",
            "status": "applied",
        },
    )
    _write_json(
        notes_root / "triggers" / "trigger_002.json",
        {
            "trigger_id": "trigger_002",
            "mission_id": mission_id,
            "created_at": "2026-04-07T02:04:00+00:00",
            "trigger_kind": "operator_refresh_requested",
            "reason": "operator requested one bounded refresh",
            "target_role": "spinetop_expeditioner",
            "allowed_action": "retry_expedition_refresh",
            "status": "blocked",
            "evaluation": {"blocked_reason": "blocked by exhausted retry budget"},
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
            "reason": "operator requested one bounded refresh",
            "policy_basis": "operator_requested_refresh",
            "updated_at": "2026-04-07T02:04:10+00:00",
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
                "created_at": "2026-04-07T02:05:00+00:00",
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
            "last_retry_at": "2026-04-07T02:04:30+00:00",
            "last_failure_reason": "replacement helper returned the same failure",
            "stop_reason": "retry_budget_exhausted",
            "decision_log": [
                {
                    "decided_at": "2026-04-07T02:04:30+00:00",
                    "decision": "blocked",
                    "retry_reason": "bounded refresh after helper returned partial evidence",
                    "why_blocked": "blocked by exhausted retry budget",
                }
            ],
            "updated_at": "2026-04-07T02:04:30+00:00",
            "derived_only": True,
        },
    )
    _write_json(
        notes_root / "mirror" / "mirror_reflection_001.json",
        {
            "role": "spinetop-mirror",
            "kind": "mirror_reflection",
            "summary": "Control signals reverse faster than the mission context stabilizes.",
            "patterns": [
                "Repeated signals outweigh explanation in the recent mission trace."
            ],
            "contradictions": [
                "Operator control signals alternate between proceed and pause across adjacent artifacts."
            ],
            "suggested_focus": [
                "Focus on the point where control signals reverse."
            ],
            "created_at": "2026-04-07T02:06:00+00:00",
        },
    )


def _create_window(client, mission_id: str, payload: dict[str, object]) -> dict[str, object]:
    response = client.post(f"/api/expeditions/{mission_id}/replay/window", json=payload)
    body = response.get_json(silent=True) or {}
    _assert(response.status_code == 200, f"replay window should succeed: {response.status_code} {body}")
    item = body.get("item") if isinstance(body.get("item"), dict) else {}
    _assert(item.get("replay_window_id"), f"replay window should return a replay_window_id: {body}")
    return item


def _test_replay_window_creation() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="replay_window_api_"))
    mission_id = "mission_replay_window"
    with _patched_roots(temp_root):
        _seed_mission(temp_root, mission_id)
        dashboard_api.app.config["TESTING"] = True
        with dashboard_api.app.test_client() as client:
            item = _create_window(client, mission_id, {"mode": "event_count", "value": 4})

        _assert(item.get("mission_id") == mission_id, f"replay window should preserve mission id: {item}")
        _assert(item.get("event_count") == 4, f"event_count window should freeze the requested slice: {item}")
        _assert(item.get("available_directions") == ["forward", "reverse"], f"replay window should advertise both traversal directions: {item}")
        _assert(item.get("truth_frozen") is True, f"replay window should explicitly preserve truth immutability: {item}")


def _test_replay_frame_fidelity_and_signals() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="replay_frame_api_"))
    mission_id = "mission_replay_frame"
    with _patched_roots(temp_root):
        _seed_mission(temp_root, mission_id)
        dashboard_api.app.config["TESTING"] = True
        with dashboard_api.app.test_client() as client:
            window = _create_window(client, mission_id, {"mode": "relative_time", "value": "5m"})
            response = client.get(
                f"/api/expeditions/{mission_id}/replay/frame",
                query_string={
                    "replay_window_id": window["replay_window_id"],
                    "cursor_index": 1,
                    "direction": "forward",
                },
            )
        body = response.get_json(silent=True) or {}
        item = body.get("item") if isinstance(body.get("item"), dict) else {}
        fidelity = item.get("artifact_fidelity") if isinstance(item.get("artifact_fidelity"), dict) else {}
        active_signals = item.get("active_signals") if isinstance(item.get("active_signals"), dict) else {}

        _assert(response.status_code == 200, f"replay frame should succeed: {response.status_code} {body}")
        _assert(fidelity == {
            "chat_output_unchanged": True,
            "mission_state_unchanged": True,
            "artifacts_unchanged": True,
        }, f"replay frame should return explicit artifact fidelity guarantees: {fidelity}")
        _assert(set(active_signals.keys()) == {"mission_id", "activity", "blocked", "contradiction", "stall", "handoff"}, f"replay frame should return structured active_signals: {active_signals}")
        _assert((active_signals.get("activity") or {}).get("kind"), f"replay activity should be grounded in the current frame event: {active_signals}")
        _assert(str(item.get("mirror_observation") or "").startswith("Mirror "), f"mirror observation should keep Mirror voice discipline: {item}")


def _test_reverse_replay_preserves_truth_invariants() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="replay_reverse_api_"))
    mission_id = "mission_replay_reverse"
    with _patched_roots(temp_root):
        _seed_mission(temp_root, mission_id)
        dashboard_api.app.config["TESTING"] = True
        with dashboard_api.app.test_client() as client:
            window = _create_window(client, mission_id, {"mode": "event_count", "value": 5})
            forward_response = client.get(
                f"/api/expeditions/{mission_id}/replay/frame",
                query_string={
                    "replay_window_id": window["replay_window_id"],
                    "cursor_index": 2,
                    "direction": "forward",
                },
            )
            reverse_response = client.get(
                f"/api/expeditions/{mission_id}/replay/frame",
                query_string={
                    "replay_window_id": window["replay_window_id"],
                    "cursor_index": 2,
                    "direction": "reverse",
                },
            )
        forward_body = forward_response.get_json(silent=True) or {}
        reverse_body = reverse_response.get_json(silent=True) or {}
        forward_item = forward_body.get("item") if isinstance(forward_body.get("item"), dict) else {}
        reverse_item = reverse_body.get("item") if isinstance(reverse_body.get("item"), dict) else {}
        forward_event = ((forward_item.get("frame_context") or {}).get("current_event") or {})
        reverse_event = ((reverse_item.get("frame_context") or {}).get("current_event") or {})

        _assert(forward_response.status_code == 200 and reverse_response.status_code == 200, f"reverse replay should succeed in both directions: {forward_body} {reverse_body}")
        _assert(forward_item.get("cursor_time") == reverse_item.get("cursor_time"), f"reverse replay should not mutate event timestamps: {forward_item} {reverse_item}")
        _assert(forward_event.get("event_key") == reverse_event.get("event_key"), f"reverse replay should change traversal only, not truth selection: {forward_event} {reverse_event}")
        _assert("Truth is unchanged" in str(reverse_item.get("observer_note") or ""), f"reverse replay should ground the user in preserved truth invariants: {reverse_item}")


def _test_unknown_mission_failures() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="replay_missing_mission_"))
    with _patched_roots(temp_root):
        dashboard_api.app.config["TESTING"] = True
        with dashboard_api.app.test_client() as client:
            window_response = client.post("/api/expeditions/missing/replay/window", json={"mode": "event_count", "value": 2})
            cursor_response = client.post("/api/expeditions/missing/replay/cursor", json={"replay_window_id": "rw_invalid", "action": "pause"})
            frame_response = client.get("/api/expeditions/missing/replay/frame", query_string={"replay_window_id": "rw_invalid"})

        for response in [window_response, cursor_response, frame_response]:
            body = response.get_json(silent=True) or {}
            _assert(response.status_code == 404, f"unknown mission should fail cleanly with 404: {response.status_code} {body}")
            _assert(body.get("error") == "mission not found", f"unknown mission should keep the existing error shape: {body}")


def main() -> int:
    _test_replay_window_creation()
    _test_replay_frame_fidelity_and_signals()
    _test_reverse_replay_preserves_truth_invariants()
    _test_unknown_mission_failures()
    print("expedition_replay_api_smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
