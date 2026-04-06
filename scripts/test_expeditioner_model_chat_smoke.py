from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import dashboard_api
import governance_utils
import helper_model_runtime
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
        (dashboard_api, "EXPEDITIONER_MODEL_LOG", temp_root / "logs" / "support" / "expeditioner_model_invocations.jsonl"),
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


@contextmanager
def _patched_attr(module, name: str, value):
    original = getattr(module, name)
    try:
        setattr(module, name, value)
        yield
    finally:
        setattr(module, name, original)


def _post_json(client, path: str, payload: dict[str, object]) -> dict[str, object]:
    response = client.post(path, json=payload)
    body = response.get_json(silent=True) or {}
    if response.status_code >= 400:
        raise RuntimeError(f"POST {path} failed with HTTP {response.status_code}: {body}")
    if not body.get("ok", False):
        raise RuntimeError(f"POST {path} returned a non-ok payload: {body}")
    return body


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            rows.append(json.loads(text))
    return rows


def _assert_no_truth_writes(temp_root: Path) -> None:
    collective_dir = temp_root / "memory" / "collective"
    approved_dispatch_dir = temp_root / "memory" / "dispatch" / "approved"
    _assert(not collective_dir.exists(), f"collective writes must stay absent: {collective_dir}")
    _assert(not approved_dispatch_dir.exists(), f"approved dispatch writes must stay absent: {approved_dispatch_dir}")


def _base_expeditioner_profile() -> helper_model_runtime.HelperRuntimeProfile:
    return helper_model_runtime.load_helper_runtime_profile("spinetop_expeditioner")


def _create_mission(client) -> str:
    created = _post_json(client, "/api/expeditions", {"objective": "how do I teach my dog to sit"})
    return str(created["item"]["mission_id"])


def _enable_first_pass_trigger(client, mission_id: str) -> None:
    _post_json(
        client,
        f"/api/expeditions/{mission_id}/triggers",
        {
            "trigger_kind": "do_now_first_pass_requested",
            "reason": "operator requested the first bounded expedition attempt",
        },
    )


