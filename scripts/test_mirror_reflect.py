from __future__ import annotations

import json
import tempfile
from pathlib import Path

import mirror_reflect


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def main() -> int:
    mission_id = "mirror_test_mission"
    temp_root = Path(tempfile.mkdtemp(prefix="mirror_reflect_"))
    mission_root = temp_root / "workbench" / "missions" / mission_id
    notes_root = mission_root / "notes"
    mirror_root = notes_root / "mirror"
    memory_root = temp_root / "memory" / "drafts"

    chat_path = notes_root / "chat.jsonl"
    status_path = memory_root / "parking_status.json"

    _write_jsonl(
        chat_path,
        [
            {
                "sender": "assistant",
                "message": "Do you want me to open the review preview and keep it pending?",
                "created_at": "2026-04-05T07:05:03Z",
            },
            {
                "sender": "user",
                "message": "Proceed",
                "created_at": "2026-04-05T07:05:10Z",
            },
            {
                "sender": "assistant",
                "message": "Do you want me to open the review preview and keep it pending?",
                "created_at": "2026-04-05T07:05:48Z",
            },
            {
                "sender": "user",
                "message": "No",
                "created_at": "2026-04-05T07:06:26Z",
            },
            {
                "sender": "user",
                "message": "Answer blockers",
                "created_at": "2026-04-05T07:05:52Z",
            },
            {
                "sender": "user",
                "message": "Answer blockers",
                "created_at": "2026-04-05T07:05:58Z",
            },
        ],
    )
    _write_json(
        status_path,
        {
            "mission_id": mission_id,
            "status": "active",
            "reason": "no",
            "updated_at": "2026-04-05T07:06:26Z",
        },
    )

    original_root = mirror_reflect.ROOT
    original_read_roots = mirror_reflect.APPROVED_READ_ROOTS
    original_output_root = mirror_reflect.ALLOWED_OUTPUT_ROOT
    original_forbidden = mirror_reflect.FORBIDDEN_WRITE_ROOTS
    try:
        mirror_reflect.ROOT = temp_root
        mirror_reflect.APPROVED_READ_ROOTS = [
            temp_root / "workbench" / "missions",
            temp_root / "logs",
            temp_root / "memory",
        ]
        mirror_reflect.ALLOWED_OUTPUT_ROOT = temp_root / "workbench" / "missions"
        mirror_reflect.FORBIDDEN_WRITE_ROOTS = [
            temp_root / "services" / "honcho",
            temp_root / "memory" / "collective",
            temp_root / "memory" / "dispatch" / "approved",
        ]

        items = mirror_reflect.load_memory_items(
            [
                "workbench/missions/mirror_test_mission/notes/chat.jsonl",
                "memory/drafts/parking_status.json",
            ]
        )
        reflection = mirror_reflect.build_reflection(items)
        output_path = mirror_reflect.resolve_output_path(
            mission_id,
            "workbench/missions/mirror_test_mission/notes/mirror/reflection.json",
        )
        _assert(output_path is not None, "expected valid mirror output path")
        mirror_reflect.write_reflection(output_path, reflection)
    finally:
        mirror_reflect.ROOT = original_root
        mirror_reflect.APPROVED_READ_ROOTS = original_read_roots
        mirror_reflect.ALLOWED_OUTPUT_ROOT = original_output_root
        mirror_reflect.FORBIDDEN_WRITE_ROOTS = original_forbidden

    _assert(reflection["kind"] == "mirror_reflection", "reflection kind mismatch")
    for key in ("summary", "patterns", "contradictions", "gaps", "suggested_focus"):
        _assert(key in reflection, f"missing reflection field: {key}")
    _assert(any("Repeated" in item for item in reflection["patterns"]), "expected repeated-signal pattern")
    _assert(any("affirmative and negative control signals" in item for item in reflection["contradictions"]), "expected contradiction detection")
    _assert(any("high-context user language" in item for item in reflection["gaps"]), "expected missing-context gap")
    _assert("task" not in reflection["summary"].lower(), "summary drifted into task-answer framing")
    _assert(output_path.exists(), "reflection output file was not written")

    try:
        mirror_reflect.ROOT = temp_root
        mirror_reflect.ALLOWED_OUTPUT_ROOT = temp_root / "workbench" / "missions"
        mirror_reflect.FORBIDDEN_WRITE_ROOTS = [
            temp_root / "services" / "honcho",
            temp_root / "memory" / "collective",
            temp_root / "memory" / "dispatch" / "approved",
        ]
        mirror_reflect.resolve_output_path(
            mission_id,
            "services/honcho/reflection.json",
        )
    except mirror_reflect.MirrorReflectError:
        pass
    else:
        raise AssertionError("Mirror should reject Honcho-adjacent output paths")
    finally:
        mirror_reflect.ROOT = original_root
        mirror_reflect.ALLOWED_OUTPUT_ROOT = original_output_root
        mirror_reflect.FORBIDDEN_WRITE_ROOTS = original_forbidden

    print("mirror_reflect_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
