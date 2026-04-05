from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

import dashboard_api
import state_machine


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@contextmanager
def _patched_roots(temp_root: Path):
    expedition_root = temp_root / "expeditions" / "active"
    workbench_root = temp_root / "workbench" / "missions"
    support_orch_root = temp_root / "logs" / "support" / "orchestration"
    support_retrieval_root = temp_root / "logs" / "support" / "retrieval"
    patches = [
        (state_machine, "ROOT", temp_root),
        (state_machine, "EXPEDITIONS_ACTIVE_DIR", expedition_root),
        (dashboard_api, "ROOT", temp_root),
        (dashboard_api, "EXPEDITIONS_ACTIVE_DIR", expedition_root),
        (dashboard_api, "WORKBENCH_MISSIONS_DIR", workbench_root),
        (dashboard_api, "SUPPORT_ORCHESTRATION_DIR", support_orch_root),
        (dashboard_api, "SUPPORT_RETRIEVAL_DIR", support_retrieval_root),
        (dashboard_api, "SUPPORT_ORCHESTRATION_INSTANCES_DIR", support_orch_root / "instances"),
        (dashboard_api, "SUPPORT_RETRIEVAL_INSTANCES_DIR", support_retrieval_root / "instances"),
        (dashboard_api, "HERMES_RUNS_DIR", temp_root / "logs" / "hermes" / "runs"),
        (dashboard_api, "CLARIFICATION_PACKETS_DIR", temp_root / "logs" / "citadel" / "clarification_packets"),
        (dashboard_api, "MEMORY_DIR", temp_root / "memory"),
        (dashboard_api, "DISPATCH_DIR", temp_root / "memory" / "dispatch"),
        (dashboard_api, "GOVERNANCE_DIR", temp_root / "logs" / "governance"),
        (dashboard_api, "COMPACTOR_LOG_DIR", temp_root / "logs" / "compactor"),
        (dashboard_api, "ARCHIVE_DIR", temp_root / "memory" / "archive"),
        (dashboard_api, "COMPACTED_DIR", temp_root / "memory" / "compacted"),
        (dashboard_api, "PROMOTION_DIR", temp_root / "memory" / "promotion"),
        (dashboard_api, "INBOX_DIR", temp_root / "memory" / "inbox"),
        (dashboard_api, "EVENT_LOG", temp_root / "logs" / "topology" / "events.jsonl"),
    ]
    originals = [(module, name, getattr(module, name)) for module, name, _ in patches]
    try:
        for module, name, value in patches:
            setattr(module, name, value)
        yield
    finally:
        for module, name, value in originals:
            setattr(module, name, value)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _file_snapshot(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    snapshot: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        snapshot[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return snapshot


def main() -> int:
    mission_id = "mission_20260405T150500Z_assumptions"
    temp_root = Path(tempfile.mkdtemp(prefix="assumption_ledger_smoke_"))
    expedition_dir = temp_root / "expeditions" / "active" / mission_id
    workbench_dir = temp_root / "workbench" / "missions" / mission_id

    _write_json(
        expedition_dir / "mission_brief.json",
        {
            "mission_id": mission_id,
            "objective": "write a python csv script",
            "task_text": "write a python csv script",
            "created_at": "2026-04-05T15:05:00Z",
            "latest_run_id": "",
        },
    )
    _write_json(
        expedition_dir / "state.json",
        {
            "mission_id": mission_id,
            "current_state": "CLARIFICATION_NEEDED",
            "updated_at": "2026-04-05T15:05:00Z",
        },
    )
    _write_json(
        expedition_dir / "artifact_index.json",
        {
            "mission_id": mission_id,
            "items": [],
        },
    )
    (workbench_dir / "notes").mkdir(parents=True, exist_ok=True)
    (workbench_dir / "notes" / "chat.jsonl").write_text("", encoding="utf-8")

    ledger_path = workbench_dir / "notes" / "assumptions" / "ledger.json"
    with _patched_roots(temp_root):
        client = dashboard_api.app.test_client()

        before_get = _file_snapshot(temp_root)
        get_before = client.get(f"/api/expeditions/{mission_id}")
        _assert(get_before.status_code == 200, f"mission detail GET failed with {get_before.status_code}")
        after_get = _file_snapshot(temp_root)
        _assert(before_get == after_get, "GET mission detail should be read-only")
        _assert(not ledger_path.exists(), "GET should not create an assumption ledger")

        before_refresh = _file_snapshot(temp_root)
        refresh_res = client.post(f"/api/expeditions/{mission_id}/refresh-assumptions")
        _assert(refresh_res.status_code == 200, f"refresh assumptions failed with {refresh_res.status_code}")
        refresh_payload = refresh_res.get_json() or {}
        item = refresh_payload.get("item") if isinstance(refresh_payload, dict) else None
        _assert(isinstance(item, dict), "refresh response missing mission detail")
        _assert(ledger_path.exists(), "refresh should create the mission-local assumption ledger")
        after_refresh = _file_snapshot(temp_root)
        changed_refresh = {path for path in after_refresh if before_refresh.get(path) != after_refresh.get(path)}
        _assert(changed_refresh == {ledger_path.relative_to(temp_root).as_posix()}, f"refresh wrote outside assumptions ledger: {changed_refresh}")
        assumptions = list(item.get("assumptions") or [])
        _assert(len(assumptions) >= 1, "refresh should surface at least one assumption")
        _assert(item.get("active_assumption_count") == 1, f"unexpected active assumption count: {item.get('active_assumption_count')}")

        assumption_id = str(assumptions[0].get("assumption_id") or "")
        _assert(assumption_id, "derived assumption is missing an assumption_id")

        before_get_after_refresh = _file_snapshot(temp_root)
        get_after_refresh = client.get(f"/api/expeditions/{mission_id}")
        _assert(get_after_refresh.status_code == 200, f"mission detail GET after refresh failed with {get_after_refresh.status_code}")
        after_get_after_refresh = _file_snapshot(temp_root)
        _assert(before_get_after_refresh == after_get_after_refresh, "GET after refresh should remain read-only")

        before_confirm = _file_snapshot(temp_root)
        confirm_res = client.post(
            f"/api/expeditions/{mission_id}/assumptions/{assumption_id}/confirm",
            json={"operator_note": "accepted in smoke test"},
        )
        _assert(confirm_res.status_code == 200, f"confirm failed with {confirm_res.status_code}")
        after_confirm = _file_snapshot(temp_root)
        changed_confirm = {path for path in after_confirm if before_confirm.get(path) != after_confirm.get(path)}
        _assert(changed_confirm == {ledger_path.relative_to(temp_root).as_posix()}, f"confirm wrote outside assumptions ledger: {changed_confirm}")
        accepted_payload = confirm_res.get_json() or {}
        accepted = accepted_payload.get("assumption") if isinstance(accepted_payload, dict) else None
        _assert(isinstance(accepted, dict) and accepted.get("status") == "accepted", "confirm did not mark the assumption accepted")

        before_reject = _file_snapshot(temp_root)
        reject_res = client.post(
            f"/api/expeditions/{mission_id}/assumptions/{assumption_id}/reject",
            json={"operator_note": "rejected in smoke test"},
        )
        _assert(reject_res.status_code == 200, f"reject failed with {reject_res.status_code}")
        after_reject = _file_snapshot(temp_root)
        changed_reject = {path for path in after_reject if before_reject.get(path) != after_reject.get(path)}
        _assert(changed_reject == {ledger_path.relative_to(temp_root).as_posix()}, f"reject wrote outside assumptions ledger: {changed_reject}")
        rejected_payload = reject_res.get_json() or {}
        rejected = rejected_payload.get("assumption") if isinstance(rejected_payload, dict) else None
        _assert(isinstance(rejected, dict) and rejected.get("status") == "rejected", "reject did not mark the assumption rejected")

    print("assumption_ledger_smoke_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
