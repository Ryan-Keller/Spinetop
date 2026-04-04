from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ALLOWED_STATUS = {"needs_input", "provisional"}
ALLOWED_IMPACT = {"low", "medium", "high"}
ALLOWED_ASSUMPTION_TYPE = {"pattern_based", "default", "task_inferred"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _numeric(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    number = float(value)
    if number < 0.0 or number > 1.0:
        raise ValueError(f"{field} must be between 0.0 and 1.0")
    return number


def _validate_string_list(values: Any, field: str) -> list[str]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{field} must be a non-empty list of strings")
    items: list[str] = []
    for item in values:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must be a non-empty list of strings")
        items.append(item.strip())
    return items


def _validate_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _validate_limiters(value: Any) -> list[dict[str, Any]]:
    limiters = _validate_object(value, "confidence_analysis")["confidence_limiters"] if isinstance(value, dict) else None
    if not isinstance(limiters, list) or not limiters:
        raise ValueError("confidence_analysis.confidence_limiters must be a non-empty list")
    items: list[dict[str, Any]] = []
    for limiter in limiters:
        if not isinstance(limiter, dict):
            raise ValueError("confidence_analysis.confidence_limiters entries must be objects")
        factor = _text(limiter.get("factor"))
        impact = _text(limiter.get("impact"))
        reason = _text(limiter.get("reason"))
        if not factor:
            raise ValueError("confidence_analysis.confidence_limiters.factor must be a non-empty string")
        if impact not in ALLOWED_IMPACT:
            raise ValueError(f"confidence_analysis.confidence_limiters.impact must be one of {sorted(ALLOWED_IMPACT)}")
        if not reason:
            raise ValueError("confidence_analysis.confidence_limiters.reason must be a non-empty string")
        items.append({"factor": factor, "impact": impact, "reason": reason})
    return items


def _validate_assumptions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("assumptions must be a non-empty list")
    items: list[dict[str, Any]] = []
    for assumption in value:
        if not isinstance(assumption, dict):
            raise ValueError("assumptions entries must be objects")
        assumption_id = _text(assumption.get("assumption_id"))
        statement = _text(assumption.get("statement"))
        source = _text(assumption.get("source"))
        assumption_type = _text(assumption.get("type"))
        confidence = assumption.get("confidence")
        if not assumption_id:
            raise ValueError("assumptions.assumption_id must be a non-empty string")
        if not statement:
            raise ValueError("assumptions.statement must be a non-empty string")
        if not source:
            raise ValueError("assumptions.source must be a non-empty string")
        if assumption_type not in ALLOWED_ASSUMPTION_TYPE:
            raise ValueError(f"assumptions.type must be one of {sorted(ALLOWED_ASSUMPTION_TYPE)}")
        items.append({
            "assumption_id": assumption_id,
            "statement": statement,
            "confidence": _numeric(confidence, "assumptions.confidence"),
            "source": source,
            "type": assumption_type,
        })
    return items


def _validate_deductive_options(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("deductive_options must be a non-empty list")
    items: list[dict[str, Any]] = []
    for option in value:
        if not isinstance(option, dict):
            raise ValueError("deductive_options entries must be objects")
        option_id = _text(option.get("option_id"))
        label = _text(option.get("label"))
        reasoning = _text(option.get("reasoning"))
        if not option_id:
            raise ValueError("deductive_options.option_id must be a non-empty string")
        if not label:
            raise ValueError("deductive_options.label must be a non-empty string")
        if not reasoning:
            raise ValueError("deductive_options.reasoning must be a non-empty string")
        items.append({
            "option_id": option_id,
            "label": label,
            "confidence": _numeric(option.get("confidence"), "deductive_options.confidence"),
            "reasoning": reasoning,
        })
    return items


def _validate_questions(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError("clarifying_questions_ranked must be a non-empty list")
    items: list[dict[str, str]] = []
    for question in value:
        if not isinstance(question, dict):
            raise ValueError("clarifying_questions_ranked entries must be objects")
        text = _text(question.get("question"))
        impact = _text(question.get("impact"))
        if not text:
            raise ValueError("clarifying_questions_ranked.question must be a non-empty string")
        if impact not in ALLOWED_IMPACT:
            raise ValueError(f"clarifying_questions_ranked.impact must be one of {sorted(ALLOWED_IMPACT)}")
        items.append({"question": text, "impact": impact})
    return items


def validate_clarification_packet(data: Any, path: Path | None = None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("clarification packet must be a JSON object")

    required = [
        "packet_id",
        "mission_id",
        "mode",
        "status",
        "known_facts",
        "missing_facts",
        "confidence_analysis",
        "assumptions",
        "provisional_answer",
        "deductive_options",
        "clarifying_questions_ranked",
        "confidence_projection",
        "created_at",
    ]
    missing = [field for field in required if field not in data]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")

    packet_id = _text(data["packet_id"])
    mission_id = _text(data["mission_id"])
    mode = _text(data["mode"])
    status = _text(data["status"])
    created_at = _text(data["created_at"])
    if not packet_id:
        raise ValueError("packet_id must be a non-empty string")
    if not mission_id:
        raise ValueError("mission_id must be a non-empty string")
    if not mode:
        raise ValueError("mode must be a non-empty string")
    if status not in ALLOWED_STATUS:
        raise ValueError(f"status must be one of {sorted(ALLOWED_STATUS)}")
    if not created_at:
        raise ValueError("created_at must be a non-empty string")

    known_facts = _validate_string_list(data["known_facts"], "known_facts")
    missing_facts = _validate_string_list(data["missing_facts"], "missing_facts")

    confidence_analysis = _validate_object(data["confidence_analysis"], "confidence_analysis")
    if "current_confidence" not in confidence_analysis:
        raise ValueError("confidence_analysis.current_confidence is required")
    current_confidence = _numeric(confidence_analysis["current_confidence"], "confidence_analysis.current_confidence")
    confidence_limiters = _validate_limiters(confidence_analysis)

    assumptions = _validate_assumptions(data["assumptions"])

    provisional_answer = _validate_object(data["provisional_answer"], "provisional_answer")
    text = _text(provisional_answer.get("text"))
    assumption_dependencies = _validate_string_list(provisional_answer.get("assumption_dependencies"), "provisional_answer.assumption_dependencies")
    if not text:
        raise ValueError("provisional_answer.text must be a non-empty string")

    deductive_options = _validate_deductive_options(data["deductive_options"])
    clarifying_questions_ranked = _validate_questions(data["clarifying_questions_ranked"])

    confidence_projection = _validate_object(data["confidence_projection"], "confidence_projection")
    if "if_no_answer" not in confidence_projection or "if_answered" not in confidence_projection:
        raise ValueError("confidence_projection must include if_no_answer and if_answered")
    if_no_answer = _numeric(confidence_projection["if_no_answer"], "confidence_projection.if_no_answer")
    if_answered = _numeric(confidence_projection["if_answered"], "confidence_projection.if_answered")
    if if_answered < if_no_answer:
        raise ValueError("confidence_projection.if_answered must be greater than or equal to if_no_answer")

    packet = dict(data)
    packet.update({
        "packet_id": packet_id,
        "mission_id": mission_id,
        "mode": mode,
        "status": status,
        "known_facts": known_facts,
        "missing_facts": missing_facts,
        "confidence_analysis": {
            "current_confidence": current_confidence,
            "confidence_limiters": confidence_limiters,
        },
        "assumptions": assumptions,
        "provisional_answer": {
            "text": text,
            "assumption_dependencies": assumption_dependencies,
        },
        "deductive_options": deductive_options,
        "clarifying_questions_ranked": clarifying_questions_ranked,
        "confidence_projection": {
            "if_no_answer": if_no_answer,
            "if_answered": if_answered,
        },
        "created_at": created_at,
    })
    return packet


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a clarification reasoning packet JSON file.")
    parser.add_argument("path", help="Path to a clarification packet JSON file")
    args = parser.parse_args()
    path = Path(args.path)
    try:
        packet = validate_clarification_packet(_load_json(path), path=path)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(packet, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
