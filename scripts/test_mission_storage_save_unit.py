from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

import mission_storage_core as core
import mission_storage_save as save_ops


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


def _test_save_writers_preserve_paths() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="mission_storage_save_"))
    mission_id = "mission_save_unit"
    with _patched_root(temp_root):
        save_artifact = save_ops._write_operator_save_artifact(mission_id, "preserve this note")
        input_record = save_ops._write_mission_input(mission_id, "operator input")
        parked = save_ops._write_parking_status(mission_id, status="parked", reason="unit test")
        resumed = save_ops._write_parking_status(mission_id, status="active", reason="resume unit test")

        save_path = temp_root / str(save_artifact["path"])
        input_path = temp_root / str(input_record["path"])

        _assert(save_path.exists(), f"save artifact path missing: {save_artifact}")
        _assert("notes/mirror/" in save_artifact["path"], f"save artifact should stay in the mirror lane: {save_artifact}")
        _assert(input_path.exists(), f"mission input path missing: {input_record}")
        _assert("intake/" in input_record["path"], f"mission input should stay in intake/: {input_record}")
        _assert(parked["status"] == "parked" and bool(parked["parked_at"]), f"parked record should capture parked_at: {parked}")
        _assert(resumed["status"] == "active" and resumed["parked_by"] == "", f"resume should clear parked_by: {resumed}")


def main() -> int:
    _test_save_writers_preserve_paths()
    print("mission_storage_save_unit_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
