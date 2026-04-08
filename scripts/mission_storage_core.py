from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from state_machine import mission_manifest_path, normalize_mission_id

ROOT = Path(__file__).resolve().parents[1]
EXPEDITIONS_ACTIVE_DIR = ROOT / "expeditions" / "active"
WORKBENCH_MISSIONS_DIR = ROOT / "workbench" / "missions"
MISSION_CHAT_FILENAME = "chat.jsonl"
MISSION_PARKING_FILENAME = "parking_status.json"
MISSION_AGENT_DIRNAME = "agent"
MISSION_AGENT_PROFILE_FILENAME = "profile.json"
MISSION_AGENT_SOUL_FILENAME = "SOUL.md"
TRIGGERS_DIRNAME = "triggers"
TRIGGER_HANDOFF_FILENAME = "pending_handoff.json"
RUNNER_RETURNS_DIRNAME = "runner_returns"
RETRY_LEDGER_FILENAME = "retries.json"
ASSUMPTIONS_DIRNAME = "assumptions"
ASSUMPTION_LEDGER_FILENAME = "ledger.json"
INTERVENTIONS_DIRNAME = "interventions"
INTERVENTION_LOG_FILENAME = "log.jsonl"
MIRROR_DIRNAME = "mirror"
AGENT_RUNS_DIRNAME = "agent_runs"
RETRY_BUDGET_TOTAL = 2
RETRY_LOG_LIMIT = 40


def configure_root(root: Path) -> None:
    global ROOT, EXPEDITIONS_ACTIVE_DIR, WORKBENCH_MISSIONS_DIR
    ROOT = Path(root)
    EXPEDITIONS_ACTIVE_DIR = ROOT / "expeditions" / "active"
    WORKBENCH_MISSIONS_DIR = ROOT / "workbench" / "missions"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_digest(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6]


def _format_bytes(value: int) -> str:
    size = max(0, int(value or 0))
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(size)
    unit = units[0]
    for candidate in units:
        unit = candidate
        if amount < 1024 or candidate == units[-1]:
            break
        amount /= 1024.0
    if unit == "B":
        return f"{int(amount)} {unit}"
    return f"{amount:.1f} {unit}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _mission_root(mission_id: str) -> Path:
    return EXPEDITIONS_ACTIVE_DIR / normalize_mission_id(mission_id)


def _workbench_root(mission_id: str) -> Path:
    return WORKBENCH_MISSIONS_DIR / normalize_mission_id(mission_id)


def _ensure_workbench_structure(mission_id: str) -> Path:
    root = _workbench_root(mission_id)
    for folder in ["intake", "scratch", "code", "test_runs", "notes", "outputs"]:
        (root / folder).mkdir(parents=True, exist_ok=True)
    return root


def _workbench_notes_root(mission_id: str, *, ensure: bool = False) -> Path:
    root = _ensure_workbench_structure(mission_id) if ensure else _workbench_root(mission_id)
    return root / "notes"


def _mission_chat_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / MISSION_CHAT_FILENAME


def _mission_agent_root(mission_id: str, *, ensure: bool = False) -> Path:
    root = _mission_root(mission_id)
    if ensure:
        (root / MISSION_AGENT_DIRNAME).mkdir(parents=True, exist_ok=True)
    return root / MISSION_AGENT_DIRNAME


def _mission_agent_profile_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _mission_agent_root(mission_id, ensure=ensure) / MISSION_AGENT_PROFILE_FILENAME


def _mission_agent_soul_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _mission_agent_root(mission_id, ensure=ensure) / MISSION_AGENT_SOUL_FILENAME


def _mission_parking_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / MISSION_PARKING_FILENAME


def _triggers_dir(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / TRIGGERS_DIRNAME


def _trigger_handoff_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _triggers_dir(mission_id, ensure=ensure) / TRIGGER_HANDOFF_FILENAME


def _runner_returns_dir(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / RUNNER_RETURNS_DIRNAME


def _retry_ledger_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / RETRY_LEDGER_FILENAME


def _assumptions_dir(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / ASSUMPTIONS_DIRNAME


def _assumption_ledger_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _assumptions_dir(mission_id, ensure=ensure) / ASSUMPTION_LEDGER_FILENAME


def _mirror_dir(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / MIRROR_DIRNAME


def _agent_runs_dir(mission_id: str, *, ensure: bool = False) -> Path:
    root = _workbench_notes_root(mission_id, ensure=ensure) / AGENT_RUNS_DIRNAME
    if ensure:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _interventions_dir(mission_id: str, *, ensure: bool = False) -> Path:
    return _workbench_notes_root(mission_id, ensure=ensure) / INTERVENTIONS_DIRNAME


def _intervention_log_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _interventions_dir(mission_id, ensure=ensure) / INTERVENTION_LOG_FILENAME


def _archive_candidate_marker_path(mission_id: str, *, ensure: bool = False) -> Path:
    return _interventions_dir(mission_id, ensure=ensure) / "archive_candidate.json"


def _mission_manifest_payload(mission_id: str) -> dict[str, Any] | None:
    path = mission_manifest_path(mission_id)
    if not path.exists():
        return None
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else None


def _latest_mtime(paths: list[Path]) -> str:
    latest: float | None = None
    for path in paths:
        if not path.exists():
            continue
        try:
            mtime = path.stat().st_mtime
        except Exception:
            continue
        if latest is None or mtime > latest:
            latest = mtime
    if latest is None:
        return ""
    return datetime.fromtimestamp(latest, tz=timezone.utc).isoformat()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
