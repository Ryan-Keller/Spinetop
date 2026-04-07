from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

import dashboard_api
import governance_utils
import mission_storage
import role_test_sandbox
import state_machine


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


@contextmanager
def _patched_roots(temp_root: Path):
    expedition_root = temp_root / "expeditions" / "active"
    workbench_root = temp_root / "workbench" / "missions"
    governance_root = temp_root / "logs" / "governance"
    nanny_status_path = temp_root / "logs" / "nanny" / "item_world_status.json"
    patches = [
        (state_machine, "ROOT", temp_root),
        (state_machine, "EXPEDITIONS_ACTIVE_DIR", expedition_root),
        (dashboard_api, "ROOT", temp_root),
        (dashboard_api, "EXPEDITIONS_ACTIVE_DIR", expedition_root),
        (dashboard_api, "WORKBENCH_MISSIONS_DIR", workbench_root),
        (dashboard_api, "HERMES_RUNS_DIR", temp_root / "logs" / "hermes" / "runs"),
        (dashboard_api, "CLARIFICATION_PACKETS_DIR", temp_root / "logs" / "citadel" / "clarification_packets"),
        (dashboard_api, "SUPPORT_ORCHESTRATION_DIR", temp_root / "logs" / "support" / "orchestration"),
        (dashboard_api, "SUPPORT_RETRIEVAL_DIR", temp_root / "logs" / "support" / "retrieval"),
        (dashboard_api, "SUPPORT_ORCHESTRATION_INSTANCES_DIR", temp_root / "logs" / "support" / "orchestration" / "instances"),
        (dashboard_api, "SUPPORT_RETRIEVAL_INSTANCES_DIR", temp_root / "logs" / "support" / "retrieval" / "instances"),
        (dashboard_api, "MEMORY_DIR", temp_root / "memory"),
        (dashboard_api, "DISPATCH_DIR", temp_root / "memory" / "dispatch"),
        (dashboard_api, "GOVERNANCE_DIR", governance_root),
        (dashboard_api, "COMPACTOR_LOG_DIR", temp_root / "logs" / "compactor"),
        (dashboard_api, "ARCHIVE_DIR", temp_root / "memory" / "archive"),
        (dashboard_api, "COMPACTED_DIR", temp_root / "memory" / "compacted"),
        (dashboard_api, "PROMOTION_DIR", temp_root / "memory" / "promotion"),
        (dashboard_api, "INBOX_DIR", temp_root / "memory" / "inbox"),
        (dashboard_api, "EVENT_LOG", temp_root / "logs" / "topology" / "events.jsonl"),
        (mission_storage, "ROOT", temp_root),
        (mission_storage, "EXPEDITIONS_ACTIVE_DIR", expedition_root),
        (mission_storage, "WORKBENCH_MISSIONS_DIR", workbench_root),
        (governance_utils, "ROOT", temp_root),
        (governance_utils, "GOVERNANCE_DIR", governance_root),
        (governance_utils, "NANNY_STATUS_PATH", nanny_status_path),
        (governance_utils, "DISPATCH_DIR", temp_root / "memory" / "dispatch"),
    ]
    originals = [(module, name, getattr(module, name)) for module, name, _ in patches]
    try:
        for module, name, value in patches:
            setattr(module, name, value)
        yield
    finally:
        for module, name, value in originals:
            setattr(module, name, value)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="role_test_sandbox_"))

    with _patched_roots(temp_root):
        created = role_test_sandbox.create_sandbox_mission()
        mission_id = str(created.get("mission_id") or "")
        inspection = created.get("inspection") if isinstance(created.get("inspection"), dict) else {}

        _assert(mission_id, "create should return a mission id")
        _assert(str(created.get("objective") or "").startswith("Sandbox role validation:"), f"unexpected objective: {created}")
        _assert(bool(inspection.get("is_clean")), f"fresh sandbox should be clean: {inspection}")
        _assert(bool(inspection.get("is_marked_sandbox")), f"fresh sandbox should be marked: {inspection}")

        marker_path = temp_root / str(created.get("marker_path") or "")
        _assert(marker_path.exists(), f"marker file missing: {marker_path}")

        parked_path = temp_root / "workbench" / "missions" / mission_id / "notes" / "parking_status.json"
        _write_json(
            parked_path,
            {
                "mission_id": mission_id,
                "status": "parked",
                "reason": "operator paused the mission",
                "parked_at": "2026-04-06T10:00:00Z",
                "parked_by": "operator",
                "resume_hint": "resume explicitly",
                "updated_at": "2026-04-06T10:00:00Z",
            },
        )

        noisy = role_test_sandbox.inspect_sandbox_mission(mission_id)
        _assert(not bool(noisy.get("is_clean")), f"parked sandbox should no longer be clean: {noisy}")
        _assert(noisy.get("clean_checks", {}).get("not_parked") is False, f"parked check should fail: {noisy}")

    print("role_test_sandbox_smoke_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
