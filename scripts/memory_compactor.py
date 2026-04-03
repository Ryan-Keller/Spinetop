from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from governance_utils import read_nanny_state, read_return_all_state
from repo_paths import repo_root


ROOT = repo_root()
COLLECTIVE_DIR = ROOT / "memory" / "collective"
COMPACTED_DIR = ROOT / "memory" / "compacted"
ARCHIVE_DIR = ROOT / "memory" / "archive" / "compacted_sources"
EVENT_LOG = ROOT / "logs" / "topology" / "events.jsonl"
RUN_LOG_DIR = ROOT / "logs" / "compactor"

GROUP_MIN_SIZE = 3


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def normalize_task_key(task: str) -> str:
    value = task.lower()
    value = re.sub(r"[^a-z0-9\s]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:80] if value else "unknown"


def load_collective_records() -> list[dict]:
    records: list[dict] = []
    if not COLLECTIVE_DIR.exists():
        return records
    for path in sorted(COLLECTIVE_DIR.glob("*.json")):
        raw = load_json(path)
        if raw is None:
            log_compaction_event("memory_compaction", path.name, "error", "malformed json")
            continue
        raw["_path"] = path
        records.append(raw)
    return records


def group_records(records: list[dict]) -> dict[tuple[str, str, str, str], list[dict]]:
    groups: dict[tuple[str, str, str, str], list[dict]] = {}
    for record in records:
        workspace = str(record.get("workspace") or "unknown")
        agent_id = str(record.get("agent_id") or "unknown")
        recommended = str(record.get("recommended_action") or "unknown")
        task_key = normalize_task_key(str(record.get("task") or ""))
        key = (workspace, agent_id, recommended, task_key)
        groups.setdefault(key, []).append(record)
    return groups


def should_compact(group: list[dict]) -> bool:
    return len(group) >= GROUP_MIN_SIZE


def build_compacted_record(key: tuple[str, str, str, str], group: list[dict]) -> dict:
    workspace, agent_id, recommended, task_key = key
    times = []
    for record in group:
        ts = record.get("timestamp_created")
        if ts:
            try:
                times.append(datetime.fromisoformat(str(ts)))
            except Exception:
                pass
    time_window_start = min(times).isoformat() if times else ""
    time_window_end = max(times).isoformat() if times else ""
    compaction_id = f"compact_{agent_id}_{task_key}_{len(group)}"
    source_records = [Path(record.get("_path")).name for record in group]

    return {
        "compaction_id": compaction_id,
        "workspace": workspace,
        "agent_id": agent_id,
        "source_type": "collective_cluster",
        "cluster_size": len(group),
        "time_window_start": time_window_start,
        "time_window_end": time_window_end,
        "recommended_action": recommended,
        "normalized_task_key": task_key,
        "summary": f"Repeated pattern detected across {len(group)} records",
        "source_records": source_records,
        "confidence": round(min(0.9, 0.4 + len(group) * 0.05), 2),
        "created_at": iso_now(),
        "compaction_version": 1,
    }


def archive_source_records(group: list[dict]) -> int:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    moved = 0
    for record in group:
        path = record.get("_path")
        if not isinstance(path, Path):
            continue
        target = ARCHIVE_DIR / path.name
        if target.exists():
            suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            target = ARCHIVE_DIR / f"{path.stem}_{suffix}{path.suffix}"
        path.replace(target)
        moved += 1
    return moved


def log_compaction_event(event_type: str, record_name: str, status: str, detail: str) -> None:
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": iso_now(),
        "machine": "Spinetop",
        "event_type": event_type,
        "record_name": record_name,
        "status": status,
        "detail": detail,
    }
    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def write_run_summary(groups_scanned: int, groups_compacted: int, records_compacted: int, records_skipped: int) -> None:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "ok": True,
        "timestamp": iso_now(),
        "groups_scanned": groups_scanned,
        "groups_compacted": groups_compacted,
        "records_compacted": records_compacted,
        "records_skipped": records_skipped,
    }
    path = RUN_LOG_DIR / "last_run.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    COMPACTED_DIR.mkdir(parents=True, exist_ok=True)

    return_all = read_return_all_state()
    nanny = read_nanny_state()
    if return_all.get("enabled") or nanny.get("temperature") in {"warm", "hot"} or int(nanny.get("global_cooldown_seconds") or 0) > 0:
        reason = "return_all active" if return_all.get("enabled") else f"nanny {nanny.get('temperature', 'cool')} or cooldown {nanny.get('global_cooldown_seconds', 0)}s active"
        log_compaction_event("memory_compaction", "none", "skipped", reason)
        write_run_summary(0, 0, 0, 0)
        return

    records = load_collective_records()
    groups = group_records(records)

    groups_scanned = len(groups)
    groups_compacted = 0
    records_compacted = 0
    records_skipped = 0

    for key, group in groups.items():
        if not should_compact(group):
            records_skipped += len(group)
            continue

        compacted = build_compacted_record(key, group)
        filename = f"{compacted['compaction_id']}.json"
        target = COMPACTED_DIR / filename
        if target.exists():
            records_skipped += len(group)
            continue

        target.write_text(json.dumps(compacted, indent=2) + "\n", encoding="utf-8")
        moved = archive_source_records(group)
        groups_compacted += 1
        records_compacted += moved

        log_compaction_event(
            "memory_compaction",
            filename,
            "success",
            f"compacted {len(group)} source records for normalized_task_key={compacted['normalized_task_key']}"
        )

    if groups_compacted == 0:
        log_compaction_event("memory_compaction", "none", "skipped", "no eligible groups")

    write_run_summary(groups_scanned, groups_compacted, records_compacted, records_skipped)


if __name__ == "__main__":
    main()
