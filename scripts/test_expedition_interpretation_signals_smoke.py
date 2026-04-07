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


def _seed_mission(root: Path, mission_id: str, *, with_mirror: bool) -> None:
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
            "objective": "Interpret the mission timeline safely",
            "task_text": "Interpret the mission timeline safely",
            "created_at": "2026-04-07T01:59:00+00:00",
            "latest_run_id": "",
        },
    )
    _write_json(expedition_root / "artifact_index.json", {"mission_id": mission_id, "items": []})
    _write_json(
        expedition_root / "working_memory.json",
        {
            "mission_id": mission_id,
            "latest_summary": "The mission is blocked on one operator confirmation.",
            "confirmed_facts": [],
            "open_questions": [],
            "deferred_questions": [],
            "updated_at": "2026-04-07T02:01:00+00:00",
            "operating_status": "blocked",
            "blocked_reason": "Need the operator to clarify the next bounded step.",
            "can_continue_without_input": False,
            "crew_status": "active",
            "expedition_activity": "running",
            "last_operator_reply_at": "2020-01-01T00:00:00+00:00",
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
            "updated_at": "2026-04-07T02:02:00+00:00",
            "derived_only": True,
        },
    )
    _write_json(
        notes_root / "retries.json",
        {
            "mission_id": mission_id,
            "retry_budget_total": 2,
            "retry_budget_used": 2,
            "last_retry_at": "2026-04-07T02:01:30+00:00",
            "last_failure_reason": "replacement helper returned the same failure",
            "stop_reason": "retry_budget_exhausted",
            "decision_log": [
                {
                    "decided_at": "2026-04-07T02:01:30+00:00",
                    "decision": "blocked",
                    "retry_reason": "bounded refresh after helper returned partial evidence",
                    "why_blocked": "blocked by exhausted retry budget",
                }
            ],
            "updated_at": "2026-04-07T02:01:30+00:00",
            "derived_only": True,
        },
    )
    _write_json(
        notes_root / "agent_runs" / "agent_run_001.json",
        {
            "run_id": "agent_run_001",
            "artifact_kind": "agent_role_invocation",
            "role": "spinetop-mirror",
            "role_label": "Mirror",
            "mission_id": mission_id,
            "created_at": "2026-04-07T02:03:00+00:00",
            "trigger_reason": "explicit_role_invocation",
            "status": "success",
            "summary": "Mirror reviewed the contradictory signals.",
            "next_step": "Inspect the contradiction note.",
        },
    )
    if with_mirror:
        _write_json(
            notes_root / "mirror" / "mirror_reflection_001.json",
            {
                "role": "spinetop-mirror",
                "kind": "mirror_reflection",
                "summary": "Control signals reverse faster than the mission context stabilizes.",
                "patterns": [
                    "Repeated signals outweigh explanation in the recent mission trace.",
                    "The same open question keeps reappearing across artifacts.",
                ],
                "contradictions": [
                    "Operator control signals alternate between proceed and pause across adjacent artifacts."
                ],
                "gaps": [
                    "Some mission-local notes are missing timestamps."
                ],
                "suggested_focus": [
                    "Focus on the point where control signals reverse."
                ],
                "created_at": "2026-04-07T02:04:00+00:00",
            },
        )


def _test_interpretation_endpoint() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="interpretation_api_"))
    mission_id = "mission_interpretation_api"
    with _patched_roots(temp_root):
        _seed_mission(temp_root, mission_id, with_mirror=True)
        dashboard_api.app.config["TESTING"] = True
        with dashboard_api.app.test_client() as client:
            response = client.get(f"/api/expeditions/{mission_id}/interpretation")
        body = response.get_json(silent=True) or {}
        item = body.get("item") if isinstance(body.get("item"), dict) else {}

        _assert(response.status_code == 200, f"interpretation endpoint should succeed: {response.status_code} {body}")
        _assert(body.get("available") is True, f"interpretation endpoint should expose persisted mirror interpretation: {body}")
        _assert(set(item.keys()) == {"summary", "patterns", "contradictions", "suggested_focus"}, f"interpretation payload should stay minimal: {item}")
        _assert(item.get("summary") == "Control signals reverse faster than the mission context stabilizes.", f"interpretation should reuse mirror summary: {item}")
        _assert(item.get("contradictions") == ["Operator control signals alternate between proceed and pause across adjacent artifacts."], f"interpretation should reuse mirror contradictions: {item}")


