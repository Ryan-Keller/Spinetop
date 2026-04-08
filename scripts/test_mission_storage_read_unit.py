from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

import mission_storage_core as core
import mission_storage_read as read_ops


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


def _test_readers_normalize_and_sort() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="mission_storage_read_"))
    mission_id = "mission_read_unit"
    with _patched_root(temp_root):
        core._ensure_workbench_structure(mission_id)
        core._write_json(
            core._mirror_dir(mission_id, ensure=True) / "older.json",
            {"artifact_id": "older", "text": "older note", "created_at": "2026-04-07T00:00:00+00:00"},
        )
        core._write_json(
            core._mirror_dir(mission_id, ensure=True) / "newer.json",
            {"artifact_id": "newer", "summary": "newer note", "created_at": "2026-04-07T01:00:00+00:00"},
        )
        core._write_json(
            core._agent_runs_dir(mission_id, ensure=True) / "run_001.json",
            {
                "run_id": "run_001",
                "role": "spinetop-mirror",
                "created_at": "2026-04-07T01:05:00+00:00",
                "output": {"result": "mirror summary", "confidence": 0.7},
            },
        )
        core._write_json(
            core._retry_ledger_path(mission_id, ensure=True),
            {
                "mission_id": mission_id,
                "retry_budget_total": 2,
                "retry_budget_used": 5,
                "decision_log": [{"decision": "blocked", "why_blocked": "budget"}],
            },
        )
        intake_dir = core._ensure_workbench_structure(mission_id) / "intake"
        core._write_json(
            intake_dir / "input_001.json",
            {"input_id": "input_001", "mission_id": mission_id, "content": "operator input", "created_at": "2026-04-07T01:06:00+00:00"},
        )

        mirror_notes = read_ops._read_mirror_notes(mission_id)
        agent_runs = read_ops._read_agent_runs(mission_id)
        retry_ledger = read_ops._read_retry_ledger(mission_id)
        mission_inputs = read_ops._mission_inputs(mission_id)

        _assert([item["artifact_id"] for item in mirror_notes] == ["newer", "older"], f"mirror notes should be newest-first: {mirror_notes}")
        _assert(agent_runs[0]["summary"] == "mirror summary", f"agent run summary should fall back to output.result: {agent_runs}")
        _assert(retry_ledger["retry_budget_used"] == 2, f"retry budget should be capped at total: {retry_ledger}")
        _assert(mission_inputs[0]["content"] == "operator input", f"mission input content missing: {mission_inputs}")


def main() -> int:
    _test_readers_normalize_and_sort()
    print("mission_storage_read_unit_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
