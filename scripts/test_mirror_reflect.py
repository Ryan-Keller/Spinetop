from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

import helper_model_runtime
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


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            rows.append(json.loads(text))
    return rows


class _PatchAttr:
    def __init__(self, module, name: str, value):
        self.module = module
        self.name = name
        self.value = value
        self.original = getattr(module, name)

    def __enter__(self):
        setattr(self.module, self.name, self.value)
        return self

    def __exit__(self, exc_type, exc, tb):
        setattr(self.module, self.name, self.original)
        return False


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

    enabled_profile = replace(helper_model_runtime.load_helper_runtime_profile("spinetop-mirror"), active=True)
    original_profile = mirror_reflect.PROFILE
    original_root = mirror_reflect.ROOT
    original_read_roots = mirror_reflect.APPROVED_READ_ROOTS
    original_output_root = mirror_reflect.ALLOWED_OUTPUT_ROOT
    original_forbidden = mirror_reflect.FORBIDDEN_WRITE_ROOTS
    original_model_log = mirror_reflect.MIRROR_MODEL_LOG
    try:
        mirror_reflect.PROFILE = enabled_profile
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
        mirror_reflect.MIRROR_MODEL_LOG = temp_root / "logs" / "support" / "mirror_model_invocations.jsonl"

        items = mirror_reflect.load_memory_items(
            [
                "workbench/missions/mirror_test_mission/notes/chat.jsonl",
                "memory/drafts/parking_status.json",
            ]
        )
        calls: list[dict] = []

        def _fake_invoke(model_key: str, prompt: str, runtime_config: dict, **kwargs) -> str:
            calls.append({"model_key": model_key, "prompt": prompt, "kwargs": kwargs})
            return json.dumps(
                {
                    "summary": "The memory shows a stalled coordination loop where repeated prompts outrun stable user intent.",
                    "patterns": [
                        "The same review-preview question repeats, so the session keeps reopening the same decision frame.",
                        "Short user replies dominate, which leaves the memory heavy on signals and light on rationale.",
                    ],
                    "contradictions": [
                        "The user alternates between proceed and no, so consent appears unstable across adjacent turns."
                    ],
                    "gaps": [
                        "There is no fuller explanation for why blockers matter, so the mission context stays thin."
                    ],
                    "suggested_focus": [
                        "Clarify the user intent behind the review-preview loop before interpreting later turns.",
                        "Look for mission-local artifacts that explain the blocker language.",
                    ],
                }
            )

        with _PatchAttr(mirror_reflect, "invoke_model", _fake_invoke):
            reflection = mirror_reflect.build_reflection(items)
        output_path = mirror_reflect.resolve_output_path(
            mission_id,
            "workbench/missions/mirror_test_mission/notes/mirror/reflection.json",
        )
        _assert(output_path is not None, "expected valid mirror output path")
        mirror_reflect.write_reflection(output_path, reflection)
    finally:
        mirror_reflect.PROFILE = original_profile
        mirror_reflect.ROOT = original_root
        mirror_reflect.APPROVED_READ_ROOTS = original_read_roots
        mirror_reflect.ALLOWED_OUTPUT_ROOT = original_output_root
        mirror_reflect.FORBIDDEN_WRITE_ROOTS = original_forbidden
        mirror_reflect.MIRROR_MODEL_LOG = original_model_log

    _assert(reflection["kind"] == "mirror_reflection", "reflection kind mismatch")
    for key in ("summary", "patterns", "contradictions", "gaps", "suggested_focus"):
        _assert(key in reflection, f"missing reflection field: {key}")
    _assert(calls, "model-backed Mirror should invoke the shared model seam")
    _assert("stalled coordination loop" in reflection["summary"], "expected model-generated summary")
    _assert(reflection["model_binding"]["source"] == "model", "expected active model binding")
    _assert("task" not in reflection["summary"].lower(), "summary drifted into task-answer framing")
    _assert(output_path.exists(), "reflection output file was not written")
    model_logs = _read_jsonl(temp_root / "logs" / "support" / "mirror_model_invocations.jsonl")
    _assert(len(model_logs) == 1, f"expected one model invocation log entry, got {model_logs}")
    _assert(str(model_logs[0].get("status") or "") == "success", f"model success should log success: {model_logs[0]}")
    _assert(not (temp_root / "services" / "honcho").exists(), "Mirror should not write into Honcho paths")

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

    disabled_profile = replace(
        helper_model_runtime.load_helper_runtime_profile("spinetop-mirror"),
        active=False,
    )
    try:
        mirror_reflect.PROFILE = disabled_profile
        mirror_reflect.ROOT = temp_root
        mirror_reflect.APPROVED_READ_ROOTS = [
            temp_root / "workbench" / "missions",
            temp_root / "logs",
            temp_root / "memory",
        ]
        mirror_reflect.MIRROR_MODEL_LOG = temp_root / "logs" / "support" / "mirror_model_disabled.jsonl"
        disabled_items = mirror_reflect.load_memory_items(
            [
                "workbench/missions/mirror_test_mission/notes/chat.jsonl",
                "memory/drafts/parking_status.json",
            ]
        )

        def _unexpected_invoke(*args, **kwargs):
            raise AssertionError("disabled-safe Mirror fallback should not invoke the model")

        with _PatchAttr(mirror_reflect, "invoke_model", _unexpected_invoke):
            disabled_reflection = mirror_reflect.build_reflection(disabled_items)
    finally:
        mirror_reflect.PROFILE = original_profile
        mirror_reflect.ROOT = original_root
        mirror_reflect.APPROVED_READ_ROOTS = original_read_roots
        mirror_reflect.MIRROR_MODEL_LOG = original_model_log

    _assert(disabled_reflection["model_binding"]["source"] == "disabled_safe_scripted_fallback", "expected disabled-safe fallback binding")
    _assert(any("Repeated" in item for item in disabled_reflection["patterns"]), "expected scripted repeated-signal fallback")
    _assert(not (temp_root / "logs" / "support" / "mirror_model_disabled.jsonl").exists(), "disabled-safe fallback should not log model invocations")

    failure_profile = replace(helper_model_runtime.load_helper_runtime_profile("spinetop-mirror"), active=True)
    try:
        mirror_reflect.PROFILE = failure_profile
        mirror_reflect.ROOT = temp_root
        mirror_reflect.APPROVED_READ_ROOTS = [
            temp_root / "workbench" / "missions",
            temp_root / "logs",
            temp_root / "memory",
        ]
        mirror_reflect.MIRROR_MODEL_LOG = temp_root / "logs" / "support" / "mirror_model_failure.jsonl"
        failure_items = mirror_reflect.load_memory_items(
            [
                "workbench/missions/mirror_test_mission/notes/chat.jsonl",
                "memory/drafts/parking_status.json",
            ]
        )

        def _failing_invoke(*args, **kwargs):
            raise RuntimeError("timeout from fake provider")

        with _PatchAttr(mirror_reflect, "invoke_model", _failing_invoke):
            failure_reflection = mirror_reflect.build_reflection(failure_items)
    finally:
        mirror_reflect.PROFILE = original_profile
        mirror_reflect.ROOT = original_root
        mirror_reflect.APPROVED_READ_ROOTS = original_read_roots
        mirror_reflect.MIRROR_MODEL_LOG = original_model_log

    _assert(
        failure_reflection["model_binding"]["source"] == "model_failure_fallback",
        "expected model failure fallback binding",
    )
    _assert(
        any("affirmative and negative control signals" in item for item in failure_reflection["contradictions"]),
        "expected scripted contradiction fallback after model failure",
    )
    failure_logs = _read_jsonl(temp_root / "logs" / "support" / "mirror_model_failure.jsonl")
    _assert(len(failure_logs) == 1, f"expected one failure log entry, got {failure_logs}")
    _assert(str(failure_logs[0].get("status") or "") == "failure", f"expected failed model invocation log: {failure_logs}")

    print("mirror_reflect_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
