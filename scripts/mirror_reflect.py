from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from helper_model_runtime import load_helper_runtime_profile
from repo_paths import repo_root
from run_hermes_v1 import extract_json_candidate, invoke_model, load_hermes_runtime_config


ROOT = repo_root()
RUNTIME_ROLE = "spinetop-mirror"
PROFILE = load_helper_runtime_profile(RUNTIME_ROLE)
MIRROR_MODEL_LOG = ROOT / "logs" / "support" / "mirror_model_invocations.jsonl"
APPROVED_READ_ROOTS = [
    ROOT / "workbench" / "missions",
    ROOT / "logs",
    ROOT / "memory",
]
FORBIDDEN_WRITE_ROOTS = [
    ROOT / "services" / "honcho",
    ROOT / "memory" / "collective",
    ROOT / "memory" / "dispatch" / "approved",
]
ALLOWED_OUTPUT_ROOT = ROOT / "workbench" / "missions"
TEXT_FIELDS = (
    "message",
    "summary",
    "reason",
    "content",
    "note",
    "task_scope",
    "resume_hint",
    "status",
)
TIMESTAMP_FIELDS = ("created_at", "updated_at", "timestamp", "occurred_at", "completed_at")
SPEAKER_FIELDS = ("sender", "role", "requested_by", "created_by", "author")
SHORT_SIGNAL_LIMIT = 3
QUESTION_SUFFIX = "?"
AFFIRMATIVE_SIGNALS = {"yes", "y", "go", "proceed", "continue", "ok", "okay"}
NEGATIVE_SIGNALS = {"no", "n", "stop", "hold", "pause", "park mission", "cancel"}
MODEL_CHAT_ITEM_LIMIT = 6
MODEL_EXECUTION_ITEM_LIMIT = 4
MODEL_STATE_ITEM_LIMIT = 4
MODEL_TOTAL_ITEM_LIMIT = 14
MODEL_TEXT_CHAR_LIMIT = 280


class MirrorReflectError(ValueError):
    pass


@dataclass(frozen=True)
class MemoryItem:
    source_ref: str
    timestamp: str
    speaker: str
    text: str
    payload: dict[str, Any]
    sort_key: tuple[int, str, str]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _is_under(path: Path, root: Path) -> bool:
    path = path.resolve()
    root = root.resolve()
    return path == root or root in path.parents


def _path_to_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except Exception:
        return path.resolve().as_posix()


def _resolve_repo_path(raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    return (ROOT / candidate).resolve()


def _resolve_input_path(raw: str) -> Path:
    candidate = _resolve_repo_path(raw)
    if not candidate.exists():
        raise MirrorReflectError(f"Input path does not exist: {raw}")
    if not any(_is_under(candidate, root) for root in APPROVED_READ_ROOTS):
        raise MirrorReflectError(f"Input path is outside Mirror approved read roots: {raw}")
    return candidate


def resolve_output_path(mission_id: str, output_path: str | None) -> Path | None:
    if not output_path:
        return None
    candidate = _resolve_repo_path(output_path)
    if any(_is_under(candidate, root) for root in FORBIDDEN_WRITE_ROOTS):
        raise MirrorReflectError("Mirror may not write to Honcho or governed truth lanes")
    if not _is_under(candidate, ALLOWED_OUTPUT_ROOT):
        raise MirrorReflectError("Mirror output must stay under workbench/missions/")
    expected_root = (ALLOWED_OUTPUT_ROOT / mission_id / "notes" / "mirror").resolve()
    if not _is_under(candidate, expected_root):
        raise MirrorReflectError("Mirror output must stay under workbench/missions/<mission_id>/notes/mirror/")
    return candidate


def _load_jsonish(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise MirrorReflectError(f"Malformed JSONL in {_path_to_ref(path)} line {line_no}: {exc}") from exc
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise MirrorReflectError(f"Malformed JSON in {_path_to_ref(path)}: {exc}") from exc

    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise MirrorReflectError(f"Unsupported input payload in {_path_to_ref(path)}")


def _extract_text(record: dict[str, Any]) -> str:
    chunks: list[str] = []
    for field in TEXT_FIELDS:
        value = record.get(field)
        if isinstance(value, str):
            text = value.strip()
            if text:
                chunks.append(text)
    return " | ".join(chunks)


def _extract_timestamp(record: dict[str, Any]) -> str:
    for field in TIMESTAMP_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_speaker(record: dict[str, Any]) -> str:
    for field in SPEAKER_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return "unknown"


def _shorten_text(text: str, *, limit: int = MODEL_TEXT_CHAR_LIMIT) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."


def _append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False) + "\n")


