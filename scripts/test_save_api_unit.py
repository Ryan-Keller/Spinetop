from __future__ import annotations

import save_api


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _test_extract_save_text_and_result_shape() -> None:
    calls: list[tuple[str, str]] = []

    def _fake_writer(mission_id: str, text: str) -> str:
        calls.append((mission_id, text))
        return f"workbench/missions/{mission_id}/notes/mirror/fake.json"

    _assert(save_api.extract_save_text(" SAVE: keep this ") == "keep this", "save prefix should be trimmed case-insensitively")
    _assert(save_api.extract_save_text("chat") is None, "non-save message should not be treated as save")

    empty = save_api.build_operator_save_result(mission_id="mission_save_api", raw_text="save:   ", write_operator_save_artifact=_fake_writer)
    valid = save_api.build_operator_save_result(mission_id="mission_save_api", raw_text="save: bounded note", write_operator_save_artifact=_fake_writer)

    _assert(empty == (400, {"ok": False, "kind": "operator_save", "message": "Empty save. Nothing written."}), f"empty save response changed: {empty}")
    _assert(valid == (200, {"ok": True, "kind": "operator_save", "artifact_path": "workbench/missions/mission_save_api/notes/mirror/fake.json", "message": "Saved to mirror."}), f"valid save response changed: {valid}")
    _assert(calls == [("mission_save_api", "bounded note")], f"writer should be called exactly once for non-empty save: {calls}")


def main() -> int:
    _test_extract_save_text_and_result_shape()
    print("save_api_unit_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
