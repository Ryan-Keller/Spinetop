from __future__ import annotations

from typing import Any, Callable

import mission_storage


def extract_save_text(message: str) -> str | None:
    raw_message = str(message or "").strip()
    if not raw_message.lower().startswith("save:"):
        return None
    return raw_message[len("save:"):].strip()


def build_operator_save_response(artifact: dict[str, Any]) -> dict[str, Any]:
    artifact_path = str(artifact.get("path") or "").strip()
    status_message = "Saved to mirror."
    return {
        "kind": "operator_save",
        "save_detected": True,
        "mirror_artifact_written": True,
        "artifact_path": artifact_path,
        "message": status_message,
        "mirror_artifact": artifact,
    }


def build_operator_save_empty_response() -> dict[str, Any]:
    status_message = "Nothing to save. Nothing was written."
    return {
        "ok": False,
        "kind": "operator_save",
        "save_detected": True,
        "mirror_artifact_written": False,
        "artifact_path": "",
        "message": status_message,
        "error": status_message,
    }


def build_operator_save_result(
    *,
    mission_id: str,
    raw_text: str,
    write_operator_save_artifact: Callable[[str, str], str] = mission_storage.write_operator_save_artifact,
) -> tuple[int, dict[str, Any]] | None:
    content = extract_save_text(raw_text)
    if content is None:
        return None
    if not content:
        return 400, {
            "ok": False,
            "kind": "operator_save",
            "message": "Empty save. Nothing written.",
        }
    artifact_path = write_operator_save_artifact(mission_id, content)
    return 200, {
        "ok": True,
        "kind": "operator_save",
        "artifact_path": artifact_path,
        "message": "Saved to mirror.",
    }
