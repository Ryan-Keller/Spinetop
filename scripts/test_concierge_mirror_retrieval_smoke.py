from __future__ import annotations

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


def _post(client, path: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    response = client.post(path, json=payload)
    return response.status_code, response.get_json(silent=True) or {}


def _create_mission(client) -> str:
    status_code, body = _post(client, "/api/expeditions", {"objective": "Keep concierge retrieval grounded only in mission-local saved mirror notes."})
    _assert(status_code == 200 and body.get("ok") is True, f"mission create failed: {status_code} {body}")
    return str((body.get("item") or {}).get("mission_id") or "")


def _save_note(client, mission_id: str, text: str) -> dict[str, object]:
    status_code, body = _post(client, f"/api/expeditions/{mission_id}/chat", {"text": f"save: {text}"})
    _assert(status_code == 200 and body.get("ok") is True, f"save failed: {status_code} {body}")
    _assert(body.get("kind") == "operator_save", f"save should stay on the operator_save path: {body}")
    return body


def _assert_no_truth_writes(temp_root: Path) -> None:
    _assert(not (temp_root / "memory" / "collective").exists(), "collective writes must stay absent during retrieval")
    _assert(not (temp_root / "memory" / "dispatch" / "approved").exists(), "approved dispatch writes must stay absent during retrieval")


def _test_recent_items() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="concierge_mirror_recent_"))
    with _patched_roots(temp_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        mission_id = _create_mission(client)
        mirror_dir = temp_root / "workbench" / "missions" / mission_id / "notes" / "mirror"
        chat_path = temp_root / "workbench" / "missions" / mission_id / "notes" / "chat.jsonl"

        _save_note(client, mission_id, "I love pizza with even more pizza.")
        _save_note(client, mission_id, "Dinner idea: grilled chicken bowls.")
        before_files = sorted(path.name for path in mirror_dir.glob("*.json"))

        def _unexpected_invoke(*args, **kwargs):
            raise AssertionError("mirror retrieval should not invoke the model seam")

        with _patched_attr(dashboard_api, "invoke_model", _unexpected_invoke):
            status_code, body = _post(client, f"/api/expeditions/{mission_id}/chat", {"content": "[Concierge] show what I saved recently"})

        _assert(status_code == 200 and body.get("ok") is True, f"recent retrieval failed: {status_code} {body}")
        _assert(body.get("kind") == "concierge_mirror_retrieval", f"recent retrieval should expose its retrieval kind: {body}")
        response = body.get("response") if isinstance(body.get("response"), dict) else {}
        matches = response.get("matches") if isinstance(response.get("matches"), list) else []
        _assert(len(matches) == 2, f"recent retrieval should return the saved notes newest-first: {body}")
        _assert(str(matches[0].get("text") or "") == "Dinner idea: grilled chicken bowls.", f"recent retrieval should surface the newest note first: {matches}")
        _assert(not chat_path.exists(), f"retrieval should stay read-only and must not append mission chat: {chat_path}")
        _assert(before_files == sorted(path.name for path in mirror_dir.glob('*.json')), "retrieval should not mutate mirror artifacts")
        _assert(not dashboard_api.EXPEDITIONER_MODEL_LOG.exists(), "retrieval should not log Expeditioner model invocations")
        _assert_no_truth_writes(temp_root)


def _test_topic_match() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="concierge_mirror_topic_"))
    with _patched_roots(temp_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        mission_id = _create_mission(client)
        chat_path = temp_root / "workbench" / "missions" / mission_id / "notes" / "chat.jsonl"

        _save_note(client, mission_id, "Dinner idea: grilled chicken bowls.")
        _save_note(client, mission_id, "Dog sitting note: use a treat lure and reward the sit.")

        def _unexpected_invoke(*args, **kwargs):
            raise AssertionError("topic retrieval should not invoke the model seam")

        with _patched_attr(dashboard_api, "invoke_model", _unexpected_invoke):
            status_code, body = _post(client, f"/api/expeditions/{mission_id}/chat", {"content": "what have I saved about dinner?"})

        _assert(status_code == 200 and body.get("ok") is True, f"topic retrieval failed: {status_code} {body}")
        response = body.get("response") if isinstance(body.get("response"), dict) else {}
        matches = response.get("matches") if isinstance(response.get("matches"), list) else []
        _assert(len(matches) == 1, f"topic retrieval should return only relevant saved notes: {body}")
        _assert(str(matches[0].get("text") or "") == "Dinner idea: grilled chicken bowls.", f"topic retrieval returned the wrong note: {matches}")
        _assert(str(response.get("query") or "") == "dinner", f"topic retrieval should preserve the cleaned query: {response}")
        _assert(not chat_path.exists(), f"topic retrieval should not append mission chat: {chat_path}")
        _assert(not dashboard_api.EXPEDITIONER_MODEL_LOG.exists(), "topic retrieval should not log Expeditioner model invocations")
        _assert_no_truth_writes(temp_root)


def _test_no_matches() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="concierge_mirror_none_"))
    with _patched_roots(temp_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        mission_id = _create_mission(client)
        chat_path = temp_root / "workbench" / "missions" / mission_id / "notes" / "chat.jsonl"

        _save_note(client, mission_id, "Dinner idea: grilled chicken bowls.")

        def _unexpected_invoke(*args, **kwargs):
            raise AssertionError("no-match retrieval should not invoke the model seam")

        with _patched_attr(dashboard_api, "invoke_model", _unexpected_invoke):
            status_code, body = _post(client, f"/api/expeditions/{mission_id}/chat", {"content": "what have I saved about volcanoes?"})

        _assert(status_code == 200 and body.get("ok") is True, f"no-match retrieval failed: {status_code} {body}")
        response = body.get("response") if isinstance(body.get("response"), dict) else {}
        matches = response.get("matches") if isinstance(response.get("matches"), list) else []
        _assert(matches == [], f"no-match retrieval should return an empty match list: {body}")
        _assert(
            str(response.get("message") or "") == "I do not see any saved mirror notes about volcanoes in this mission.",
            f"no-match retrieval should answer plainly and only from mission-local mirror notes: {response}",
        )
        _assert(not chat_path.exists(), f"no-match retrieval should not append mission chat: {chat_path}")
        _assert(not dashboard_api.EXPEDITIONER_MODEL_LOG.exists(), "no-match retrieval should not log Expeditioner model invocations")
        _assert_no_truth_writes(temp_root)


def main() -> int:
    _test_recent_items()
    _test_topic_match()
    _test_no_matches()
    print("concierge_mirror_retrieval_smoke_ok")
    print("verified=recent retrieval, topic match retrieval, no-match retrieval, no mirror mutation, no mission-chat append during retrieval, no Expeditioner model invocation, no truth-lane writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
