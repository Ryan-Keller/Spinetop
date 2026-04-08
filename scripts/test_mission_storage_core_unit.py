from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

import mission_storage_core as core


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


@contextmanager
def _patched_root(temp_root: Path):
    original_root = core.ROOT
    try:
        core.configure_root(temp_root)
        yield
    finally:
        core.configure_root(original_root)


def _test_path_layout_and_jsonl_primitives() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="mission_storage_core_"))
    mission_id = "mission_core_unit"
    with _patched_root(temp_root):
        mission_root = core._mission_root(mission_id)
        workbench_root = core._ensure_workbench_structure(mission_id)
        chat_path = core._mission_chat_path(mission_id, ensure=True)

        _assert(mission_root == temp_root / "expeditions" / "active" / mission_id, f"unexpected mission root: {mission_root}")
        _assert(workbench_root == temp_root / "workbench" / "missions" / mission_id, f"unexpected workbench root: {workbench_root}")
        _assert((workbench_root / "notes").exists(), "ensure_workbench_structure should create notes/")

        core._append_jsonl(chat_path, {"sender": "user", "message": "hello"})
        rows = core._read_jsonl(chat_path)
        _assert(rows == [{"sender": "user", "message": "hello"}], f"jsonl round-trip mismatch: {rows}")
        _assert(bool(core._latest_mtime([chat_path])), "latest_mtime should detect the written chat file")


def main() -> int:
    _test_path_layout_and_jsonl_primitives()
    print("mission_storage_core_unit_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