def _parse_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_memory_items(paths: list[str]) -> list[MemoryItem]:
    items: list[MemoryItem] = []
    for raw_path in paths:
        path = _resolve_input_path(raw_path)
        for record in _load_jsonish(path):
            text = _extract_text(record)
            if not text:
                continue
            timestamp = _extract_timestamp(record)
            parsed_timestamp = _parse_timestamp(timestamp)
            items.append(
                MemoryItem(
                    source_ref=_path_to_ref(path),
                    timestamp=timestamp,
                    speaker=_extract_speaker(record),
                    text=text,
                    payload=record,
                    sort_key=(
                        0 if parsed_timestamp is not None else 1,
                        parsed_timestamp.isoformat() if parsed_timestamp is not None else "",
                        _path_to_ref(path),
                    ),
                )
            )
    if not items:
        raise MirrorReflectError("Mirror needs at least one readable memory item")
    items.sort(key=lambda item: item.sort_key)
    return items


def _normalize_text(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9\s?]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _find_repeated_messages(items: list[MemoryItem]) -> list[str]:
    counts = Counter(_normalize_text(item.text) for item in items if _normalize_text(item.text))
    repeats = [(text, count) for text, count in counts.items() if count >= 2 and len(text.split()) >= 2]
    repeats.sort(key=lambda pair: (-pair[1], pair[0]))
    lines: list[str] = []
    for text, count in repeats[:4]:
        lines.append(f"Repeated {count} times: '{text}'")
    return lines


def _find_role_patterns(items: list[MemoryItem]) -> list[str]:
    speaker_counts = Counter(item.speaker for item in items)
    patterns: list[str] = []
    if speaker_counts:
        ordered = ", ".join(f"{speaker}={count}" for speaker, count in speaker_counts.most_common())
        patterns.append(f"Memory is dominated by these voices: {ordered}.")

    short_user_messages = [
        item for item in items if item.speaker == "user" and len(_normalize_text(item.text).split()) <= SHORT_SIGNAL_LIMIT
    ]
    if short_user_messages:
        patterns.append(
            f"User input is often compressed into short signals ({len(short_user_messages)} brief turns), which increases ambiguity."
        )

    repeated_questions = Counter(
        _normalize_text(item.text)
        for item in items
        if item.speaker in {"assistant", "system"} and item.text.strip().endswith(QUESTION_SUFFIX)
    )
    for text, count in repeated_questions.most_common():
        if count >= 2:
            patterns.append(f"The same open question persists across turns: '{text}'.")
            break
    return patterns


def _iter_payload_scalars(payload: Any) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        for value in payload.values():
            values.extend(_iter_payload_scalars(value))
    elif isinstance(payload, list):
        for value in payload:
            values.extend(_iter_payload_scalars(value))
    elif isinstance(payload, (str, bool, int, float)):
        text = str(payload).strip()
        if text:
            values.append(text)
    return values


def _payload_text(item: MemoryItem) -> str:
    return " | ".join(_iter_payload_scalars(item.payload)).lower()


def _looks_like_operator_driven(item: MemoryItem) -> bool:
    payload_text = _payload_text(item)
    return any(token in payload_text for token in ("operator_", "operator ", "manual", "control_tower", "explicit_role_invocation"))


def _item_kind(item: MemoryItem) -> str:
    artifact_kind = str(item.payload.get("artifact_kind") or "").strip().lower()
    if artifact_kind in {"agent_role_invocation", "agent_run"}:
        return "execution"
    if str(item.payload.get("status") or "").strip().lower() == "parked" or bool(str(item.payload.get("parked_at") or "").strip()):
        return "parking"
    if (
        str(item.payload.get("trigger_kind") or "").strip()
        or str(item.payload.get("allowed_action") or "").strip()
        or str(item.payload.get("policy_basis") or "").strip()
    ):
        return "trigger"
    if item.source_ref.endswith(".jsonl"):
        return "conversation"
    return "state"


