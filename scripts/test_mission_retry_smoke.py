from __future__ import annotations

import json
import tempfile
import threading
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


def _create_mission(client, objective: str) -> str:
    created = _post_json(client, "/api/expeditions", {"objective": objective})
    return str(created["item"]["mission_id"])


def _retry_ledger_path(root: Path, mission_id: str) -> Path:
    return root / "workbench" / "missions" / mission_id / "notes" / "retries.json"


def _runner_return_path(root: Path, mission_id: str, instance_id: str) -> Path:
    return root / "workbench" / "missions" / mission_id / "notes" / "runner_returns" / f"{instance_id}.json"


def _write_runner_return(root: Path, mission_id: str, instance_id: str, *, summary: str, open_question: str, next_step: str) -> None:
    path = _runner_return_path(root, mission_id, instance_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mission_id": mission_id,
        "instance_id": instance_id,
        "created_at": "2026-04-05T12:00:00+00:00",
        "summary": summary,
        "open_questions": [open_question],
        "recommended_next_step": next_step,
        "derived_only": True,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    concurrent_root = Path(tempfile.mkdtemp(prefix="mission_retry_concurrent_"))
    with _patched_roots(concurrent_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        concurrent_mission = _create_mission(client, "Concurrent retries should reserve one shared budget slot")
        original_budget_total = dashboard_api.RETRY_BUDGET_TOTAL
        dashboard_api.RETRY_BUDGET_TOTAL = 1
        try:
            barrier = threading.Barrier(2)
            results: list[dict[str, object]] = [{}, {}]

            def _attempt_retry(index: int) -> None:
                barrier.wait()
                results[index] = dashboard_api._create_trigger_record(
                    concurrent_mission,
                    trigger_kind="operator_refresh_requested",
                    reason=f"concurrent retry attempt {index + 1}",
                    source="test_concurrency",
                )

            threads = [threading.Thread(target=_attempt_retry, args=(index,)) for index in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        finally:
            dashboard_api.RETRY_BUDGET_TOTAL = original_budget_total

        concurrent_statuses = sorted(str(result.get("status") or "") for result in results)
        concurrent_reasons = [str(((result.get("evaluation") or {}) if isinstance(result.get("evaluation"), dict) else {}).get("blocked_reason") or "") for result in results]
        concurrent_ledger = _read_json(_retry_ledger_path(concurrent_root, concurrent_mission))
        _assert(concurrent_statuses == ["blocked", "pending"], f"concurrent retries should allow only one winner: {results}")
        _assert(any("exhausted retry budget" in reason for reason in concurrent_reasons), f"concurrent blocked retry should exhaust the one-slot budget: {results}")
        _assert(int(concurrent_ledger.get("retry_budget_used") or 0) == 1, f"concurrent retries must consume exactly one budget unit: {concurrent_ledger}")

    allowed_root = Path(tempfile.mkdtemp(prefix="mission_retry_allowed_"))
    with _patched_roots(allowed_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        allowed_mission = _create_mission(client, "Allowed retry should consume budget")
        allowed = _post_json(
            client,
            f"/api/expeditions/{allowed_mission}/triggers",
            {
                "trigger_kind": "operator_refresh_requested",
                "reason": "operator requested bounded refresh",
            },
        )
        allowed_trigger = allowed.get("trigger")
        allowed_ledger = _read_json(_retry_ledger_path(allowed_root, allowed_mission))
        _assert(isinstance(allowed_trigger, dict) and allowed_trigger.get("status") == "pending", "allowed retry should be pending")
        _assert(int(allowed_ledger.get("retry_budget_used") or 0) == 1, f"allowed retry should consume one budget unit: {allowed_ledger}")
        _assert(str(allowed_ledger.get("retry_reasons") or "") != "[]", "allowed retry should record a retry reason")

    blocked_root = Path(tempfile.mkdtemp(prefix="mission_retry_blocked_"))
    with _patched_roots(blocked_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        blocked_mission = _create_mission(client, "Blocked retry should not consume budget")
        _post_json(
            client,
            f"/api/expeditions/{blocked_mission}/parking",
            {
                "status": "parked",
                "reason": "pause while blocked",
                "resume_hint": "resume explicitly",
            },
        )
        blocked = _post_json(
            client,
            f"/api/expeditions/{blocked_mission}/triggers",
            {
                "trigger_kind": "operator_refresh_requested",
                "reason": "should be blocked while parked",
            },
        )
        blocked_trigger = blocked.get("trigger")
        blocked_ledger = _read_json(_retry_ledger_path(blocked_root, blocked_mission))
        blocked_log = blocked_ledger.get("decision_log") if isinstance(blocked_ledger.get("decision_log"), list) else []
        _assert(isinstance(blocked_trigger, dict) and blocked_trigger.get("status") == "blocked", "parked retry should be blocked")
        _assert(int(blocked_ledger.get("retry_budget_used") or 0) == 0, f"blocked retry should not consume budget: {blocked_ledger}")
        _assert(blocked_log and str(blocked_log[-1].get("stop_condition") or "") == "mission_parked", f"blocked retry should log parked stop condition: {blocked_ledger}")

    repeated_root = Path(tempfile.mkdtemp(prefix="mission_retry_repeat_"))
    with _patched_roots(repeated_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        repeated_mission = _create_mission(client, "Repeated same failure should stop")
        _write_runner_return(
            repeated_root,
            repeated_mission,
            "runner_same_failure",
            summary="Runner helper blocked on the same evidence bundle.",
            open_question="The helper blocked before it could return a complete evidence bundle.",
            next_step="Inspect the blocked retrieval receipt and decide whether replacement is needed.",
        )
        first_retry = _post_json(
            client,
            f"/api/expeditions/{repeated_mission}/triggers",
            {
                "trigger_kind": "operator_refresh_requested",
                "reason": "retry after helper suggested one bounded follow-up",
            },
        )
        second_retry = _post_json(
            client,
            f"/api/expeditions/{repeated_mission}/triggers",
            {
                "trigger_kind": "operator_refresh_requested",
                "reason": "retry the same failure again",
            },
        )
        repeated_ledger = _read_json(_retry_ledger_path(repeated_root, repeated_mission))
        repeated_log = repeated_ledger.get("decision_log") if isinstance(repeated_ledger.get("decision_log"), list) else []
        _assert(isinstance(first_retry.get("trigger"), dict) and first_retry["trigger"].get("status") == "pending", "first repeated-failure retry should be allowed once")
        _assert(isinstance(second_retry.get("trigger"), dict) and second_retry["trigger"].get("status") == "blocked", "second repeated-failure retry should be blocked")
        _assert(int(repeated_ledger.get("retry_budget_used") or 0) == 1, f"blocked repeated failure should not consume another budget unit: {repeated_ledger}")
        _assert(
            repeated_log and str(repeated_log[-1].get("stop_condition") or "") == "repeated_same_failure_without_new_evidence",
            f"repeated same failure should stop explicitly: {repeated_ledger}",
        )

    parked_root = Path(tempfile.mkdtemp(prefix="mission_retry_parked_"))
    with _patched_roots(parked_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        parked_mission = _create_mission(client, "Parked mission cannot retry")
        _post_json(
            client,
            f"/api/expeditions/{parked_mission}/parking",
            {
                "status": "parked",
                "reason": "operator paused the mission",
                "resume_hint": "resume explicitly",
            },
        )
        parked_retry = _post_json(
            client,
            f"/api/expeditions/{parked_mission}/triggers",
            {
                "trigger_kind": "operator_refresh_requested",
                "reason": "parked mission should not retry",
            },
        )
        parked_ledger = _read_json(_retry_ledger_path(parked_root, parked_mission))
        _assert(isinstance(parked_retry.get("trigger"), dict) and parked_retry["trigger"].get("status") == "blocked", "parked mission retry must be blocked")
        _assert(str(parked_ledger.get("stop_reason") or "") == "mission_parked", f"parked mission should record an explicit stop reason: {parked_ledger}")

        expedition_retry_dir = parked_root / "expeditions" / "active" / parked_mission / "notes"
        _assert(not expedition_retry_dir.exists(), "retry ledger must remain mission-local and not leak into canonical expedition state")
        dispatch_root = parked_root / "memory" / "dispatch"
        _assert(not dispatch_root.exists() or not any(dispatch_root.rglob("*.json")), "retry flow should not write to dispatch")

    print("mission retry smoke passed")
    print("verified=concurrent atomic retry budget, allowed budget use, blocked no-consume, repeated same-failure stop, parked stop, mission-local writes only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
