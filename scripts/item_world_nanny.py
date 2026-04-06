from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG = ROOT / "logs" / "topology" / "events.jsonl"
DISPATCH_DIR = ROOT / "memory" / "dispatch"
STATUS_PATH = ROOT / "logs" / "nanny" / "item_world_status.json"
EXPEDITIONS_ACTIVE_DIR = ROOT / "expeditions" / "active"
WORKBENCH_MISSIONS_DIR = ROOT / "workbench" / "missions"
OPERATOR_LEARNING_PATH = ROOT / "workbench" / "system" / "operator_learning" / "nanny_pattern_memory.json"

WINDOW_SECONDS = 300
ERROR_WINDOW_SECONDS = 600
BRIDGE_WINDOW_SECONDS = 600
DISPATCH_WINDOW_SECONDS = 900
POLL_SECONDS = 30

WARM_BURST = 20
HOT_BURST = 40
WARM_ERRORS = 4
HOT_ERRORS = 8
WARM_BRIDGE_RETRIES = 3
HOT_BRIDGE_RETRIES = 6
AGENT_DISPATCH_WARN = 3

COOLDOWN_COOL = 0
COOLDOWN_WARM = 15
COOLDOWN_HOT = 30

QUEUE_STALE_DAYS = 7
QUEUE_LONG_PARKED_DAYS = 14
QUEUE_PRESSURE_MISSIONS = 6
QUEUE_PRESSURE_DUPLICATES = 3
QUEUE_PRESSURE_ARCHIVE = 2
BLOCKER_JUNK_REPEAT = 2
WEAK_QUESTION_REPEAT = 2
RETRY_REPEAT_WARN = 2
POOR_INTAKE_WARN = 2
REVIVE_ELIGIBLE_WARN = 2
BLOCKED_REVIEW_WARN = 3
MAX_SIGNALS = 4

JUNK_OBJECTIVE_RE = re.compile(
    r"^(?:test|tmp|temp|temporary|debug|scratch|demo|dummy|junk|throwaway|foo|bar|asdf)\b",
    re.IGNORECASE,
)
SYSTEM_BLOCKER_RE = re.compile(
    r"\b(?:retry|budget|handoff|system|refresh|pending|guard|blocked|failure|loop|bridge)\b",
    re.IGNORECASE,
)
WEAK_QUESTION_RE = re.compile(
    r"^(?:help|status|update|what next|next|please advise|thoughts|any ideas)\??$",
    re.IGNORECASE,
)


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for entry in value:
        text = str(entry or "").strip()
        if text:
            items.append(text)
    return items


def _normalize_objective(value: str) -> str:
    text = re.sub(r"[^\w\s]+", " ", str(value or "").lower().strip())
    return re.sub(r"\s+", " ", text).strip()


def _days_since(timestamp: str, *, now: datetime) -> float | None:
    parsed = parse_time(timestamp)
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return max(0.0, (now - parsed).total_seconds() / 86400)


def _is_junk_objective(objective: str) -> bool:
    normalized = _normalize_objective(objective)
    return bool(normalized and len(normalized) <= 48 and JUNK_OBJECTIVE_RE.match(normalized))


def _is_weak_question(question: str) -> bool:
    text = str(question or "").strip()
    if not text:
        return False
    words = [part for part in re.split(r"\s+", text) if part]
    normalized = _normalize_objective(text)
    if WEAK_QUESTION_RE.match(text):
        return True
    if len(words) <= 3:
        return True
    if len(text) < 18:
        return True
    if "?" not in text and len(words) <= 5:
        return True
    if normalized in {"what now", "what next", "next step", "need input"}:
        return True
    return False


def _mission_ids() -> list[str]:
    mission_ids: set[str] = set()
    if EXPEDITIONS_ACTIVE_DIR.exists():
        mission_ids.update(path.name for path in EXPEDITIONS_ACTIVE_DIR.iterdir() if path.is_dir())
    if WORKBENCH_MISSIONS_DIR.exists():
        mission_ids.update(path.name for path in WORKBENCH_MISSIONS_DIR.iterdir() if path.is_dir())
    return sorted(mission_ids)