def _select_model_items(items: list[MemoryItem]) -> list[MemoryItem]:
    selected_indexes: set[int] = set()

    def add_matching(limit: int, predicate) -> None:
        count = 0
        for index in range(len(items) - 1, -1, -1):
            if predicate(items[index]):
                selected_indexes.add(index)
                count += 1
                if count >= limit:
                    break

    add_matching(MODEL_CHAT_ITEM_LIMIT, lambda item: _item_kind(item) == "conversation")
    add_matching(MODEL_EXECUTION_ITEM_LIMIT, lambda item: _item_kind(item) == "execution")
    add_matching(MODEL_STATE_ITEM_LIMIT, lambda item: _item_kind(item) in {"trigger", "parking", "state"})
    add_matching(1, lambda item: "no active agent runs" in _normalize_text(item.text) or "no active runs" in _normalize_text(item.text))
    add_matching(1, _looks_like_operator_driven)

    if len(selected_indexes) < MODEL_TOTAL_ITEM_LIMIT:
        for index in range(len(items) - 1, -1, -1):
            selected_indexes.add(index)
            if len(selected_indexes) >= MODEL_TOTAL_ITEM_LIMIT:
                break

    selected = [items[index] for index in sorted(selected_indexes)]
    if len(selected) <= MODEL_TOTAL_ITEM_LIMIT:
        return selected

    priority_order = {"trigger": 0, "parking": 1, "execution": 2, "state": 3, "conversation": 4}
    ranked = sorted(
        enumerate(selected),
        key=lambda pair: (
            priority_order.get(_item_kind(pair[1]), 9),
            0 if _looks_like_operator_driven(pair[1]) else 1,
            0 if pair[1].timestamp else 1,
            -pair[0],
        ),
    )
    keep_positions = {position for position, _item in ranked[:MODEL_TOTAL_ITEM_LIMIT]}
    return [item for position, item in enumerate(selected) if position in keep_positions]


