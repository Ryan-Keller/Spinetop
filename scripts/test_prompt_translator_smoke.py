from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

import dashboard_api
import governance_utils
import prompt_translator
import state_machine


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _file_snapshot(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    snapshot: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        snapshot[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return snapshot


@contextmanager
def _patched_roots(temp_root: Path):
    expedition_root = temp_root / "expeditions" / "active"
    workbench_root = temp_root / "workbench" / "missions"
    memory_root = temp_root / "memory"
    governance_root = temp_root / "logs" / "governance"
    nanny_status_path = temp_root / "logs" / "nanny" / "item_world_status.json"
    patches = [
        (state_machine, "ROOT", temp_root),
        (state_machine, "EXPEDITIONS_ACTIVE_DIR", expedition_root),
        (dashboard_api, "ROOT", temp_root),
        (dashboard_api, "EXPEDITIONS_ACTIVE_DIR", expedition_root),
        (dashboard_api, "WORKBENCH_MISSIONS_DIR", workbench_root),
        (dashboard_api, "MEMORY_DIR", memory_root),
        (dashboard_api, "DISPATCH_DIR", memory_root / "dispatch"),
        (dashboard_api, "GOVERNANCE_DIR", governance_root),
        (dashboard_api, "EVENT_LOG", temp_root / "logs" / "topology" / "events.jsonl"),
        (dashboard_api, "HERMES_RUNS_DIR", temp_root / "logs" / "hermes" / "runs"),
        (dashboard_api, "CLARIFICATION_PACKETS_DIR", temp_root / "logs" / "citadel" / "clarification_packets"),
        (dashboard_api, "SUPPORT_ORCHESTRATION_DIR", temp_root / "logs" / "support" / "orchestration"),
        (dashboard_api, "SUPPORT_RETRIEVAL_DIR", temp_root / "logs" / "support" / "retrieval"),
        (dashboard_api, "SUPPORT_ORCHESTRATION_INSTANCES_DIR", temp_root / "logs" / "support" / "orchestration" / "instances"),
        (dashboard_api, "SUPPORT_RETRIEVAL_INSTANCES_DIR", temp_root / "logs" / "support" / "retrieval" / "instances"),
        (dashboard_api, "COMPACTOR_LOG_DIR", temp_root / "logs" / "compactor"),
        (dashboard_api, "ARCHIVE_DIR", memory_root / "archive"),
        (dashboard_api, "COMPACTED_DIR", memory_root / "compacted"),
        (dashboard_api, "PROMOTION_DIR", memory_root / "promotion"),
        (dashboard_api, "INBOX_DIR", memory_root / "inbox"),
        (governance_utils, "ROOT", temp_root),
        (governance_utils, "GOVERNANCE_DIR", governance_root),
        (governance_utils, "NANNY_STATUS_PATH", nanny_status_path),
        (governance_utils, "DISPATCH_DIR", memory_root / "dispatch"),
        (prompt_translator, "ROOT", temp_root),
        (prompt_translator, "WORKBENCH_MISSIONS_DIR", workbench_root),
    ]
    originals = [(module, name, getattr(module, name)) for module, name, _ in patches]
    try:
        for module, name, value in patches:
            setattr(module, name, value)
        yield
    finally:
        for module, name, value in originals:
            setattr(module, name, value)


def _seed_mission(root: Path, mission_id: str, objective: str) -> None:
    expedition_root = root / "expeditions" / "active" / mission_id
    _write_json(
        expedition_root / "state.json",
        {
            "mission_id": mission_id,
            "current_state": "CLARIFICATION_NEEDED",
            "updated_at": "2026-04-05T12:00:00+00:00",
        },
    )
    _write_json(
        expedition_root / "mission_brief.json",
        {
            "mission_id": mission_id,
            "objective": objective,
            "task_text": objective,
            "created_at": "2026-04-05T11:59:00+00:00",
            "status": "active",
            "latest_run_id": "",
        },
    )
    _write_json(expedition_root / "artifact_index.json", {"mission_id": mission_id, "items": []})
    _write_json(
        expedition_root / "working_memory.json",
        {
            "mission_id": mission_id,
            "latest_summary": "Waiting on a bounded next step.",
            "confirmed_facts": [],
            "open_questions": [],
            "deferred_questions": [],
            "updated_at": "2026-04-05T12:01:00+00:00",
            "operating_status": "blocked",
            "blocked_reason": "",
            "can_continue_without_input": False,
            "crew_status": "active",
            "expedition_activity": "running",
        },
    )


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="prompt_translator_smoke_"))
    mission_id = "mission_prompt_translator"

    with _patched_roots(temp_root):
        _seed_mission(temp_root, mission_id, "Investigate the current operator request safely")

        messy = prompt_translator.translate_and_store_prompt(
            "Can you take a first pass on the flaky release issue, maybe review the latest runner return, "
            "and keep it bounded to this mission until I confirm?",
            mission_id=mission_id,
        )
        _assert(messy["target_type"] == "existing_mission", f"unexpected target type: {messy}")
        _assert(messy["target_mission_id"] == mission_id, f"unexpected target mission: {messy}")
        _assert(messy["recommended_role"] == "sentinel", f"unexpected role: {messy}")
        _assert(messy["recommended_mode"] == "review", f"unexpected mode: {messy}")
        _assert(messy["scope"] == "read_only", f"unexpected scope: {messy}")
        _assert(messy["sufficiency"]["can_proceed"] is True, f"messy prompt should be sufficient: {messy}")
        _assert(messy["requires_operator_confirmation"] is False, f"bounded mission-local review should not require extra confirmation: {messy}")
        _assert("translated_instruction" in messy and str(messy["translated_instruction"]).strip(), "translated instruction missing")

        blocked = prompt_translator.translate_and_store_prompt("fix this code for me", mission_id=mission_id)
        _assert(blocked["recommended_mode"] == "clarify", f"missing-artifact prompt should clarify: {blocked}")
        _assert(blocked["sufficiency"]["can_proceed"] is False, f"missing-artifact prompt should block: {blocked}")
        missing = blocked["sufficiency"]["missing_requirements"]
        _assert(isinstance(missing, list) and missing and "code" in missing[0].lower(), f"missing requirement should mention code: {blocked}")
        _assert(blocked["requires_operator_confirmation"] is True, f"blocked translation should require operator review: {blocked}")

        before_snapshot = _file_snapshot(temp_root)
        stored = prompt_translator.translate_and_store_prompt("Please summarize this text", mission_id=mission_id)
        after_snapshot = _file_snapshot(temp_root)
        changed_paths = {path for path, content in after_snapshot.items() if before_snapshot.get(path) != content}
        _assert(len(changed_paths) == 1, f"translator should only write one file, changed={sorted(changed_paths)}")
        changed_path = next(iter(changed_paths))
        allowed_prefix = f"workbench/missions/{mission_id}/notes/prompt_translator/"
        _assert(changed_path.startswith(allowed_prefix), f"translator wrote outside mission-local lane: {changed_path}")
        _assert(not changed_path.startswith("memory/"), f"translator wrote into memory: {changed_path}")
        _assert(not changed_path.startswith("logs/governance/"), f"translator wrote into governance: {changed_path}")
        _assert(not (temp_root / "workbench" / "missions" / mission_id / "notes" / "triggers").exists(), "translator should not create triggers")
        _assert(stored["derived_only"] is True, f"translator result must stay derived-only: {stored}")

        detail = dashboard_api._build_expedition_detail(mission_id)
        latest = detail.get("latest_prompt_translation")
        _assert(isinstance(latest, dict), "mission detail should expose latest translator result")
        _assert(str(latest.get("translation_id") or "") == str(stored.get("translation_id") or ""), "mission detail latest translation mismatch")
        _assert(int(detail.get("prompt_translation_count") or 0) >= 3, f"translation count should reflect stored results: {detail}")

    print("prompt_translator_smoke_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
