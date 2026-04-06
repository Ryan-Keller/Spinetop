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


class MirrorReflectError(ValueError):
    pass


@dataclass(frozen=True)
class MemoryItem:
    source_ref: str
    timestamp: str
    speaker: str
    text: str
    payload: dict[str, Any]


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


def _append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False) + "\n")


def load_memory_items(paths: list[str]) -> list[MemoryItem]:
    items: list[MemoryItem] = []
    for raw_path in paths:
        path = _resolve_input_path(raw_path)
        for record in _load_jsonish(path):
            text = _extract_text(record)
            if not text:
                continue
            items.append(
                MemoryItem(
                    source_ref=_path_to_ref(path),
                    timestamp=_extract_timestamp(record),
                    speaker=_extract_speaker(record),
                    text=text,
                    payload=record,
                )
            )
    if not items:
        raise MirrorReflectError("Mirror needs at least one readable memory item")
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
    return gaps


def _build_summary(items: list[MemoryItem], patterns: list[str], contradictions: list[str], gaps: list[str]) -> str:
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
    patterns = repeated + [line for line in role_patterns if line not in repeated]
    contradictions = _find_contradictions(items)
    gaps = _find_gaps(items)
    return {
        "role": PROFILE.role_id,
        "kind": "mirror_reflection",
        "summary": _build_summary(items, patterns, contradictions, gaps),
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
        ],
        "memory_items": [
            {
                "source_ref": item.source_ref,
                "timestamp": item.timestamp,
                "speaker": item.speaker,
                "text": item.text,
            }
            for item in items
        ],
    }
    return json.dumps(prompt, indent=2, ensure_ascii=False)


def _build_model_reflection(items: list[MemoryItem]) -> dict[str, Any]:
    binding = _scripted_model_binding(
        "model",
        active=PROFILE.active and PROFILE.execution_backend == "model_backed" and bool(PROFILE.default_model_key),
    )
    fallback = _scripted_reflection(items, model_binding=_scripted_model_binding("disabled_safe_scripted_fallback", active=False))
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
