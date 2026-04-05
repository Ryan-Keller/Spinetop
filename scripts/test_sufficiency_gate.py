from __future__ import annotations

import dashboard_api


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _summary_for(objective: str) -> dict:
    return dashboard_api._mission_summary_payload(
        mission_id="mission_test",
        objective=objective,
        current_state="CLARIFICATION_NEEDED",
        manifest=None,
        latest_run=None,
        latest_draft=None,
        latest_packet=None,
        latest_runner_return=None,
        mission_inputs=[],
        working_memory={
            "open_questions": [{"question": "Need more detail?", "impact": "medium"}],
            "deferred_questions": [{"question": "Need more detail later?", "impact": "medium"}],
            "active_assumptions": [],
            "confirmed_facts": [],
            "operating_status": "",
            "blocked_reason": "",
            "can_continue_without_input": False,
            "latest_summary": "",
        },
        parking_status={"status": "active"},
    )


def main() -> int:
    sufficient, reason = dashboard_api._is_sufficient_to_proceed(
        "how do I teach my dog to sit",
        [],
        "CLARIFICATION_NEEDED",
        None,
    )
    _assert(sufficient and reason == "general_instruction_task", "dog sit should be sufficient")
    summary = _summary_for("how do I teach my dog to sit")
    _assert(summary["operator_posture"] == "proceed_with_assumptions", "dog sit posture should proceed")
    _assert(summary["triage_bucket"] == "do_now", "dog sit triage should be do_now")
    _assert(summary["can_continue_without_input"] is True, "dog sit should continue without input")
    _assert(summary["blocking_questions"] == [], "dog sit should not have blocking questions")
    dog_reply, dog_tone = dashboard_api._clarification_reply_text(
        "",
        None,
        {
            "objective": "how do I teach my dog to sit",
            "current_state": "CLARIFICATION_NEEDED",
            "assumptions": [],
            "blocking_questions": [],
            "mission_summary": summary,
            "working_memory": {
                "open_questions": [{"question": "Need more detail?", "impact": "medium"}],
                "blocked_reason": "",
            },
        },
    )
    _assert(dog_tone == "good", "dog sit clarification reply should be actionable")
    _assert("use a treat to guide the dog into a sit" in dog_reply, "dog sit should return a first-pass answer")

    sufficient, reason = dashboard_api._is_sufficient_to_proceed(
        "write a python csv script",
        [],
        "CLARIFICATION_NEEDED",
        None,
    )
    _assert(sufficient and reason == "general_instruction_task", "python csv script should be sufficient")
    summary = _summary_for("write a python csv script")
    _assert(summary["operator_posture"] == "proceed_with_assumptions", "python csv script posture should proceed")

    sufficient, reason = dashboard_api._is_sufficient_to_proceed(
        "summarize this text",
        [],
        "CLARIFICATION_NEEDED",
        None,
    )
    _assert(not sufficient, "summarize this text should not be sufficient")
    _assert(reason == "Please provide the text you want summarized.", "summarize text should ask for text")
    summary = _summary_for("summarize this text")
    _assert(summary["operator_posture"] == "needs_operator_answer", "summarize text posture should wait")
    _assert(summary["triage_bucket"] == "waiting", "summarize text triage should wait")
    _assert(summary["blocking_questions"] == ["Please provide the text you want summarized."], "summarize text blocker mismatch")
    summarize_reply, summarize_tone = dashboard_api._clarification_reply_text(
        "?",
        None,
        {
            "objective": "summarize this text",
            "current_state": "CLARIFICATION_NEEDED",
            "assumptions": [],
            "blocking_questions": ["Please provide the text you want summarized."],
            "mission_summary": summary,
            "working_memory": {
                "open_questions": [{"question": "Need more detail?", "impact": "medium"}],
                "blocked_reason": "Please provide the text you want summarized.",
            },
        },
    )
    _assert(summarize_tone == "watch", "summarize reply should stay in blocker posture")
    _assert(
        summarize_reply == "I need one concrete blocker answer to continue: Please provide the text you want summarized.",
        "summarize reply should ask one concrete blocker",
    )

    sufficient, reason = dashboard_api._is_sufficient_to_proceed(
        "fix my code",
        [],
        "CLARIFICATION_NEEDED",
        None,
    )
    _assert(not sufficient, "fix my code should not be sufficient")
    _assert(reason == "Please provide the code or error output you want fixed.", "fix code should ask for code")
    summary = _summary_for("fix my code")
    _assert(summary["operator_posture"] == "needs_operator_answer", "fix code posture should wait")
    _assert(summary["blocking_questions"] == ["Please provide the code or error output you want fixed."], "fix code blocker mismatch")

    print("sufficiency_gate_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