def main() -> int:
    success_root = Path(tempfile.mkdtemp(prefix="expeditioner_model_success_"))
    with _patched_roots(success_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        mission = _create_mission(client)
        _enable_first_pass_trigger(client, mission)
        active_profile = replace(_base_expeditioner_profile(), active=True)

        calls: list[dict[str, object]] = []

        def _fake_invoke(model_key: str, prompt: str, runtime_config: dict[str, object], **kwargs) -> str:
            calls.append({"model_key": model_key, "prompt": prompt, "kwargs": kwargs})
            return json.dumps(
                {
                    "first_pass_answer": "Use a treat lure, mark the sit, and reward immediately.",
                    "assumptions": ["The dog can focus for short 2 to 5 minute sessions."],
                    "next_steps": ["Add the verbal cue after a few successful lured reps."],
                }
            )

        with _patched_attr(dashboard_api, "load_helper_runtime_profile", lambda role_id: active_profile):
            with _patched_attr(dashboard_api, "invoke_model", _fake_invoke):
                result = _post_json(
                    client,
                    f"/api/expeditions/{mission}/chat",
                    {"content": "Please give the first pass now."},
                )

        response = result.get("response") if isinstance(result.get("response"), dict) else {}
        answer = str(response.get("answer") or "")
        _assert(calls, "model-backed path should invoke the shared model seam")
        _assert("First-pass answer:" in answer, "model-backed answer should preserve the first-pass label")
        _assert("Assumptions:" in answer, "model-backed answer should preserve the assumptions section")
        _assert("Next steps:" in answer, "model-backed answer should preserve the next-steps section")
        _assert("Use a treat lure" in answer, "model-backed answer should surface the model result")
        model_logs = _read_jsonl(dashboard_api.EXPEDITIONER_MODEL_LOG)
        _assert(len(model_logs) == 1, f"expected one model invocation log entry, got {model_logs}")
        _assert(str(model_logs[0].get("role") or "") == "spinetop_expeditioner", f"unexpected log role: {model_logs[0]}")
        _assert(str(model_logs[0].get("status") or "") == "success", f"model success should log success: {model_logs[0]}")
        _assert(str(model_logs[0].get("trigger_reason") or ""), f"trigger reason should be logged: {model_logs[0]}")
        _assert_no_truth_writes(success_root)

    no_trigger_root = Path(tempfile.mkdtemp(prefix="expeditioner_model_no_trigger_"))
    with _patched_roots(no_trigger_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        mission = _create_mission(client)
        active_profile = replace(_base_expeditioner_profile(), active=True)

        def _unexpected_invoke(*args, **kwargs):
            raise AssertionError("chat without trigger should not invoke the model")

        with _patched_attr(dashboard_api, "load_helper_runtime_profile", lambda role_id: active_profile):
            with _patched_attr(dashboard_api, "invoke_model", _unexpected_invoke):
                result = _post_json(
                    client,
                    f"/api/expeditions/{mission}/chat",
                    {"content": "Please give the first pass now."},
                )

        response = result.get("response") if isinstance(result.get("response"), dict) else {}
        answer = str(response.get("answer") or "")
        _assert("First-pass answer:" in answer, "chat without trigger should still preserve the output structure")
        _assert("use a treat to guide the dog into a sit" in answer.lower(), "chat without trigger should use the current scripted first pass")
        _assert(not dashboard_api.EXPEDITIONER_MODEL_LOG.exists(), "chat without trigger should not log a model invocation")
        _assert_no_truth_writes(no_trigger_root)

    disabled_root = Path(tempfile.mkdtemp(prefix="expeditioner_model_disabled_"))
    with _patched_roots(disabled_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        mission = _create_mission(client)
        disabled_profile = replace(_base_expeditioner_profile(), active=False)

        def _unexpected_invoke_disabled(*args, **kwargs):
            raise AssertionError("inactive role should not invoke the model")

        with _patched_attr(dashboard_api, "load_helper_runtime_profile", lambda role_id: disabled_profile):
            with _patched_attr(dashboard_api, "invoke_model", _unexpected_invoke_disabled):
                result = _post_json(
                    client,
                    f"/api/expeditions/{mission}/chat",
                    {"content": "Please give the first pass now."},
                )

        response = result.get("response") if isinstance(result.get("response"), dict) else {}
        answer = str(response.get("answer") or "")
        _assert("First-pass answer:" in answer, "inactive fallback should still preserve the output structure")
        _assert("use a treat to guide the dog into a sit" in answer.lower(), "inactive fallback should use the current scripted first pass")
        _assert(not dashboard_api.EXPEDITIONER_MODEL_LOG.exists(), "disabled-safe fallback should not log a model invocation")
        _assert_no_truth_writes(disabled_root)

    failure_root = Path(tempfile.mkdtemp(prefix="expeditioner_model_failure_"))
    with _patched_roots(failure_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        mission = _create_mission(client)
        _enable_first_pass_trigger(client, mission)
        active_profile = replace(_base_expeditioner_profile(), active=True)

        def _failing_invoke(*args, **kwargs):
            raise RuntimeError("timeout from fake provider")

        with _patched_attr(dashboard_api, "load_helper_runtime_profile", lambda role_id: active_profile):
            with _patched_attr(dashboard_api, "invoke_model", _failing_invoke):
                result = _post_json(
                    client,
                    f"/api/expeditions/{mission}/chat",
                    {"content": "Please give the first pass now."},
                )

        response = result.get("response") if isinstance(result.get("response"), dict) else {}
        answer = str(response.get("answer") or "")
        _assert("First-pass answer:" in answer, "failure fallback should preserve the output structure")
        _assert("use a treat to guide the dog into a sit" in answer.lower(), "failure fallback should return the scripted answer")
        model_logs = _read_jsonl(dashboard_api.EXPEDITIONER_MODEL_LOG)
        _assert(len(model_logs) == 1, f"expected one failed model invocation log entry, got {model_logs}")
        _assert(str(model_logs[0].get("status") or "") == "failure", f"failed invocation should log failure: {model_logs[0]}")
        _assert("timeout" in str(model_logs[0].get("error") or "").lower(), f"failed invocation should record the provider error: {model_logs[0]}")
        _assert_no_truth_writes(failure_root)

    print("expeditioner_model_chat_smoke_ok")
    print("verified=triggered model path only, no-trigger fallback, inactive fallback, failure fallback, structured output, no truth-lane writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
