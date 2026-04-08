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
    status_code, body = _post(client, "/api/expeditions", {"objective": "Keep this mission-local note path mechanical and inspectable."})
    _assert(status_code == 200, f"mission create failed: {status_code} {body}")
    _assert(body.get("ok") is True, f"mission create payload not ok: {body}")
    return str((body.get("item") or {}).get("mission_id") or "")


def _assert_no_truth_writes(temp_root: Path) -> None:
    collective_dir = temp_root / "memory" / "collective"
    approved_dispatch_dir = temp_root / "memory" / "dispatch" / "approved"
    _assert(not collective_dir.exists(), f"collective writes must stay absent: {collective_dir}")
    _assert(not approved_dispatch_dir.exists(), f"approved dispatch writes must stay absent: {approved_dispatch_dir}")


def _test_valid_save_write() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="operator_save_valid_"))
    with _patched_roots(temp_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        mission_id = _create_mission(client)
        mirror_dir = temp_root / "workbench" / "missions" / mission_id / "notes" / "mirror"
        chat_path = temp_root / "workbench" / "missions" / mission_id / "notes" / "chat.jsonl"

        def _unexpected_invoke(*args, **kwargs):
            raise AssertionError("save path should not invoke the model seam")

        with _patched_attr(dashboard_api, "invoke_model", _unexpected_invoke):
            status_code, body = _post(
                client,
                f"/api/expeditions/{mission_id}/chat",
                {"text": "save: I love pizza with even more pizza."},
            )

        _assert(status_code == 200, f"save write should succeed: {status_code} {body}")
        _assert(body.get("ok") is True, f"save write payload should be ok: {body}")
        _assert(body.get("kind") == "operator_save", f"save write should return operator_save kind: {body}")
        _assert(body.get("message") == "Saved to mirror.", f"save write should return the bounded success message: {body}")
        artifact_path = temp_root / str(body.get("artifact_path") or "")
        _assert(artifact_path.exists(), f"mirror artifact file missing: {artifact_path}")
        _assert(artifact_path.parent == mirror_dir, f"mirror artifact should live under the mission-local mirror lane: {artifact_path}")
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        _assert(payload.get("artifact_kind") == "operator_save", f"unexpected artifact kind: {payload}")
        _assert(payload.get("source") == "operator", f"unexpected artifact source: {payload}")
        _assert(payload.get("text") == "I love pizza with even more pizza.", f"text should be preserved exactly after `save:`: {payload}")
        _assert(payload.get("mission_id") == mission_id, f"artifact mission_id mismatch: {payload}")
        _assert(payload.get("derived_only") is False, f"operator save should not be marked derived-only: {payload}")
        _assert(not chat_path.exists(), f"save path should not append mission chat: {chat_path}")
        _assert(not dashboard_api.EXPEDITIONER_MODEL_LOG.exists(), "save path should not log a model invocation")
        notes_response = client.get(f"/api/expeditions/{mission_id}/mirror-notes")
        notes_body = notes_response.get_json(silent=True) or {}
        _assert(notes_response.status_code == 200, f"mirror-notes endpoint should succeed after save: {notes_response.status_code} {notes_body}")
        items = notes_body.get("items") if isinstance(notes_body.get("items"), list) else []
        _assert(items, f"mirror-notes endpoint should return the saved note: {notes_body}")
        latest = items[0] if isinstance(items[0], dict) else {}
        _assert(latest.get("artifact_id") == payload.get("artifact_id"), f"mirror-notes should expose artifact_id: {latest}")
        _assert(latest.get("artifact_kind") == "operator_save", f"mirror-notes should expose operator_save kind: {latest}")
        _assert(latest.get("text") == "I love pizza with even more pizza.", f"mirror-notes should expose exact saved text: {latest}")
        _assert_no_truth_writes(temp_root)


def _test_message_field_save_write_via_input() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="operator_save_message_"))
    with _patched_roots(temp_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        mission_id = _create_mission(client)
        mirror_dir = temp_root / "workbench" / "missions" / mission_id / "notes" / "mirror"
        intake_dir = temp_root / "workbench" / "missions" / mission_id / "intake"
        chat_path = temp_root / "workbench" / "missions" / mission_id / "notes" / "chat.jsonl"

        def _unexpected_invoke(*args, **kwargs):
            raise AssertionError("message-field save path should not invoke the model seam")

        with _patched_attr(dashboard_api, "invoke_model", _unexpected_invoke):
            status_code, body = _post(
                client,
                f"/api/expeditions/{mission_id}/input",
                {"message": "  SAVE: preserve this exact note  "},
            )

        _assert(status_code == 200, f"message-field save should succeed: {status_code} {body}")
        _assert(body.get("ok") is True, f"message-field save payload should be ok: {body}")
        _assert(body.get("kind") == "operator_save", f"message-field save should return operator_save kind: {body}")
        artifact_path = temp_root / str(body.get("artifact_path") or "")
        _assert(artifact_path.exists(), f"message-field mirror artifact missing: {artifact_path}")
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        _assert(payload.get("text") == "preserve this exact note", f"message-field save should trim only around the save prefix content: {payload}")
        _assert(artifact_path.parent == mirror_dir, f"message-field save should write to the mirror lane: {artifact_path}")
        _assert(not list(intake_dir.glob("*.json")), f"message-field save should not create intake artifacts: {list(intake_dir.glob('*.json'))}")
        _assert(not chat_path.exists(), f"message-field save should not append mission chat: {chat_path}")
        _assert_no_truth_writes(temp_root)


def _test_empty_save_is_bounded_noop() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="operator_save_empty_"))
    with _patched_roots(temp_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        mission_id = _create_mission(client)
        mirror_dir = temp_root / "workbench" / "missions" / mission_id / "notes" / "mirror"
        chat_path = temp_root / "workbench" / "missions" / mission_id / "notes" / "chat.jsonl"

        def _unexpected_invoke(*args, **kwargs):
            raise AssertionError("empty save path should not invoke the model seam")

        with _patched_attr(dashboard_api, "invoke_model", _unexpected_invoke):
            status_code, body = _post(
                client,
                f"/api/expeditions/{mission_id}/chat",
                {"text": "save:   "},
            )

        _assert(status_code == 400, f"empty save should return a bounded failure: {status_code} {body}")
        _assert(body.get("ok") is False, f"empty save should not be ok: {body}")
        _assert(body.get("kind") == "operator_save", f"empty save should keep operator_save kind: {body}")
        message_text = str(body.get("message") or "").lower()
        _assert("nothing written" in message_text, f"empty save should stay bounded and explicit: {body}")
        _assert(not mirror_dir.exists(), f"empty save should not create the mirror lane: {mirror_dir}")
        _assert(not chat_path.exists(), f"empty save should not append mission chat: {chat_path}")
        _assert(not dashboard_api.EXPEDITIONER_MODEL_LOG.exists(), "empty save should not log a model invocation")
        _assert_no_truth_writes(temp_root)


def _test_mirror_notes_endpoint_returns_empty_list_when_lane_is_missing() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="operator_save_empty_lane_"))
    with _patched_roots(temp_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()
        mission_id = _create_mission(client)

        response = client.get(f"/api/expeditions/{mission_id}/mirror-notes")
        body = response.get_json(silent=True) or {}

        _assert(response.status_code == 200, f"mirror-notes should stay readable when the folder is absent: {response.status_code} {body}")
        _assert(body.get("ok") is True, f"mirror-notes empty-lane response should still be ok: {body}")
        _assert(body.get("items") == [], f"mirror-notes should return an empty list when nothing has been saved: {body}")


def main() -> int:
    _test_valid_save_write()
    _test_message_field_save_write_via_input()
    _test_empty_save_is_bounded_noop()
    _test_mirror_notes_endpoint_returns_empty_list_when_lane_is_missing()
    print("operator_save_smoke_ok")
    print("verified=text and message payloads short-circuit early; valid save writes only to mission-local mirror lane; mirror-notes read endpoint exposes newest-first saved text; empty save is a bounded no-op; no chat append; no intake write; no model seam; no truth-lane writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