def _test_interpretation_mode_is_deferred() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="interpretation_mode_deferred_"))
    mission_id = "mission_interpretation_mode"
    with _patched_roots(temp_root):
        _seed_mission(temp_root, mission_id, with_mirror=True)
        dashboard_api.app.config["TESTING"] = True
        with dashboard_api.app.test_client() as client:
            response = client.get(f"/api/expeditions/{mission_id}/interpretation?mode=strict")
        body = response.get_json(silent=True) or {}

        _assert(response.status_code == 400, f"mode should be explicitly deferred rather than invented: {response.status_code} {body}")
        _assert("deferred" in str(body.get("error") or "").lower(), f"mode defer reason should be explicit: {body}")


def _test_interpretation_unavailable_without_mirror() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="interpretation_unavailable_"))
    mission_id = "mission_no_interpretation"
    with _patched_roots(temp_root):
        _seed_mission(temp_root, mission_id, with_mirror=False)
        dashboard_api.app.config["TESTING"] = True
        with dashboard_api.app.test_client() as client:
            response = client.get(f"/api/expeditions/{mission_id}/interpretation")
        body = response.get_json(silent=True) or {}

        _assert(response.status_code == 200, f"missing mirror interpretation should be reported without mutation: {response.status_code} {body}")
        _assert(body.get("available") is False, f"endpoint should say interpretation is unavailable instead of inventing one: {body}")


def _test_signals_endpoint() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="signals_api_"))
    mission_id = "mission_signals_api"
    with _patched_roots(temp_root):
        _seed_mission(temp_root, mission_id, with_mirror=True)
        dashboard_api.app.config["TESTING"] = True
        with dashboard_api.app.test_client() as client:
            response = client.get(f"/api/expeditions/{mission_id}/signals")
        body = response.get_json(silent=True) or {}
        item = body.get("item") if isinstance(body.get("item"), dict) else {}

        _assert(response.status_code == 200, f"signals endpoint should succeed: {response.status_code} {body}")
        _assert(set(item.keys()) == {"mission_id", "activity", "blocked", "contradiction", "stall", "handoff"}, f"signals payload should stay minimal: {item}")
        activity = item.get("activity") if isinstance(item.get("activity"), dict) else {}
        contradiction = item.get("contradiction") if isinstance(item.get("contradiction"), dict) else {}
        stall = item.get("stall") if isinstance(item.get("stall"), dict) else {}
        handoff = item.get("handoff") if isinstance(item.get("handoff"), dict) else {}

        _assert(activity.get("role") == "Mirror", f"activity should reuse the latest derived activity from Mirror/control tower ordering: {activity}")
        _assert(activity.get("kind") == "mirror_note", f"activity kind should come from the existing control tower latest activity: {activity}")
        _assert((item.get("blocked") or {}).get("present") is True, f"blocked signal should come from existing blocked/autonomy state: {item}")
        _assert(contradiction.get("present") is True and contradiction.get("count") == 1, f"contradiction should come from mirror-derived contradictions: {contradiction}")
        _assert(stall.get("present") is True, f"stall should come from queue hygiene stale/blocked signals: {stall}")
        _assert(handoff.get("present") is True and handoff.get("status") == "blocked", f"handoff should reuse the existing blocked handoff overlay without inventing a new state: {handoff}")


def main() -> int:
    _test_interpretation_endpoint()
    _test_interpretation_mode_is_deferred()
    _test_interpretation_unavailable_without_mirror()
    _test_signals_endpoint()
    print("expedition_interpretation_signals_smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
