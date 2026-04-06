from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from dashboard_api import (
    EXPEDITIONS_ACTIVE_DIR,
    WORKBENCH_MISSIONS_DIR,
    _apply_control_tower_intervention,
    _build_expedition_detail,
    _create_mission_brief,
    _ensure_workbench_structure,
    _list_expeditions,
    _mission_parking_path,
    _write_parking_status,
)
from state_machine import write_state


def _make_mission_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _cleanup(mission_id: str) -> None:
    shutil.rmtree(EXPEDITIONS_ACTIVE_DIR / mission_id, ignore_errors=True)
    shutil.rmtree(WORKBENCH_MISSIONS_DIR / mission_id, ignore_errors=True)


def _create_test_mission(mission_id: str, objective: str) -> None:
    (EXPEDITIONS_ACTIVE_DIR / mission_id).mkdir(parents=True, exist_ok=True)
    _ensure_workbench_structure(mission_id)
    write_state(mission_id, "MISSION_DEFINED")
    _create_mission_brief(mission_id, objective)


def test_archive_candidate_marker_is_non_destructive() -> None:
    mission_id = _make_mission_id("feed_archive")
    try:
        _create_test_mission(mission_id, "Feed archive smoke mission")
        result = _apply_control_tower_intervention(
            mission_id,
            action="mark_archive_candidate",
            reason="smoke test archive dismiss",
        )
        assert result["ok"] is True
        changed_paths = result["intervention"]["changed_paths"]
        assert any(path.endswith("archive_candidate.json") for path in changed_paths)
        assert all("memory/collective" not in path.replace("\\", "/") for path in changed_paths)
        assert (EXPEDITIONS_ACTIVE_DIR / mission_id).exists(), "archive mark must not delete mission"
        _, grouped_counts = _list_expeditions()
        assert grouped_counts["queue_summary"]["archive_close_candidates"] >= 1
        detail = _build_expedition_detail(mission_id)
        assert detail["queue_hygiene"]["archive_candidate"] is True
    finally:
        _cleanup(mission_id)


def test_parked_mission_stays_retrievable() -> None:
    mission_id = _make_mission_id("feed_park")
    try:
        _create_test_mission(mission_id, "Feed parked smoke mission")
        parking = _write_parking_status(
            mission_id,
            status="parked",
            reason="smoke test parked dismiss",
            parked_by="operator",
            resume_hint="resume from smoke test",
        )
        assert parking["status"] == "parked"
        assert _mission_parking_path(mission_id).exists()
        assert (EXPEDITIONS_ACTIVE_DIR / mission_id).exists(), "parked mission must still exist"
        detail = _build_expedition_detail(mission_id)
        assert detail["parking_status"]["status"] == "parked"
        assert detail["queue_hygiene"]["parked_candidate"] is True
    finally:
        _cleanup(mission_id)


if __name__ == "__main__":
    test_archive_candidate_marker_is_non_destructive()
    test_parked_mission_stays_retrievable()
    print("feed dismiss smoke tests passed")
