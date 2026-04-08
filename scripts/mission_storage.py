from __future__ import annotations

from mission_storage_core import (
    AGENT_RUNS_DIRNAME,
    ASSUMPTIONS_DIRNAME,
    ASSUMPTION_LEDGER_FILENAME,
    INTERVENTIONS_DIRNAME,
    INTERVENTION_LOG_FILENAME,
    MIRROR_DIRNAME,
    MISSION_AGENT_DIRNAME,
    MISSION_AGENT_PROFILE_FILENAME,
    MISSION_AGENT_SOUL_FILENAME,
    MISSION_CHAT_FILENAME,
    MISSION_PARKING_FILENAME,
    RETRY_BUDGET_TOTAL,
    RETRY_LEDGER_FILENAME,
    RETRY_LOG_LIMIT,
    RUNNER_RETURNS_DIRNAME,
    TRIGGERS_DIRNAME,
    TRIGGER_HANDOFF_FILENAME,
    _agent_runs_dir,
    _append_jsonl,
    _archive_candidate_marker_path,
    _assumption_ledger_path,
    _assumptions_dir,
    _ensure_workbench_structure,
    _format_bytes,
    _intervention_log_path,
    _interventions_dir,
    _latest_mtime,
    _load_json,
    _mission_agent_profile_path,
    _mission_agent_root,
    _mission_agent_soul_path,
    _mission_chat_path,
    _mission_manifest_payload,
    _mission_parking_path,
    _mission_root,
    _mirror_dir,
    _read_jsonl,
    _retry_ledger_path,
    _runner_returns_dir,
    _short_digest,
    _trigger_handoff_path,
    _triggers_dir,
    _workbench_notes_root,
    _workbench_root,
    _write_json,
    configure_root,
    iso_now,
)
from mission_storage_read import (
    _default_parking_status,
    _default_retry_ledger,
    _default_trigger_handoff,
    _mission_inputs,
    _normalize_retry_log_items,
    _read_agent_runs,
    _read_archive_candidate_marker,
    _read_mirror_notes,
    _read_parking_status,
    _read_retry_ledger,
    _read_runner_returns,
    _read_trigger_handoff,
    _read_trigger_records,
    _workbench_files,
)
from mission_storage_save import (
    _write_mission_input,
    _write_operator_save_artifact,
    _write_parking_status,
    _write_retry_ledger,
    _write_trigger_handoff,
    write_operator_save_artifact,
)
import mission_storage_core as _core


def __getattr__(name: str):
    if hasattr(_core, name):
        return getattr(_core, name)
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_core)))
