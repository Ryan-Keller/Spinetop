from __future__ import annotations

import json
import shutil
from pathlib import Path

import agent_invocation
import dashboard_api


ROOT = Path(__file__).resolve().parents[1]
EXPEDITIONS_ACTIVE_DIR = ROOT / "expeditions" / "active"
WORKBENCH_MISSIONS_DIR = ROOT / "workbench" / "missions"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _cleanup(mission_id: str) -> None:
    shutil.rmtree(EXPEDITIONS_ACTIVE_DIR / mission_id, ignore_errors=True)
    shutil.rmtree(WORKBENCH_MISSIONS_DIR / mission_id, ignore_errors=True)


def main() -> int:
    mission_id = f"mission_agent_invocation_smoke_{agent_invocation.utc_stamp().lower()}"
    expedition_root = EXPEDITIONS_ACTIVE_DIR / mission_id
    workbench_root = WORKBENCH_MISSIONS_DIR / mission_id

    try:
        expedition_root.mkdir(parents=True, exist_ok=True)
        (workbench_root / "notes").mkdir(parents=True, exist_ok=True)
        _write_json(expedition_root / "mission_brief.json", {
            "mission_id": mission_id,
            "objective": "Produce an explicit first pass and then a review artifact.",
            "task_text": "Produce an explicit first pass and then a review artifact.",
            "created_at": dashboard_api.iso_now(),
            "status": "active",
            "latest_run_id": "",
        })
        _write_json(expedition_root / "state.json", {
            "mission_id": mission_id,
            "current_state": "EXPEDITION_ACTIVE",
            "updated_at": dashboard_api.iso_now(),
        })
        _write_json(expedition_root / "artifact_index.json", {"mission_id": mission_id, "items": []})
        dashboard_api._create_mission_agent_identity(mission_id, "Produce an explicit first pass and then a review artifact.")

        original_invoke = agent_invocation.invoke_model
        try:
            def _fake_invoke(model_key: str, prompt: str, runtime_config: dict, **kwargs: object) -> str:
                payload = json.loads(prompt)
                return json.dumps({
                    "role": "spinetop-sentinel",
                    "mission_id": mission_id,
                    "result": f"Reviewed explicit invocation for {payload['mission']['objective']}",
                    "confidence": 0.81,
                    "next_step": "Store this review as a mission-local derived artifact.",
                    "derived_only": True,
                })

            agent_invocation.invoke_model = _fake_invoke
            sentinel = agent_invocation.invoke_role(
                "spinetop-sentinel",
                mission_id,
                {"trigger_reason": "smoke_test_review", "input": "review the first pass artifact when present"},
            )
        finally:
            agent_invocation.invoke_model = original_invoke

        _assert(sentinel["ok"] is True, f"sentinel invocation should succeed: {sentinel}")
        _assert(sentinel["output"]["role"] == "spinetop-sentinel", f"unexpected sentinel role output: {sentinel}")
        _assert((workbench_root / "notes" / "agent_runs").exists(), "agent_runs directory should be created")

        mirror = agent_invocation.invoke_role(
            "spinetop-mirror",
            mission_id,
            {"trigger_reason": "smoke_test_mirror_review", "input": "review the mission-local notes in bounded read-only mode"},
        )
        _assert(mirror["ok"] is False, "inactive mirror should stay disabled-safe")
        _assert(mirror["status"] == "inactive", f"expected inactive status: {mirror}")
        _assert(mirror["output"]["derived_only"] is True, "disabled-safe output must stay derived-only")

        detail = dashboard_api._build_expedition_detail(mission_id)
        latest_role_activity = ((detail.get("control_tower_summary") or {}) if isinstance(detail, dict) else {}).get("latest_role_activity") or {}
        _assert(str(latest_role_activity.get("kind") or "") == "agent_run", f"latest role activity should come from agent runs: {latest_role_activity}")
        _assert(str(latest_role_activity.get("role") or "") in {"Sentinel", "Mirror"}, f"unexpected latest role label: {latest_role_activity}")
        _assert(int(detail.get("agent_run_count") or 0) >= 2, f"expected two agent runs in detail: {detail.get('agent_run_count')}")

        print(f"mission_id={mission_id}")
        print("agent_invocation_smoke_ok")
        return 0
    finally:
        _cleanup(mission_id)


if __name__ == "__main__":
    raise SystemExit(main())