def _collapse_model_items(items: list[MemoryItem]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for item in items:
        normalized = _normalize_text(item.text)
        key = (item.speaker, _item_kind(item), normalized or item.source_ref)
        if key not in grouped:
            grouped[key] = {
                "source_ref": item.source_ref,
                "timestamp": item.timestamp,
                "speaker": item.speaker,
                "kind": _item_kind(item),
                "text": _shorten_text(item.text),
                "repeat_count": 1,
                "source_refs": {item.source_ref},
            }
            order.append(key)
            continue
        grouped[key]["repeat_count"] = int(grouped[key]["repeat_count"]) + 1
        grouped[key]["timestamp"] = item.timestamp or grouped[key]["timestamp"]
        grouped[key]["text"] = _shorten_text(item.text)
        grouped[key]["source_ref"] = item.source_ref
        grouped[key]["source_refs"].add(item.source_ref)

    collapsed: list[dict[str, Any]] = []
    for key in order:
        entry = grouped[key]
        payload = {
            "source_ref": str(entry["source_ref"]),
            "timestamp": str(entry["timestamp"]),
            "speaker": str(entry["speaker"]),
            "kind": str(entry["kind"]),
            "text": str(entry["text"]),
        }
        if int(entry["repeat_count"]) > 1:
            payload["repeat_count"] = int(entry["repeat_count"])
        if len(entry["source_refs"]) > 1:
            payload["source_ref_count"] = len(entry["source_refs"])
        collapsed.append(payload)
    return collapsed


def _build_model_context(items: list[MemoryItem]) -> dict[str, Any]:
    selected_items = _select_model_items(items)
    prompt_items = _collapse_model_items(selected_items)
    kind_counts = Counter(_item_kind(item) for item in items)
    speaker_counts = Counter(item.speaker for item in items)
    success_runs = [
        item
        for item in items
        if str(item.payload.get("status") or "").strip().lower() == "success"
        and _item_kind(item) == "execution"
    ]
    operator_success_runs = [item for item in success_runs if _looks_like_operator_driven(item)]
    blocked_items = [
        item
        for item in items
        if str(item.payload.get("status") or "").strip().lower() == "blocked"
        or "blocked by parked mission" in _payload_text(item)
    ]
    parked_items = [item for item in items if _item_kind(item) == "parking"]
    return {
        "context_window": {
            "total_loaded_items": len(items),
            "selected_items_before_collapse": len(selected_items),
            "prompt_items_after_collapse": len(prompt_items),
            "caps": {
                "conversation_items": MODEL_CHAT_ITEM_LIMIT,
                "execution_items": MODEL_EXECUTION_ITEM_LIMIT,
                "state_items": MODEL_STATE_ITEM_LIMIT,
                "total_items": MODEL_TOTAL_ITEM_LIMIT,
                "text_chars_per_item": MODEL_TEXT_CHAR_LIMIT,
            },
        },
        "history_summary": {
            "source_ref_count": len({item.source_ref for item in items}),
            "speaker_counts": dict(sorted(speaker_counts.items())),
            "kind_counts": dict(sorted(kind_counts.items())),
            "successful_execution_count": len(success_runs),
            "successful_manual_execution_count": len(operator_success_runs),
            "blocked_evidence_count": len(blocked_items),
            "parked_evidence_count": len(parked_items),
        },
        "memory_items": prompt_items,
    }


def _find_timeline_mismatches(items: list[MemoryItem]) -> tuple[list[str], list[str], list[str], str | None]:
    contradictions: list[str] = []
    patterns: list[str] = []
    gaps: list[str] = []

    success_runs = [
        item
        for item in items
        if str(item.payload.get("status") or "").strip().lower() == "success"
        and str(item.payload.get("artifact_kind") or "").strip().lower() in {"agent_role_invocation", "agent_run"}
    ]
    operator_success_runs = [item for item in success_runs if _looks_like_operator_driven(item)]
    blocked_triggers = [
        item
        for item in items
        if (
            str(item.payload.get("status") or "").strip().lower() == "blocked"
            or "blocked by parked mission" in _payload_text(item)
            or str((((item.payload.get("evaluation") or {}) if isinstance(item.payload.get("evaluation"), dict) else {}).get("blocked_reason")) or "").strip().lower() == "blocked by parked mission"
        )
        and (
            str(item.payload.get("trigger_kind") or "").strip()
            or str(item.payload.get("allowed_action") or "").strip()
            or str(item.payload.get("policy_basis") or "").strip()
        )
    ]
    parked_items = [
        item
        for item in items
        if str(item.payload.get("status") or "").strip().lower() == "parked"
        or bool(str(item.payload.get("parked_at") or "").strip())
    ]
    no_active_claims = [
        item
        for item in items
        if any(phrase in _normalize_text(item.text) for phrase in ("no active agent runs", "no active runs"))
    ]

    latest_success = success_runs[-1] if success_runs else None
    latest_operator_success = operator_success_runs[-1] if operator_success_runs else None
    latest_blocked_trigger = blocked_triggers[-1] if blocked_triggers else None
    latest_parked = parked_items[-1] if parked_items else None

    if latest_operator_success and latest_blocked_trigger:
        contradictions.append(
            "Recent operator-driven role execution succeeded even while trigger history shows autonomy blocked by a parked mission, so manual execution and autonomous continuation are diverging rather than agreeing."
        )

    if latest_success and no_active_claims:
        contradictions.append(
            "Recent execution artifacts exist, but at least one reflection frame says there are no active runs; the mission needs a timeline-aware distinction between historical success and currently active work."
        )

    if latest_parked and len(success_runs) >= 2:
        patterns.append(
            f"Artifact history kept growing while the mission stayed parked, with {len(success_runs)} successful role run artifacts still visible in mission-local notes."
        )

    if blocked_triggers and operator_success_runs:
        patterns.append(
            f"Operator-driven activity remains visible ({len(operator_success_runs)} successful run artifact{'s' if len(operator_success_runs) != 1 else ''}) even though trigger-driven autonomy is blocked."
        )

    summary_note = None
    if latest_operator_success and latest_blocked_trigger:
        summary_note = (
            "Recent operator-driven successes do not clear the parked, blocked autonomy posture; they show that manual invocation can still work while autonomous continuation remains blocked."
        )
    elif latest_success and latest_parked:
        summary_note = "Recent execution should be read as artifact history, not proof that the parked mission is currently active."

    if not any(item.timestamp for item in success_runs + blocked_triggers + parked_items):
        gaps.append("Recent run, trigger, or parking evidence is present but weakly timestamped, which makes timeline comparison less reliable.")

    return contradictions, patterns, gaps, summary_note


def _find_contradictions(items: list[MemoryItem]) -> list[str]:
    contradictions: list[str] = []
    by_speaker: dict[str, set[str]] = {}
    for item in items:
        normalized = _normalize_text(item.text)
        if normalized in AFFIRMATIVE_SIGNALS:
            by_speaker.setdefault(item.speaker, set()).add("affirmative")
        if normalized in NEGATIVE_SIGNALS:
            by_speaker.setdefault(item.speaker, set()).add("negative")
    for speaker, signals in sorted(by_speaker.items()):
        if {"affirmative", "negative"}.issubset(signals):
            contradictions.append(
                f"{speaker} alternates between affirmative and negative control signals, so intent appears to shift faster than context."
            )

    structured_pairs: dict[tuple[str, str], set[str]] = {}
    for item in items:
        for key, value in item.payload.items():
            if isinstance(value, (str, bool, int, float)) and key in {"status", "parked_by", "reason"}:
                structured_pairs.setdefault((item.source_ref, key), set()).add(str(value).strip().lower())
    for (_source_ref, key), values in structured_pairs.items():
        meaningful = {value for value in values if value}
        if key == "status" and {"active", "parked"}.issubset(meaningful):
            contradictions.append("Structured memory flips between 'active' and 'parked', suggesting unresolved session state.")
            break
    timeline_contradictions, _, _, _ = _find_timeline_mismatches(items)
    for line in timeline_contradictions:
        if line not in contradictions:
            contradictions.append(line)
    return contradictions


def _find_gaps(items: list[MemoryItem]) -> list[str]:
    gaps: list[str] = []
    unresolved_questions = [
        item for item in items if item.speaker in {"assistant", "system"} and item.text.strip().endswith(QUESTION_SUFFIX)
    ]
    if unresolved_questions:
        last_question = _normalize_text(unresolved_questions[-1].text)
        if not any(
            item.speaker == "user" and len(_normalize_text(item.text).split()) > SHORT_SIGNAL_LIMIT
            for item in items[items.index(unresolved_questions[-1]) + 1 :]
        ):
            gaps.append(f"Latest open question remains thinly answered: '{last_question}'.")

    if not any(item.speaker == "user" and len(_normalize_text(item.text).split()) >= 6 for item in items):
        gaps.append("There is very little high-context user language, so mission intent remains weakly grounded in memory.")

    timestamped = sum(1 for item in items if item.timestamp)
    if timestamped < len(items):
        gaps.append("Some memory items lack timestamps, which weakens pattern-over-time interpretation.")
    _, _, timeline_gaps, _ = _find_timeline_mismatches(items)
    for line in timeline_gaps:
        if line not in gaps:
            gaps.append(line)
    return gaps


def _build_summary(items: list[MemoryItem], patterns: list[str], contradictions: list[str], gaps: list[str], summary_note: str | None = None) -> str:
    dominant_speaker = Counter(item.speaker for item in items).most_common(1)[0][0]
    summary_parts = [
        f"This session reads as a memory of coordination rather than resolution, with {len(items)} interpretable records led mostly by {dominant_speaker}.",
    ]
    if patterns:
        summary_parts.append("Repeated signals outweigh rich context, so the memory carries rhythm more strongly than explanation.")
    if contradictions:
        summary_parts.append("Intent shows at least one tension or reversal instead of a single stable trajectory.")
    if gaps:
        summary_parts.append("Missing context limits how confidently the session meaning can be reconstructed.")
    if summary_note:
        summary_parts.append(summary_note)
    return " ".join(summary_parts)


def _build_suggested_focus(patterns: list[str], contradictions: list[str], gaps: list[str]) -> list[str]:
    focus: list[str] = []
    if contradictions:
        focus.append("The strongest meaning sits in where control signals reverse or compete.")
    if gaps:
        focus.append("The next useful reflection surface is the missing context around the unresolved question or thin user replies.")
    if patterns:
        focus.append("Repeated phrasing appears more durable than any single reply and likely defines the session memory trace.")
    if not focus:
        focus.append("The memory is internally consistent but still best understood as a pattern trace rather than a task record.")
    return focus[:3]


def _scripted_model_binding(source: str, *, active: bool, error: str | None = None) -> dict[str, Any]:
    binding = {
        "role_id": PROFILE.role_id,
        "active_flag": PROFILE.active,
        "execution_backend": PROFILE.execution_backend,
        "model_key": PROFILE.default_model_key,
        "fallback_model_key": PROFILE.fallback_model_key,
        "provider_requirement": PROFILE.provider_requirement,
        "active": active,
        "source": source,
    }
    if error:
        binding["error"] = error
    return binding


def _scripted_reflection(items: list[MemoryItem], *, model_binding: dict[str, Any] | None = None) -> dict[str, Any]:
    repeated = _find_repeated_messages(items)
    role_patterns = _find_role_patterns(items)
    timeline_contradictions, timeline_patterns, timeline_gaps, summary_note = _find_timeline_mismatches(items)
    patterns = repeated + [line for line in role_patterns if line not in repeated]
    for line in timeline_patterns:
        if line not in patterns:
            patterns.append(line)
    contradictions = _find_contradictions(items)
    for line in timeline_contradictions:
        if line not in contradictions:
            contradictions.append(line)
    gaps = _find_gaps(items)
    for line in timeline_gaps:
        if line not in gaps:
            gaps.append(line)
    return {
        "role": PROFILE.role_id,
        "kind": "mirror_reflection",
        "summary": _build_summary(items, patterns, contradictions, gaps, summary_note),
        "patterns": patterns,
        "contradictions": contradictions,
        "gaps": gaps,
        "suggested_focus": _build_suggested_focus(patterns, contradictions, gaps),
        "source_refs": sorted({item.source_ref for item in items}),
        "model_binding": model_binding or _scripted_model_binding("scripted", active=False),
    }


def _normalize_string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise MirrorReflectError(f"Model field '{field}' must be a list")
    out: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            raise MirrorReflectError(f"Model field '{field}' item {idx} must be a string")
        text = item.strip()
        if text:
            out.append(text)
    return out


def _model_prompt(items: list[MemoryItem]) -> str:
    timeline_contradictions, timeline_patterns, timeline_gaps, summary_note = _find_timeline_mismatches(items)
    model_context = _build_model_context(items)
    prompt = {
        "role": "Spinetop-Mirror",
        "task": "Read memory-like inputs and produce a reflective mission-local interpretation only.",
        "authority_boundary": {
            "may_read": list(PROFILE.authority_boundary.get("may_read") or []),
            "may_write_only": list(PROFILE.authority_boundary.get("may_write_only") or []),
            "may_not": list(PROFILE.authority_boundary.get("may_not") or []),
            "critical_rule": "Mirror reads memory. Mirror never writes to memory.",
        },
        "required_output_schema": {
            "summary": "string",
            "patterns": ["string"],
            "contradictions": ["string"],
            "gaps": ["string"],
            "suggested_focus": ["string"],
        },
        "requirements": [
            "Return only structured reflection fields.",
            "Stay mission-local and derived-only.",
            "Do not answer tasks, approve actions, or act as governance.",
            "Do not propose writes to Honcho or any mutation of sessions/messages/peers.",
            "Prefer recent timestamped evidence over static state snapshots when they differ.",
            "Explicitly compare recent execution artifacts, current mission posture, autonomy status, and trigger history.",
            "Distinguish operator-driven or manual execution from autonomy-driven execution.",
            "Treat 'recent execution but no active runs' as a possible timeline mismatch, not automatic consistency.",
        ],
        "timeline_cues": {
            "candidate_contradictions": timeline_contradictions,
            "candidate_patterns": timeline_patterns,
            "candidate_gaps": timeline_gaps,
            "summary_note": summary_note or "",
        },
        "context_window": model_context["context_window"],
        "history_summary": model_context["history_summary"],
        "memory_items": model_context["memory_items"],
    }
    return json.dumps(prompt, indent=2, ensure_ascii=False)


def _build_model_reflection(items: list[MemoryItem]) -> dict[str, Any]:
    binding = _scripted_model_binding(
        "model",
        active=PROFILE.active and PROFILE.execution_backend == "model_backed" and bool(PROFILE.default_model_key),
    )
    fallback = _scripted_reflection(items, model_binding=_scripted_model_binding("disabled_safe_scripted_fallback", active=False))
    timeline_contradictions, timeline_patterns, timeline_gaps, summary_note = _find_timeline_mismatches(items)
    if not binding["active"]:
        return fallback

    prompt = _model_prompt(items)
    try:
        raw = invoke_model(
            str(binding["model_key"]),
            prompt,
            load_hermes_runtime_config(),
            system_prompt=(
                "You are Spinetop-Mirror. Return only a JSON object with summary, patterns, contradictions, "
                "gaps, and suggested_focus. Mirror reads memory and never writes to memory. "
                "Do not write to Honcho, do not mutate sessions/messages/peers, and do not claim authority."
            ),
            response_format="json_object",
        )
        candidate = extract_json_candidate(raw)
        payload = json.loads(candidate)
        reflection = {
            "role": PROFILE.role_id,
            "kind": "mirror_reflection",
            "summary": str(payload.get("summary") or "").strip(),
            "patterns": _normalize_string_list(payload.get("patterns"), field="patterns"),
            "contradictions": _normalize_string_list(payload.get("contradictions"), field="contradictions"),
            "gaps": _normalize_string_list(payload.get("gaps"), field="gaps"),
            "suggested_focus": _normalize_string_list(payload.get("suggested_focus"), field="suggested_focus"),
            "source_refs": sorted({item.source_ref for item in items}),
            "model_binding": binding,
        }
        for line in timeline_patterns:
            if line not in reflection["patterns"]:
                reflection["patterns"].append(line)
        for line in timeline_contradictions:
            if line not in reflection["contradictions"]:
                reflection["contradictions"].append(line)
        for line in timeline_gaps:
            if line not in reflection["gaps"]:
                reflection["gaps"].append(line)
        if summary_note and summary_note not in reflection["summary"]:
            reflection["summary"] = f"{reflection['summary']} {summary_note}".strip()
        if not reflection["summary"]:
            raise MirrorReflectError("Model field 'summary' must be a non-empty string")
        _append_jsonl(
            MIRROR_MODEL_LOG,
            {
                "timestamp": utc_now_iso(),
                "role": PROFILE.role_id,
                "status": "success",
                "model_key": binding["model_key"],
                "artifact_kind": "mirror_reflection",
                "source_ref_count": len(reflection["source_refs"]),
            },
        )
        return reflection
    except Exception as exc:
        fallback["model_binding"] = _scripted_model_binding("model_failure_fallback", active=False, error=str(exc))
        _append_jsonl(
            MIRROR_MODEL_LOG,
            {
                "timestamp": utc_now_iso(),
                "role": PROFILE.role_id,
                "status": "failure",
                "model_key": binding["model_key"],
                "artifact_kind": "mirror_reflection",
                "error": str(exc),
            },
        )
        return fallback


def build_reflection(items: list[MemoryItem]) -> dict[str, Any]:
    return _build_model_reflection(items)


def write_reflection(path: Path, reflection: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reflection, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Produce a read-only Mirror reflection from memory-like inputs.")
    parser.add_argument("--mission-id", required=True, help="Mission id used to validate mirror output scope.")
    parser.add_argument("--input", dest="inputs", action="append", required=True, help="JSON or JSONL memory input path.")
    parser.add_argument(
        "--output",
        help="Optional output path under workbench/missions/<mission_id>/notes/mirror/. Defaults to stdout only.",
    )
    args = parser.parse_args(argv)

    items = load_memory_items(args.inputs)
    reflection = build_reflection(items)
    output_path = resolve_output_path(args.mission_id, args.output)
    if output_path is not None:
        write_reflection(output_path, reflection)
    json.dump(reflection, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
