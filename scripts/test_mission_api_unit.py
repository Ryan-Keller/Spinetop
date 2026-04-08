from __future__ import annotations

from contextlib import contextmanager

from flask import Flask

import mission_api


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


@contextmanager
def _patched_attr(module, name: str, value):
    original = getattr(module, name)
    try:
        setattr(module, name, value)
        yield
    finally:
        setattr(module, name, original)


def _decode_response(result):
    if isinstance(result, tuple):
        response, status_code = result[0], int(result[1])
    else:
        response, status_code = result, int(result.status_code)
    return status_code, response.get_json(silent=True) or {}


class _FakeApi:
    @staticmethod
    def normalize_mission_id(mission_id: str) -> str:
        return str(mission_id or "").strip()

    @staticmethod
    def _mission_exists(mission_id: str) -> bool:
        return mission_id == "mission_api_unit"

    @staticmethod
    def _operator_raw_text(payload):
        if not isinstance(payload, dict):
            return ""
        for key in ("text", "message", "content"):
            value = payload.get(key)
            if value is not None:
                return str(value)
        return ""

    @staticmethod
    def _build_expedition_detail(mission_id: str):
        return {"mission_id": mission_id, "parking_status": {"status": "active"}}

    @staticmethod
    def _build_chat_exchange_items(mission_id: str, message: str, assistant: dict[str, object]):
        return (
            {"sender": "user", "mission_id": mission_id, "message": message},
            {"sender": "assistant", "mission_id": mission_id, "message": str(assistant.get("message") or "")},
        )

    @staticmethod
    def _mission_chat_messages(mission_id: str):
        return []


def _test_input_save_short_circuit() -> None:
    app = Flask(__name__)
    fake_api = _FakeApi()
    with _patched_attr(mission_api.save_api, "build_operator_save_result", lambda **kwargs: (200, {"ok": True, "kind": "operator_save", "artifact_path": "mirror/fake.json", "message": "Saved to mirror."})):
        with app.test_request_context(json={"text": "save: note"}):
            status_code, body = _decode_response(mission_api.handle_expedition_input(fake_api, "mission_api_unit"))
    _assert(status_code == 200, f"input save short-circuit should succeed: {status_code} {body}")
    _assert(body["kind"] == "operator_save", f"input save should preserve operator_save kind: {body}")


def _test_chat_retrieval_short_circuit() -> None:
    app = Flask(__name__)
    fake_api = _FakeApi()
    retrieval_payload = {
        "ok": True,
        "kind": "concierge_mirror_retrieval",
        "mission_id": "mission_api_unit",
        "query": "dinner",
        "mode": "semantic_match",
        "matches": [{"artifact_id": "note_001", "text": "Dinner idea: grilled chicken bowls.", "created_at": "2026-04-07T01:00:00+00:00", "artifact_kind": "operator_save"}],
        "message": "I found 1 saved mirror note about dinner in this mission.",
    }
    with _patched_attr(mission_api.save_api, "build_operator_save_result", lambda **kwargs: None):
        with _patched_attr(mission_api.mirror_api, "concierge_mirror_retrieval_result", lambda *args, **kwargs: retrieval_payload):
            with app.test_request_context(json={"text": "what have I saved about dinner?"}):
                status_code, body = _decode_response(mission_api.handle_expedition_chat(fake_api, "mission_api_unit"))
    _assert(status_code == 200, f"chat retrieval short-circuit should succeed: {status_code} {body}")
    _assert(body["kind"] == "concierge_mirror_retrieval", f"chat retrieval should preserve retrieval kind: {body}")
    _assert(body["response"]["query"] == "dinner", f"chat retrieval should surface the cleaned query: {body}")


def main() -> int:
    _test_input_save_short_circuit()
    _test_chat_retrieval_short_circuit()
    print("mission_api_unit_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
