from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

import autonomy_guardrails
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


def _post_json(client, path: str, payload: dict[str, object]) -> dict[str, object]:
    response = client.post(path, json=payload)
    body = response.get_json(silent=True) or {}
    if response.status_code >= 400:
        raise RuntimeError(f"POST {path} failed with HTTP {response.status_code}: {body}")
    if not body.get("ok", False):
        raise RuntimeError(f"POST {path} returned a non-ok payload: {body}")
    return body


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _get_json(client, path: str) -> dict[str, object]:
    response = client.get(path)
    body = response.get_json(silent=True) or {}
    if response.status_code >= 400:
        raise RuntimeError(f"GET {path} failed with HTTP {response.status_code}: {body}")
    if not body.get("ok", False):
        raise RuntimeError(f"GET {path} returned a non-ok payload: {body}")
    return body


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="mission_triggers_smoke_"))

    with _patched_roots(temp_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()

        created = _post_json(client, "/api/expeditions", {"objective": "Investigate the release regression with the provided logs"})
        mission = str(created["item"]["mission_id"])
        triggers_dir = temp_root / "workbench" / "missions" / mission / "notes" / "triggers"

        safe = _post_json(
            client,
            f"/api/expeditions/{mission}/triggers",
            {
                "trigger_kind": "do_now_first_pass_requested",
                "reason": "operator requested the first bounded expedition attempt",
            },
        )
        safe_trigger = safe.get("trigger")
        _assert(isinstance(safe_trigger, dict), "safe trigger payload missing")
        _assert(safe_trigger.get("status") == "pending", f"expected pending safe trigger, got {safe_trigger}")
        safe_path = temp_root / str(safe_trigger.get("path") or "")
        _assert(safe_path.exists(), f"safe trigger file missing: {safe_path}")
        _assert(triggers_dir in safe_path.parents, "safe trigger was not written to the mission-local trigger lane")
        safe_guardrails = safe_trigger.get("evaluation", {}).get("guardrails", {}) if isinstance(safe_trigger, dict) else {}
        _assert(str(safe_guardrails.get("status") or "") == "allowed", f"safe trigger guardrails should allow bounded movement: {safe_trigger}")

        duplicate_first_pass = _post_json(
            client,
            f"/api/expeditions/{mission}/triggers",
            {
                "trigger_kind": "do_now_first_pass_requested",
                "reason": "operator clicked the first-pass trigger again before execution",
            },
        )
        duplicate_trigger = duplicate_first_pass.get("trigger")
        duplicate_eval = duplicate_trigger.get("evaluation") if isinstance(duplicate_trigger, dict) else {}
        _assert(isinstance(duplicate_trigger, dict) and duplicate_trigger.get("status") == "blocked", "duplicate first-pass trigger should be rejected")
        _assert(str((duplicate_eval or {}).get("blocked_reason") or "") == "first-pass already pending", f"duplicate first-pass should say already pending: {duplicate_trigger}")

        blocked = _post_json(
            client,
            f"/api/expeditions/{mission}/triggers",
            {
                "trigger_kind": "operator_refresh_requested",
                "reason": "operator requested one explicit refresh",
            },
        )
        second_allowed = _post_json(
            client,
            f"/api/expeditions/{mission}/triggers",
            {
                "trigger_kind": "operator_refresh_requested",
                "reason": "operator requested a second bounded refresh",
            },
        )
        blocked_retry = _post_json(
            client,
            f"/api/expeditions/{mission}/triggers",
            {
                "trigger_kind": "operator_refresh_requested",
                "reason": "operator requested a third refresh beyond budget",
            },
        )
        first_refresh = blocked.get("trigger")
        second_refresh = second_allowed.get("trigger")
        third_refresh = blocked_retry.get("trigger")
        _assert(isinstance(first_refresh, dict) and first_refresh.get("status") == "pending", "first refresh trigger should be pending")
        _assert(isinstance(second_refresh, dict) and second_refresh.get("status") == "pending", "second refresh trigger should still be pending within budget")
        _assert(isinstance(third_refresh, dict) and third_refresh.get("status") == "blocked", "third refresh trigger should be blocked")
        third_eval = third_refresh.get("evaluation") if isinstance(third_refresh, dict) else {}
        _assert("exhausted retry budget" in str((third_eval or {}).get("reason") or ""), f"blocked retry reason missing: {third_refresh}")

        _write_json(
            temp_root / "logs" / "governance" / "return_all.json",
            {
                "enabled": True,
                "issued_by": "operator",
                "issued_at": "2026-04-05T12:00:00Z",
                "reason": "global pause",
            },
        )
        kill_switched = _post_json(
            client,
            f"/api/expeditions/{mission}/triggers",
            {
                "trigger_kind": "operator_refresh_requested",
                "reason": "refresh should stay blocked while return-all is active",
            },
        )
        kill_switch_trigger = kill_switched.get("trigger")
        _assert(isinstance(kill_switch_trigger, dict) and kill_switch_trigger.get("status") == "blocked", "kill-switch should block trigger execution")
        kill_switch_reason = str((kill_switch_trigger.get("evaluation") or {}).get("reason") or "").lower()
        _assert("kill-switch" in kill_switch_reason, f"kill-switch block reason missing: {kill_switch_trigger}")
        _write_json(temp_root / "logs" / "governance" / "return_all.json", {"enabled": False})

        parked = _post_json(
            client,
            f"/api/expeditions/{mission}/parking",
            {
                "status": "parked",
                "reason": "pause until explicit resume",
                "resume_hint": "resume explicitly",
            },
        )
        _assert(parked["parking_status"]["status"] == "parked", "mission did not park")
        parked_trigger = _post_json(
            client,
            f"/api/expeditions/{mission}/triggers",
            {
                "trigger_kind": "operator_refresh_requested",
                "reason": "refresh should stay blocked while parked",
            },
        )
        parked_record = parked_trigger.get("trigger")
        _assert(isinstance(parked_record, dict) and parked_record.get("status") == "blocked", "parked mission should block refresh trigger")
        parked_eval = parked_record.get("evaluation") if isinstance(parked_record, dict) else {}
        _assert("parked" in str((parked_eval or {}).get("reason") or "").lower(), f"parked block reason missing: {parked_record}")
        detail = _get_json(client, f"/api/expeditions/{mission}")
        mission_item = detail.get("item") if isinstance(detail.get("item"), dict) else {}
        autonomy_status = mission_item.get("autonomy_status") if isinstance(mission_item, dict) else {}
        _assert(isinstance(autonomy_status, dict), "autonomy status surface missing")
        for field in ("autonomy_status", "last_trigger_outcome", "retry_budget_summary", "last_blocked_reason"):
            _assert(str(autonomy_status.get(field) or "").strip() != "", f"autonomy status field missing: {field}")
        _assert(str(autonomy_status.get("autonomy_status") or "") == "blocked", f"blocked trigger should surface blocked autonomy status: {autonomy_status}")
        _assert("parked" in str(autonomy_status.get("last_blocked_reason") or "").lower(), f"blocked autonomy reason should stay blocked-only: {autonomy_status}")

        resumed = _post_json(
            client,
            f"/api/expeditions/{mission}/parking",
            {
                "status": "active",
                "reason": "resume explicitly",
            },
        )
        resume_trigger = resumed.get("trigger")
        _assert(isinstance(resume_trigger, dict), "resume trigger missing")
        _assert(resume_trigger.get("status") == "pending", f"resume trigger should be pending: {resume_trigger}")
        _assert(resume_trigger.get("trigger_kind") == "mission_resumed", f"unexpected resume trigger: {resume_trigger}")

        forbidden_guardrail = autonomy_guardrails.evaluate_autonomy_guardrails(
            mission_id=mission,
            trigger_kind="operator_refresh_requested",
            target_role="spinetop-expeditioner",
            allowed_action="retry_expedition_refresh",
            policy_basis="operator_requested_refresh",
            trigger_reason="test forbidden write target",
            trigger_source="operator_console",
            retry_budget_total=2,
            retry_budget_used=0,
            return_all_enabled=False,
            nanny_cooling=False,
            parked=False,
            allow_while_parked=False,
            counts_against_retry_budget=True,
            summary={"can_continue_without_input": True, "blocked_reason": ""},
            working_memory={},
            write_targets=["memory/collective/"],
        )
        _assert(str(forbidden_guardrail.get("status") or "") == "blocked", f"forbidden write target should be rejected: {forbidden_guardrail}")
        _assert(
            "forbidden write target" in str(forbidden_guardrail.get("reason") or "").lower(),
            f"forbidden write target reason missing: {forbidden_guardrail}",
        )

        trigger_files = sorted(triggers_dir.glob("*.json"))
        _assert(trigger_files, "expected trigger files to exist")
        for path in trigger_files:
            payload = _read_json(path)
            _assert(str(payload.get("mission_id") or "") == mission, f"trigger file mission mismatch: {path}")
            _assert(triggers_dir in path.parents or path == triggers_dir / "pending_handoff.json", f"trigger path escaped mission notes lane: {path}")

        expedition_trigger_dir = temp_root / "expeditions" / "active" / mission / "notes" / "triggers"
        _assert(not expedition_trigger_dir.exists(), "trigger records leaked into canonical expedition state")
        dispatch_root = temp_root / "memory" / "dispatch"
        _assert(not dispatch_root.exists() or not any(dispatch_root.rglob("*.json")), "trigger flow should not write to dispatch")

    status_root = Path(tempfile.mkdtemp(prefix="mission_status_allowed_"))
    with _patched_roots(status_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        created = _post_json(client, "/api/expeditions", {"objective": "Allowed trigger should not look blocked"})
        mission = str(created["item"]["mission_id"])
        _post_json(
            client,
            f"/api/expeditions/{mission}/triggers",
            {
                "trigger_kind": "do_now_first_pass_requested",
                "reason": "operator requested the first bounded expedition attempt",
            },
        )
        detail = _get_json(client, f"/api/expeditions/{mission}")
        mission_item = detail.get("item") if isinstance(detail.get("item"), dict) else {}
        autonomy_status = mission_item.get("autonomy_status") if isinstance(mission_item, dict) else {}
        _assert(str(autonomy_status.get("autonomy_status") or "") == "ready", f"allowed trigger should stay ready/ok, not blocked: {autonomy_status}")
        _assert(str(autonomy_status.get("last_blocked_reason") or "") == "", f"allowed trigger should not populate last_blocked_reason: {autonomy_status}")

    print("mission trigger smoke passed")
    print(f"mission_id={mission}")
    print("verified=safe create, duplicate first-pass rejection, kill-switch block, bounded retry budget, parked block, explicit resume, correct autonomy status, mission-local writes only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