def _mission_snapshot(mission_id: str, *, now: datetime) -> dict[str, Any]:
    expedition_root = EXPEDITIONS_ACTIVE_DIR / mission_id
    workbench_root = WORKBENCH_MISSIONS_DIR / mission_id
    notes_root = workbench_root / "notes"

    brief = _load_json(expedition_root / "mission_brief.json")
    state = _load_json(expedition_root / "state.json")
    working_memory = _load_json(expedition_root / "working_memory.json")
    parking = _load_json(notes_root / "parking_status.json")
    retries = _load_json(notes_root / "retries.json")

    objective = str(brief.get("objective") or brief.get("task_text") or "").strip()
    normalized_objective = _normalize_objective(objective)
    blocked_reason = str(working_memory.get("blocked_reason") or "").strip()
    questions = _list_strings(working_memory.get("blocking_questions"))
    questions.extend(_list_strings(working_memory.get("open_questions")))
    next_question = str(working_memory.get("next_question") or "").strip()
    if next_question:
        questions.append(next_question)
    deduped_questions = list(dict.fromkeys(question for question in questions if question))
    weak_questions = [question for question in deduped_questions if _is_weak_question(question)]
    parked = str(parking.get("status") or "active").strip().lower() == "parked"
    can_continue = bool(working_memory.get("can_continue_without_input", False))
    updated_candidates = [
        str(state.get("updated_at") or "").strip(),
        str(working_memory.get("updated_at") or "").strip(),
        str(parking.get("updated_at") or "").strip(),
        str(brief.get("created_at") or "").strip(),
    ]
    updated_at = max(updated_candidates) if any(updated_candidates) else ""
    last_activity_age_days = _days_since(updated_at, now=now)
    intake_count = len(list((workbench_root / "intake").glob("*.json"))) if (workbench_root / "intake").exists() else 0
    decision_log = retries.get("decision_log") if isinstance(retries.get("decision_log"), list) else []
    retry_stop_conditions = [
        str(item.get("stop_condition") or "").strip()
        for item in decision_log
        if isinstance(item, dict) and str(item.get("stop_condition") or "").strip()
    ]
    retry_reasons = [
        str(item.get("reason") or item.get("blocked_reason") or "").strip()
        for item in decision_log
        if isinstance(item, dict) and str(item.get("reason") or item.get("blocked_reason") or "").strip()
    ]
    poor_intake = (
        not objective
        or len(normalized_objective.split()) < 3
        or len(normalized_objective) < 18
        or (intake_count == 0 and len(normalized_objective.split()) <= 4)
        or _is_junk_objective(objective)
    )
    return {
        "mission_id": mission_id,
        "objective": objective,
        "normalized_objective": normalized_objective,
        "current_state": str(state.get("current_state") or "").strip(),
        "blocked_reason": blocked_reason,
        "questions": deduped_questions,
        "weak_questions": weak_questions,
        "parked": parked,
        "can_continue": can_continue,
        "updated_at": updated_at,
        "last_activity_age_days": last_activity_age_days,
        "intake_count": intake_count,
        "junk_objective": _is_junk_objective(objective),
        "poor_intake": poor_intake,
        "retry_budget_used": int(retries.get("retry_budget_used") or 0),
        "retry_stop_conditions": retry_stop_conditions,
        "retry_reasons": retry_reasons,
    }


def _signal(
    signal_id: str,
    *,
    level: str,
    title: str,
    cause: str,
    action_label: str,
    action_kind: str,
    severity: str = "watch",
) -> dict[str, Any]:
    return {
        "id": signal_id,
        "level": level,
        "title": title,
        "cause": cause,
        "action_label": action_label,
        "action_kind": action_kind,
        "severity": severity,
    }


def _learning_payload(
    missions: list[dict[str, Any]],
    *,
    counts: dict[str, int],
    weak_question_examples: list[str],
) -> dict[str, Any]:
    junk_examples = [mission["objective"] for mission in missions if mission.get("blocker_classification") == "junk" and mission.get("objective")][:3]
    system_examples = [mission["objective"] for mission in missions if mission.get("blocker_classification") == "system" and mission.get("objective")][:3]
    human_examples = [mission["objective"] for mission in missions if mission.get("blocker_classification") == "human" and mission.get("objective")][:3]
    return {
        "updated_at": iso_now(),
        "derived_only": True,
        "blocker_patterns": {
            "counts": counts,
            "weak_question_count": len(weak_question_examples),
            "weak_question_examples": weak_question_examples[:5],
        },
        "examples": {
            "junk": junk_examples,
            "system": system_examples,
            "human": human_examples,
        },
        "stored_in": OPERATOR_LEARNING_PATH.relative_to(ROOT).as_posix(),
    }


def read_events() -> list[dict]:
    if not EVENT_LOG.exists():
        return []
    rows: list[dict] = []
    for line in EVENT_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def read_dispatch_records() -> list[dict]:
    records: list[dict] = []
    for folder in ("pending", "approved", "deferred", "rejected"):
        path = DISPATCH_DIR / folder
        if not path.exists():
            continue
        for file in path.glob("*.json"):
            try:
                payload = json.loads(file.read_text(encoding="utf-8"))
            except Exception:
                continue
            payload["petition_status"] = folder
            records.append(payload)
    return records


