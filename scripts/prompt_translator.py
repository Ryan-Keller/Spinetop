from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repo_paths import repo_root
from state_machine import normalize_mission_id


ROOT = repo_root()
WORKBENCH_MISSIONS_DIR = ROOT / "workbench" / "missions"
PROMPT_TRANSLATOR_DIRNAME = "prompt_translator"

ROLE_VALUES = {"sentinel", "expeditioner", "helper_2b", "mirror", "operator"}
MODE_VALUES = {"review", "first_pass", "reflect", "retry", "resume", "clarify", "unknown"}
TARGET_VALUES = {"existing_mission", "new_mission", "unknown"}
SCOPE_VALUES = {"mission_local_only", "read_only", "support_lane_only", "unknown"}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _short_digest(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _translator_dir(mission_id: str, *, ensure: bool = False) -> Path:
    mission = normalize_mission_id(mission_id)
    path = WORKBENCH_MISSIONS_DIR / mission / "notes" / PROMPT_TRANSLATOR_DIRNAME
    if ensure:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _relative_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except Exception:
        return path.as_posix()


def _mentions_any(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _extract_missing_requirements(text: str) -> list[str]:
    requirements: list[str] = []
    if re.search(r"\b(summarize|review|analyze)\s+(this|my|the)\s+(text|article|document|note|transcript)\b", text):
        requirements.append("Provide the text or document to inspect.")
    if re.search(r"\b(fix|debug|review|analyze)\s+(this|my|the)\s+(code|script|program|error|stack trace|log)\b", text):
        requirements.append("Provide the code, error output, or logs.")
    if re.search(r"\b(analyze|review)\s+(this|my|the)\s+(dataset|data|csv|spreadsheet|table|report)\b", text):
        requirements.append("Provide the dataset or a representative sample.")
    return requirements


def _recommended_role(text: str, missing_requirements: list[str]) -> str:
    if _mentions_any(text, ["mirror", "reflect", "memory", "contradiction", "recall"]):
        return "mirror"
    if _mentions_any(text, ["review", "inspect", "verify", "check", "audit", "safe"]):
        return "sentinel"
    if _mentions_any(text, ["fetch", "gather", "retrieve", "lookup", "evidence", "receipt", "runner return"]):
        return "helper_2b"
    if _mentions_any(text, ["approve", "submit", "dispatch", "bridge", "governance", "promote", "truth"]):
        return "operator"
    if missing_requirements:
        return "operator"
    return "expeditioner"


def _recommended_mode(text: str, missing_requirements: list[str]) -> str:
    if missing_requirements:
        return "clarify"
    if _mentions_any(text, ["resume", "unpause", "continue mission"]):
        return "resume"
    if _mentions_any(text, ["retry", "again", "re-run", "rerun", "refresh"]):
        return "retry"
    if _mentions_any(text, ["mirror", "reflect", "memory", "contradiction"]):
        return "reflect"
    if _mentions_any(text, ["review", "inspect", "verify", "check", "audit"]):
        return "review"
    if _mentions_any(text, ["build", "write", "draft", "make", "create", "fix", "analyze", "investigate"]):
        return "first_pass"
    return "unknown"


def _scope(text: str, role: str) -> str:
    if role == "mirror" or _mentions_any(text, ["review", "inspect", "verify", "check", "read-only", "read only"]):
        return "read_only"
    if role == "helper_2b" or _mentions_any(text, ["support lane", "retrieval", "runner return", "helper"]):
        return "support_lane_only"
    if _mentions_any(text, ["governance", "truth", "collective", "honcho", "dispatch approved", "promotion"]):
        return "unknown"
    return "mission_local_only"


def _target_type(text: str, mission_id: str | None) -> tuple[str, str | None]:
    if _mentions_any(text, ["new mission", "separate mission", "another mission", "fresh mission"]):
        return "new_mission", None
    if mission_id:
        return "existing_mission", normalize_mission_id(mission_id)
    return "unknown", None


def _recommended_safe_action(
    *,
    target_type: str,
    role: str,
    mode: str,
    scope: str,
    missing_requirements: list[str],
    requires_operator_confirmation: bool,
) -> str:
    if missing_requirements:
        return "Collect the missing artifact and wait for operator review before any execution step."
    if scope == "unknown" or role == "operator":
        return "Keep this as a proposal only and require explicit operator review before any governed or truth-lane step."
    if target_type == "new_mission":
        return "Present this as a proposed new mission and wait for operator confirmation before creating or resuming anything."
    if mode == "resume":
        return "Propose a bounded mission resume and wait for explicit operator confirmation."
    if mode == "retry":
        return "Propose one bounded retry plan for operator review; do not submit or trigger it automatically."
    if requires_operator_confirmation:
        return "Hold this as a mission-local proposed action packet for operator review."
    return "Store this as a mission-local proposed action packet for inspection only."


def _translated_instruction(
    *,
    source_text: str,
    target_type: str,
    target_mission_id: str | None,
    role: str,
    mode: str,
    scope: str,
    missing_requirements: list[str],
) -> str:
    action_line = f"Proposed role={role}; mode={mode}; scope={scope}; target={target_type}"
    if target_mission_id:
        action_line += f" ({target_mission_id})"
    if missing_requirements:
        return (
            f"{action_line}. Block execution and request the missing requirement(s): "
            + "; ".join(missing_requirements)
        )
    cleaned = source_text.strip()
    return f"{action_line}. Translate the operator intent into one bounded, inspectable mission-local instruction: {cleaned}"


def translate_prompt(source_text: str, *, mission_id: str | None = None) -> dict[str, Any]:
    normalized_source = str(source_text or "").strip()
    lowered = _normalize_text(source_text).lower()
    normalized_mission = normalize_mission_id(mission_id) if mission_id else None
    target_type, target_mission_id = _target_type(lowered, normalized_mission)
    missing_requirements = _extract_missing_requirements(lowered)
    role = _recommended_role(lowered, missing_requirements)
    mode = _recommended_mode(lowered, missing_requirements)
    scope = _scope(lowered, role)
    requires_operator_confirmation = bool(
        missing_requirements
        or target_type != "existing_mission"
        or role == "operator"
        or mode in {"retry", "resume", "unknown"}
        or scope == "unknown"
    )
    notes: list[str] = []
    if target_type == "new_mission":
        notes.append("The prompt appears to describe a new mission rather than work inside the current mission.")
    if missing_requirements:
        notes.append("The prompt references an external artifact that is not present in the translator input.")
    if role == "operator":
        notes.append("The prompt touches operator-only or governed concepts, so the translator keeps the result proposal-only.")
    if scope == "unknown":
        notes.append("The requested scope may cross governance or truth-lane boundaries and must stay blocked for review.")
    if not notes:
        notes.append("The translator classified this request using bounded local heuristics only.")

    created_at = iso_now()
    mission_segment = target_mission_id or "request_local"
    translation_id = (
        f"translation_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        f"_{_short_digest(f'{mission_segment}|{normalized_source}|{created_at}')}"
    )

    result = {
        "translation_id": translation_id,
        "created_at": created_at,
        "source_text": normalized_source,
        "target_type": target_type,
        "target_mission_id": target_mission_id,
        "recommended_role": role if role in ROLE_VALUES else "operator",
        "recommended_mode": mode if mode in MODE_VALUES else "unknown",
        "scope": scope if scope in SCOPE_VALUES else "unknown",
        "sufficiency": {
            "can_proceed": not missing_requirements and bool(normalized_source),
            "missing_requirements": missing_requirements,
        },
        "recommended_safe_action": _recommended_safe_action(
            target_type=target_type,
            role=role,
            mode=mode,
            scope=scope,
            missing_requirements=missing_requirements,
            requires_operator_confirmation=requires_operator_confirmation,
        ),
        "requires_operator_confirmation": requires_operator_confirmation,
        "translated_instruction": _translated_instruction(
            source_text=normalized_source,
            target_type=target_type,
            target_mission_id=target_mission_id,
            role=role,
            mode=mode,
            scope=scope,
            missing_requirements=missing_requirements,
        ),
        "notes": notes,
        "derived_only": True,
    }
    return result


def write_translation_result(mission_id: str, result: dict[str, Any]) -> Path:
    mission = normalize_mission_id(mission_id)
    path = _translator_dir(mission, ensure=True) / f"{str(result.get('translation_id') or 'translation').strip()}.json"
    payload = dict(result)
    payload["target_mission_id"] = mission if str(payload.get("target_mission_id") or "").strip() in {"", mission} else payload.get("target_mission_id")
    payload["path"] = _relative_path(path)
    _write_json(path, payload)
    return path


def translate_and_store_prompt(source_text: str, *, mission_id: str) -> dict[str, Any]:
    result = translate_prompt(source_text, mission_id=mission_id)
    path = write_translation_result(mission_id, result)
    stored = _load_json(path)
    return stored if isinstance(stored, dict) else {**result, "path": _relative_path(path)}


def read_prompt_translations(mission_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = _translator_dir(mission_id)
    if not root.exists():
        return rows
    for path in sorted(root.glob("*.json")):
        payload = _load_json(path)
        if not isinstance(payload, dict):
            continue
        payload.setdefault("path", _relative_path(path))
        rows.append(payload)
    rows.sort(
        key=lambda item: (
            str(item.get("created_at") or ""),
            str(item.get("translation_id") or ""),
        ),
        reverse=True,
    )
    return rows


def read_latest_prompt_translation(mission_id: str) -> dict[str, Any] | None:
    rows = read_prompt_translations(mission_id)
    return rows[0] if rows else None
