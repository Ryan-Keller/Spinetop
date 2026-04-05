from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repo_paths import repo_root


ROOT = repo_root()
CLARIFICATION_PACKETS_DIR = ROOT / "logs" / "citadel" / "clarification_packets"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_digest(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clamp_confidence(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(value)
        except Exception:
            return fallback
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return 1.0
    return number


def _normalize_task(task: str) -> str:
    return " ".join(_text(task).split())


def _task_signals(task: str) -> dict[str, bool]:
    normalized = f" {_normalize_task(task).lower()} "
    personal = any(marker in normalized for marker in (" my ", " your ", " this ", " our "))
    open_ended = _normalize_task(task).lower().startswith(
        (
            "how ",
            "what ",
            "why ",
            "can you ",
            "could you ",
            "should i ",
            "please ",
            "review ",
            "analyze ",
            "analyse ",
            "assess ",
            "suggest ",
            "teach ",
            "help ",
            "explain ",
        )
    )
    return {"personal": personal, "open_ended": open_ended}


def _known_facts(task: str, hermes_result: dict[str, Any]) -> list[str]:
    facts: list[str] = []
    task_text = _normalize_task(task)
    if task_text:
        facts.append(f"Task text: {task_text}")

    mode = _text(hermes_result.get("mode"))
    if mode:
        facts.append(f"Sentinel mode: {mode}")

    status = _text(hermes_result.get("status"))
    if status:
        facts.append(f"Sentinel status: {status}")

    action = _text(hermes_result.get("recommended_action"))
    if action:
        facts.append(f"Recommended action: {action}")

    summary = _text(hermes_result.get("summary"))
    if summary:
        facts.append(f"Summary: {summary}")

    evidence_refs = hermes_result.get("evidence_refs")
    if isinstance(evidence_refs, list) and evidence_refs:
        facts.append(f"Evidence refs count: {len(evidence_refs)}")

    petition_kind = hermes_result.get("petition_kind")
    if petition_kind is not None:
        facts.append(f"Petition kind: {_text(petition_kind)}")

    confidence = _clamp_confidence(hermes_result.get("confidence"), fallback=0.0)
    facts.append(f"Sentinel confidence: {confidence:.2f}")
    return facts


def _missing_facts(task: str, hermes_result: dict[str, Any]) -> list[str]:
    facts: list[str] = []
    signals = _task_signals(task)

    if signals["personal"]:
        facts.append("The task refers to a personal or implicit subject, but the concrete subject details are not explicit.")
    if signals["open_ended"]:
        facts.append("The task is phrased as an open-ended request, so the desired outcome is not fully bounded.")

    status = _text(hermes_result.get("status"))
    if status == "summary_only":
        facts.append("Sentinel returned a summary-only result rather than a direct action.")

    action = _text(hermes_result.get("recommended_action"))
    if action == "defer":
        facts.append("Sentinel recommended defer instead of a concrete action.")

    petition_kind = hermes_result.get("petition_kind")
    if petition_kind is None:
        facts.append("Sentinel did not specify a petition kind.")

    evidence_refs = hermes_result.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        facts.append("No supporting evidence references were present in the Sentinel result.")

    classification = hermes_result.get("classification")
    if classification is None:
        facts.append("No classification metadata was present in the Sentinel result.")

    if not facts:
        facts.append("The request still lacks a concrete subject and enough context to answer confidently.")

    deduped: list[str] = []
    for fact in facts:
        fact = _text(fact)
        if fact and fact not in deduped:
            deduped.append(fact)
    return deduped


def _limiter_for_fact(fact: str) -> dict[str, str]:
    lower = fact.lower()
    if "personal" in lower or "implicit subject" in lower:
        return {
            "factor": "missing_subject_context",
            "impact": "high",
            "reason": fact,
        }
    if "open-ended" in lower or "desired outcome" in lower:
        return {
            "factor": "unbounded_request",
            "impact": "medium",
            "reason": fact,
        }
    if "summary-only" in lower or "summary only" in lower:
        return {
            "factor": "summary_only_output",
            "impact": "high",
            "reason": fact,
        }
    if "petition kind" in lower:
        return {
            "factor": "missing_petition_kind",
            "impact": "medium",
            "reason": fact,
        }
    if "evidence" in lower:
        return {
            "factor": "missing_supporting_evidence",
            "impact": "medium",
            "reason": fact,
        }
    if "classification" in lower:
        return {
            "factor": "missing_classification",
            "impact": "low",
            "reason": fact,
        }
    return {
        "factor": "context_gap",
        "impact": "medium",
        "reason": fact,
    }


def _assumptions(task: str, hermes_result: dict[str, Any], known_facts: list[str]) -> list[dict[str, Any]]:
    task_text = _normalize_task(task)
    task_lower = task_text.lower()
    assumptions: list[dict[str, Any]] = []

    if "dog" in task_lower:
        assumptions.append({
            "assumption_id": "assumption_1",
            "statement": "The task is asking about a household dog rather than a general animal-behavior question.",
            "confidence": 0.35,
            "source": "task text",
            "type": "task_inferred",
        })
    elif "anomal" in task_lower:
        assumptions.append({
            "assumption_id": "assumption_1",
            "statement": "The task is about recent anomalies in the current workspace context rather than an external incident.",
            "confidence": 0.45,
            "source": "task text",
            "type": "task_inferred",
        })
    else:
        assumptions.append({
            "assumption_id": "assumption_1",
            "statement": "The task wants the smallest safe next step, not a broad policy rewrite.",
            "confidence": 0.40,
            "source": "task text",
            "type": "default",
        })

    summary = _text(hermes_result.get("summary"))
    assumptions.append({
        "assumption_id": "assumption_2",
        "statement": f"Sentinel summary is the best available provisional answer: {summary or 'summary unavailable'}",
        "confidence": 0.55,
        "source": "Sentinel result",
        "type": "default",
    })

    if len(known_facts) >= 3:
        assumptions.append({
            "assumption_id": "assumption_3",
            "statement": "The available context is enough to suggest a cautious direction, but not enough to finalize the answer.",
            "confidence": 0.45,
            "source": "Sentinel result",
            "type": "pattern_based",
        })

    return assumptions


def _deductive_options(task: str, hermes_result: dict[str, Any], missing_facts: list[str], current_confidence: float) -> list[dict[str, Any]]:
    trigger_count = len(missing_facts)
    questionable = trigger_count > 0
    if questionable:
        first_confidence = min(0.95, max(0.30, 0.55 + 0.05 * trigger_count))
        second_confidence = min(0.95, max(0.20, current_confidence))
    else:
        first_confidence = min(0.95, max(0.30, current_confidence))
        second_confidence = max(0.10, min(0.70, current_confidence - 0.10))

    summary = _text(hermes_result.get("summary"))
    return [
        {
            "option_id": "option_1",
            "label": "Ask for the missing context before acting",
            "confidence": first_confidence,
            "reasoning": "The packet was created because the run lacked enough explicit context to finish cleanly.",
        },
        {
            "option_id": "option_2",
            "label": "Proceed with a conservative provisional answer",
            "confidence": second_confidence,
            "reasoning": summary or "Use the Sentinel result as a weak provisional answer and avoid overcommitting.",
        },
    ]


def _clarifying_questions(missing_facts: list[str]) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    for fact in missing_facts:
        lower = fact.lower()
        if "personal" in lower or "implicit subject" in lower or "subject details" in lower:
            question = "What exact subject or situation should I tailor the answer to?"
            impact = "high"
        elif "open-ended" in lower or "desired outcome" in lower:
            question = "What outcome do you want from this task?"
            impact = "high"
        elif "petition kind" in lower:
            question = "What kind of response should this become?"
            impact = "medium"
        elif "evidence" in lower:
            question = "Which source or evidence should I treat as authoritative?"
            impact = "medium"
        elif "classification" in lower:
            question = "Should I treat this as a simple guidance task or a structured decision task?"
            impact = "low"
        else:
            question = "What missing detail should I assume next?"
            impact = "medium"

        item = {"question": question, "impact": impact}
        if item not in questions:
            questions.append(item)

    if not questions:
        questions.append({
            "question": "What detail should I ask for before answering?",
            "impact": "high",
        })
    return questions


def build_clarification_packet(task: str, hermes_result: dict[str, Any]) -> dict[str, Any]:
    task_text = _normalize_task(task)
    run_id = _text(hermes_result.get("run_id")) or "unknown_run"
    mode = _text(hermes_result.get("mode")) or "unknown_mode"
    summary = _text(hermes_result.get("summary"))
    current_confidence = _clamp_confidence(hermes_result.get("confidence"), fallback=0.0)

    known_facts = _known_facts(task_text, hermes_result)
    missing_facts = _missing_facts(task_text, hermes_result)
    confidence_limiters = [_limiter_for_fact(fact) for fact in missing_facts]
    assumptions = _assumptions(task_text, hermes_result, known_facts)
    provisional_answer = {
        "text": summary or "Sentinel did not provide a summary, so only a weak provisional answer is available.",
        "assumption_dependencies": [assumption["assumption_id"] for assumption in assumptions[:2]],
    }
    clarifying_questions = _clarifying_questions(missing_facts)
    high_impact_count = sum(1 for item in clarifying_questions if item.get("impact") == "high")
    confidence_projection = {
        "if_no_answer": current_confidence,
        "if_answered": min(0.95, current_confidence + (0.1 * high_impact_count)),
    }

    timestamp = utc_stamp()
    created_at = _iso_now()
    packet_id = f"clarification_{timestamp}_{_short_digest('|'.join([run_id, mode, task_text, summary, created_at]))}"
    status = "needs_input" if missing_facts else "provisional"

    packet = {
        "packet_id": packet_id,
        "mission_id": run_id,
        "mode": mode,
        "status": status,
        "known_facts": known_facts,
        "missing_facts": missing_facts,
        "confidence_analysis": {
            "current_confidence": current_confidence,
            "confidence_limiters": confidence_limiters,
        },
        "assumptions": assumptions,
        "provisional_answer": provisional_answer,
        "deductive_options": _deductive_options(task_text, hermes_result, missing_facts, current_confidence),
        "clarifying_questions_ranked": clarifying_questions,
        "confidence_projection": confidence_projection,
        "created_at": created_at,
    }
    return packet


def clarification_packet_path_for(packet: dict[str, Any]) -> Path:
    packet_id = _text(packet.get("packet_id"))
    if not packet_id:
        raise ValueError("clarification packet is missing packet_id")
    CLARIFICATION_PACKETS_DIR.mkdir(parents=True, exist_ok=True)
    return CLARIFICATION_PACKETS_DIR / f"{packet_id}.json"


def write_clarification_packet(packet: dict[str, Any]) -> Path:
    path = clarification_packet_path_for(packet)
    path.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