def log_nanny_event(status: str, detail: str) -> None:
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": iso_now(),
        "machine": "Spinetop",
        "event_type": "item_world_nanny",
        "record_name": "global",
        "status": status,
        "detail": detail,
    }
    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def compute_status() -> dict:
    now = datetime.now()
    events = read_events()
    dispatch_records = read_dispatch_records()
    missions = [_mission_snapshot(mission_id, now=now) for mission_id in _mission_ids()]

    grouped_objectives: dict[str, list[dict[str, Any]]] = {}
    for mission in missions:
        group_key = str(mission.get("normalized_objective") or mission.get("mission_id") or "").strip()
        grouped_objectives.setdefault(group_key, []).append(mission)
    for group in grouped_objectives.values():
        group.sort(key=lambda mission: str(mission.get("updated_at") or ""), reverse=True)
        for index, mission in enumerate(group, start=1):
            duplicate_count = len(group)
            mission["duplicate_count"] = duplicate_count
            mission["duplicate_rank"] = index
            mission["duplicate_follower"] = duplicate_count > 1 and index > 1

    weak_question_examples: list[str] = []
    blocker_counts = {"junk": 0, "system": 0, "human": 0}
    for mission in missions:
        blocked_reason = str(mission.get("blocked_reason") or "")
        questions = mission.get("questions") if isinstance(mission.get("questions"), list) else []
        if mission.get("junk_objective") or mission.get("duplicate_follower"):
            blocker_classification = "junk"
        elif SYSTEM_BLOCKER_RE.search(blocked_reason) or any(
            condition in {"repeated_same_failure_without_new_evidence", "exhausted_retry_budget"}
            for condition in mission.get("retry_stop_conditions", [])
        ):
            blocker_classification = "system"
        elif questions or not bool(mission.get("can_continue", False)) or blocked_reason:
            blocker_classification = "human"
        else:
            blocker_classification = "system"
        mission["blocker_classification"] = blocker_classification
        blocker_counts[blocker_classification] += 1
        weak_question_examples.extend(mission.get("weak_questions", []))

    duplicate_followers = sum(1 for mission in missions if mission.get("duplicate_follower"))
    stale_missions = sum(
        1
        for mission in missions
        if mission.get("last_activity_age_days") is not None and float(mission["last_activity_age_days"]) >= QUEUE_STALE_DAYS
    )
    archive_candidates = sum(
        1
        for mission in missions
        if (
            bool(mission.get("duplicate_follower"))
            or bool(mission.get("junk_objective") and mission.get("last_activity_age_days") is not None and float(mission["last_activity_age_days"]) >= QUEUE_STALE_DAYS)
            or bool(mission.get("parked") and mission.get("last_activity_age_days") is not None and float(mission["last_activity_age_days"]) >= QUEUE_LONG_PARKED_DAYS)
        )
    )
    blocked_missions = sum(
        1
        for mission in missions
        if not bool(mission.get("parked"))
        and (
            bool(mission.get("questions"))
            or str(mission.get("blocked_reason") or "").strip()
            or not bool(mission.get("can_continue", False))
        )
    )
    weak_questions = len(weak_question_examples)
    junk_blockers = sum(
        1
        for mission in missions
        if mission.get("blocker_classification") == "junk"
        and (mission.get("questions") or mission.get("blocked_reason") or mission.get("duplicate_follower"))
    )
    poor_intake = sum(1 for mission in missions if mission.get("poor_intake"))
    missing_objectives = sum(1 for mission in missions if not str(mission.get("objective") or "").strip())
    revive_candidates = sum(
        1
        for mission in missions
        if mission.get("parked")
        and not mission.get("junk_objective")
        and not mission.get("duplicate_follower")
        and bool(mission.get("can_continue", False))
    )
    retry_loops = sum(
        1
        for mission in missions
        if "repeated_same_failure_without_new_evidence" in mission.get("retry_stop_conditions", [])
    )
    retry_budget_hits = sum(
        1 for mission in missions if "exhausted_retry_budget" in mission.get("retry_stop_conditions", [])
    )
    repeated_retry_failures = sum(
        1 for mission in missions if len(mission.get("retry_reasons", [])) >= 2 or int(mission.get("retry_budget_used") or 0) >= 2
    )

    honcho_events = [
        e for e in events
        if str(e.get("event_type", "")).startswith("honcho_")
        or e.get("event_type") in {"dispatch_petition", "item_world_nanny"}
    ]

    recent_events = [
        e for e in honcho_events
        if (parse_time(str(e.get("timestamp"))) or now) > now - timedelta(seconds=WINDOW_SECONDS)
    ]
    recent_errors = [
        e for e in honcho_events
        if (parse_time(str(e.get("timestamp"))) or now) > now - timedelta(seconds=ERROR_WINDOW_SECONDS)
        and str(e.get("status")) in {"error", "skipped", "timeout"}
    ]
    recent_bridge_errors = [
        e for e in honcho_events
        if str(e.get("event_type")) in {"honcho_bridge", "honcho_bridge_file", "honcho_bridge_watcher"}
        and (parse_time(str(e.get("timestamp"))) or now) > now - timedelta(seconds=BRIDGE_WINDOW_SECONDS)
        and str(e.get("status")) in {"error", "skipped"}
    ]

    dispatch_recent = [
        r for r in dispatch_records
        if (parse_time(str(r.get("timestamp_created"))) or now) > now - timedelta(seconds=DISPATCH_WINDOW_SECONDS)
    ]
    agent_counts: dict[str, int] = {}
    for record in dispatch_recent:
        agent = str(record.get("agent_id") or "unknown")
        agent_counts[agent] = agent_counts.get(agent, 0) + 1

    warnings = []
    for agent_id, count in agent_counts.items():
        if count >= AGENT_DISPATCH_WARN:
            warnings.append({
                "agent_id": agent_id,
                "reason": "too many requests",
            })

    burst_score = len(recent_events)
    error_score = len(recent_errors)
    bridge_retries = len(recent_bridge_errors)

    temperature = "cool"
    if burst_score >= HOT_BURST or error_score >= HOT_ERRORS or bridge_retries >= HOT_BRIDGE_RETRIES:
        temperature = "hot"
    elif burst_score >= WARM_BURST or error_score >= WARM_ERRORS or bridge_retries >= WARM_BRIDGE_RETRIES:
        temperature = "warm"
    elif warnings:
        temperature = "warm"

    recommended_actions: list[str] = []
    if temperature in {"warm", "hot"}:
        recommended_actions.append("slow dispatch intake")
        recommended_actions.append("prefer deferred review")
    if bridge_retries >= WARM_BRIDGE_RETRIES:
        recommended_actions.append("pause bridge retries")

    if temperature == "hot":
        global_cooldown = COOLDOWN_HOT
    elif temperature == "warm":
        global_cooldown = COOLDOWN_WARM
    else:
        global_cooldown = COOLDOWN_COOL

    signals: list[dict[str, Any]] = []
    if (
        len(missions) >= QUEUE_PRESSURE_MISSIONS
        or duplicate_followers >= QUEUE_PRESSURE_DUPLICATES
        or archive_candidates >= QUEUE_PRESSURE_ARCHIVE
    ):
        cause_parts: list[str] = []
        if duplicate_followers:
            cause_parts.append(f"{duplicate_followers} duplicate missions")
        if junk_blockers:
            cause_parts.append(f"{junk_blockers} junk blockers")
        if archive_candidates:
            cause_parts.append(f"{archive_candidates} archive candidates")
        signals.append(_signal(
            "queue_pressure",
            level="signal",
            title="Queue overloaded",
            cause=" + ".join(cause_parts[:3]) or f"{len(missions)} missions in queue",
            action_label="Clean Queue",
            action_kind="clean_queue",
            severity="bad" if duplicate_followers >= QUEUE_PRESSURE_DUPLICATES and archive_candidates >= QUEUE_PRESSURE_ARCHIVE else "watch",
        ))
        recommended_actions.append("clean queue")

    if junk_blockers >= BLOCKER_JUNK_REPEAT or weak_questions >= WEAK_QUESTION_REPEAT:
        cause = (
            f"{junk_blockers} junk blockers repeating"
            if junk_blockers >= BLOCKER_JUNK_REPEAT
            else f"{weak_questions} weak blocker questions repeating"
        )
        signals.append(_signal(
            "blocker_quality",
            level="issue",
            title="Repeated junk blockers detected" if junk_blockers >= BLOCKER_JUNK_REPEAT else "Weak blocker questions detected",
            cause=cause,
            action_label="Review system fix",
            action_kind="review_system_fix",
            severity="watch",
        ))
        recommended_actions.append("review system fix")

    if retry_loops >= 1 or retry_budget_hits >= RETRY_REPEAT_WARN or repeated_retry_failures >= RETRY_REPEAT_WARN:
        cause_parts: list[str] = []
        if retry_loops:
            cause_parts.append("same failure repeated")
        if retry_budget_hits:
            cause_parts.append(f"{retry_budget_hits} retry budget stops")
        if repeated_retry_failures:
            cause_parts.append(f"{repeated_retry_failures} repeated failure missions")
        signals.append(_signal(
            "retry_pattern",
            level="issue",
            title="Retry loop risk",
            cause=" + ".join(cause_parts[:3]) or "Repeated failures without new evidence",
            action_label="Review blocked missions",
            action_kind="review_blocked_missions",
            severity="bad" if retry_loops else "watch",
        ))
        recommended_actions.append("review blocked missions")

    if poor_intake >= POOR_INTAKE_WARN or missing_objectives >= 1:
        cause_parts: list[str] = []
        if poor_intake:
            cause_parts.append(f"{poor_intake} low-signal intakes")
        if missing_objectives:
            cause_parts.append(f"{missing_objectives} missing objectives")
        signals.append(_signal(
            "system_issue",
            level="issue",
            title="Poor intake quality",
            cause=" + ".join(cause_parts[:3]) or "Mission objectives are too weak to route cleanly",
            action_label="Review system fix",
            action_kind="review_system_fix",
            severity="watch",
        ))
        recommended_actions.append("review intake rules")

    if len(signals) < MAX_SIGNALS and blocked_missions >= BLOCKED_REVIEW_WARN:
        signals.append(_signal(
            "blocked_recall",
            level="signal",
            title="Blocked missions piling up",
            cause=f"{blocked_missions} blocked missions need review",
            action_label="Review blocked missions",
            action_kind="review_blocked_missions",
            severity="watch",
        ))
        recommended_actions.append("review blocked missions")

    if len(signals) < MAX_SIGNALS and revive_candidates >= REVIVE_ELIGIBLE_WARN:
        signals.append(_signal(
            "revive_recall",
            level="signal",
            title="Revive eligible missions",
            cause=f"{revive_candidates} parked missions can likely continue",
            action_label="Revive eligible missions",
            action_kind="revive_eligible_missions",
            severity="watch",
        ))
        recommended_actions.append("revive eligible missions")

    learning = _learning_payload(
        missions,
        counts=blocker_counts,
        weak_question_examples=weak_question_examples,
    )

    return {
        "ok": True,
        "temperature": temperature,
        "burst_score": burst_score,
        "error_score": error_score,
        "active_agent_warnings": warnings,
        "recommended_actions": sorted(set(recommended_actions)),
        "global_cooldown_seconds": global_cooldown,
        "system_signals": signals[:MAX_SIGNALS],
        "signal_count": min(len(signals), MAX_SIGNALS),
        "learning_summary": {
            "stored_path": learning["stored_in"],
            "updated_at": learning["updated_at"],
            "counts": blocker_counts,
            "weak_question_count": weak_questions,
        },
        "derived_counts": {
            "missions": len(missions),
            "duplicates": duplicate_followers,
            "archive_candidates": archive_candidates,
            "blocked_missions": blocked_missions,
            "stale_missions": stale_missions,
            "junk_blockers": junk_blockers,
            "weak_questions": weak_questions,
            "retry_loops": retry_loops,
            "poor_intake": poor_intake,
        },
        "_learning_payload": learning,
    }


def maybe_log_event(status: dict) -> None:
    previous = None
    if STATUS_PATH.exists():
        try:
            previous = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            previous = None

    changed = True
    if previous:
        changed = (
            previous.get("temperature") != status.get("temperature")
            or previous.get("active_agent_warnings") != status.get("active_agent_warnings")
            or previous.get("recommended_actions") != status.get("recommended_actions")
        )

    if changed:
        detail = (
            f"burst={status['burst_score']} error={status['error_score']} "
            f"cooldown={status['global_cooldown_seconds']}s"
        )
        if status["recommended_actions"]:
            detail += f"; actions={','.join(status['recommended_actions'])}"
        log_nanny_event(status["temperature"], detail)


def write_status(status: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(status)
    payload.pop("_learning_payload", None)
    STATUS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_learning(status: dict) -> None:
    learning = status.get("_learning_payload")
    if not isinstance(learning, dict):
        return
    OPERATOR_LEARNING_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPERATOR_LEARNING_PATH.write_text(json.dumps(learning, indent=2) + "\n", encoding="utf-8")


def run_once() -> None:
    status = compute_status()
    maybe_log_event(status)
    write_status(status)
    write_learning(status)


def main() -> None:
    watch = "--watch" in __import__("sys").argv
    if watch:
        while True:
            run_once()
            time.sleep(POLL_SECONDS)
    else:
        run_once()


if __name__ == "__main__":
    main()
