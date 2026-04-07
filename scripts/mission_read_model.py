from __future__ import annotations

from typing import Any

from autonomy_guardrails import build_autonomy_status_view
from governance_utils import read_nanny_state, read_return_all_state
from state_machine import normalize_mission_id, read_artifact_index, read_mission_brief, read_state, read_working_memory

import mission_storage


def _helper(helpers: dict[str, Any], name: str) -> Any:
    return helpers[name]


def _is_parked_mission_item(mission: dict[str, Any]) -> bool:
    parking_status = mission.get("parking_status") if isinstance(mission.get("parking_status"), dict) else {}
    mission_summary = mission.get("mission_summary") if isinstance(mission.get("mission_summary"), dict) else {}
    return (
        str(parking_status.get("status") or "active").strip() == "parked"
        or str(mission.get("operator_posture") or mission_summary.get("operator_posture") or "").strip() == "parked"
        or str(mission.get("triage_bucket") or mission_summary.get("triage_bucket") or "").strip() == "parked"
    )


def _role_label_for_helper(helper_type: str) -> str:
    helper = str(helper_type or "").strip()
    if helper == "retrieval_helper_2b":
        return "helper_2b"
    if helper == "runner_helper_2b":
        return "Expeditioner"
    return helper or "unknown"


def _latest_role_activity(
    *,
    latest_agent_run: dict[str, Any] | None,
    latest_runner_return: dict[str, Any] | None,
    latest_mirror_note: dict[str, Any] | None,
    trigger_handoff: dict[str, Any],
    manifest: dict[str, Any] | None,
    parked: bool,
    helpers: dict[str, Any],
) -> dict[str, Any] | None:
    safe_relative_path = _helper(helpers, "safe_relative_path")
    trigger_handoff_path = _helper(helpers, "trigger_handoff_path")
    mission_manifest_path = _helper(helpers, "mission_manifest_path")

    candidates: list[dict[str, Any]] = []
    if isinstance(latest_agent_run, dict) and (latest_agent_run.get("created_at") or latest_agent_run.get("path")):
        candidates.append({
            "role": str(latest_agent_run.get("role_label") or latest_agent_run.get("role") or "").strip() or "role",
            "kind": "agent_run",
            "summary": str(latest_agent_run.get("summary") or "").strip(),
            "created_at": str(latest_agent_run.get("created_at") or "").strip(),
            "source_ref": str(latest_agent_run.get("path") or "").strip(),
        })
    if isinstance(latest_runner_return, dict) and (latest_runner_return.get("created_at") or latest_runner_return.get("path")):
        candidates.append({
            "role": _role_label_for_helper(str(latest_runner_return.get("helper_type") or latest_runner_return.get("runner_id") or "")),
            "kind": "runner_return",
            "summary": str(latest_runner_return.get("summary") or "").strip(),
            "created_at": str(latest_runner_return.get("created_at") or "").strip(),
            "source_ref": str(latest_runner_return.get("path") or latest_runner_return.get("source_ref") or "").strip(),
        })
    if isinstance(latest_mirror_note, dict) and (latest_mirror_note.get("created_at") or latest_mirror_note.get("path")):
        candidates.append({
            "role": "Mirror",
            "kind": "mirror_note",
            "summary": str(latest_mirror_note.get("summary") or "").strip(),
            "created_at": str(latest_mirror_note.get("created_at") or "").strip(),
            "source_ref": str(latest_mirror_note.get("path") or "").strip(),
        })
    if not parked and str(trigger_handoff.get("status") or "").strip() in {"pending", "active", "blocked"}:
        candidates.append({
            "role": str(trigger_handoff.get("target_role") or "").strip() or "Expeditioner",
            "kind": "trigger_handoff",
            "summary": str(trigger_handoff.get("allowed_action") or trigger_handoff.get("reason") or "").strip(),
            "created_at": str(trigger_handoff.get("updated_at") or "").strip(),
            "source_ref": safe_relative_path(trigger_handoff_path(str(trigger_handoff.get("mission_id") or ""))),
        })
    if isinstance(manifest, dict) and (manifest.get("updated_at") or manifest.get("created_at")):
        candidates.append({
            "role": "Expeditioner",
            "kind": "mission_manifest",
            "summary": str(manifest.get("summary") or manifest.get("recommended_next_step") or "").strip(),
            "created_at": str(manifest.get("updated_at") or manifest.get("created_at") or "").strip(),
            "source_ref": safe_relative_path(mission_manifest_path(str(manifest.get("mission_id") or ""))),
        })
    if not candidates:
        return None
    candidates.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("source_ref") or "")), reverse=True)
    return candidates[0]


def _mission_summary_payload(
    *,
    mission_id: str,
    objective: str,
    current_state: str,
    manifest: dict[str, Any] | None,
    latest_run: dict[str, Any] | None,
    latest_draft: dict[str, Any] | None,
    latest_packet: dict[str, Any] | None,
    latest_runner_return: dict[str, Any] | None,
    mission_inputs: list[dict[str, Any]],
    assumption_entries: list[dict[str, Any]] | None = None,
    working_memory: dict[str, Any] | None = None,
    parking_status: dict[str, Any] | None = None,
    helpers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    helpers = helpers or {}
    dict_list = _helper(helpers, "dict_list")
    assumption_display_items = _helper(helpers, "assumption_display_items")
    fact_summary_lines = _helper(helpers, "fact_summary_lines")
    assumption_summary_lines = _helper(helpers, "assumption_summary_lines")
    question_summary_lines = _helper(helpers, "question_summary_lines")
    blocking_question_lines = _helper(helpers, "blocking_question_lines")
    is_sufficient_to_proceed = _helper(helpers, "is_sufficient_to_proceed")
    operator_options = _helper(helpers, "operator_options")
    assumptions_last_updated = _helper(helpers, "assumptions_last_updated")
    record_object = _helper(helpers, "record_object")

    working_memory = working_memory if isinstance(working_memory, dict) else read_working_memory(mission_id)
    parking_status = parking_status if isinstance(parking_status, dict) else mission_storage._read_parking_status(mission_id)
    confirmed_fact_items = dict_list(working_memory.get("confirmed_facts"))
    active_assumption_items = assumption_display_items(dict_list(assumption_entries))
    open_question_items = dict_list(working_memory.get("open_questions"))
    deferred_question_items = dict_list(working_memory.get("deferred_questions"))
    operating_status = str(working_memory.get("operating_status") or "").strip()
    blocked_reason = str(working_memory.get("blocked_reason") or "").strip()
    can_continue_without_input = bool(working_memory.get("can_continue_without_input", True))
    memory_latest_summary = str(working_memory.get("latest_summary") or "").strip()
    memory_confidence = working_memory.get("latest_confidence")

    believed: list[str] = []
    if memory_latest_summary:
        believed.append(memory_latest_summary)
    if objective:
        believed.append(f"Objective: {objective}")
    if latest_run:
        run_summary = str(latest_run.get("summary") or "").strip()
        if run_summary:
            believed.append(run_summary)
        recommended_action = str(latest_run.get("recommended_action") or "").strip()
        if recommended_action:
            believed.append(f"Sentinel recommended: {recommended_action}")
    if latest_packet:
        provisional = str((latest_packet.get("provisional_answer") or {}).get("text") or "").strip()
        if provisional:
            believed.append(provisional)
    if manifest:
        manifest_summary = str(manifest.get("summary") or "").strip()
        if manifest_summary:
            believed.append(manifest_summary)
    if latest_draft:
        draft_summary = str((latest_draft.get("draft") or {}).get("summary") or latest_draft.get("summary") or "").strip()
        if draft_summary:
            believed.append(draft_summary)
    for item in confirmed_fact_items[:2]:
        text = str(item.get("text") or "").strip()
        if text:
            believed.append(text)
    for item in active_assumption_items[:2]:
        text = str(item.get("statement") or "").strip()
        if text:
            believed.append(f"Assuming: {text}")
    believed = [item for item in believed if item][:5]

    baseline_confidence = 0.18
    if latest_run:
        baseline_confidence += 0.22
    if latest_draft:
        baseline_confidence += 0.12
    if latest_packet:
        baseline_confidence += 0.18
    if manifest:
        baseline_confidence += 0.08
    if mission_inputs:
        baseline_confidence += min(0.08, len(mission_inputs) * 0.02)
    baseline_confidence = max(0.05, min(0.95, baseline_confidence))

    confidence = baseline_confidence
    if current_state in {"CLARIFICATION_NEEDED", "RECONSIDERATION_REQUESTED"}:
        confidence -= 0.05
    if active_assumption_items:
        confidence -= min(0.25, 0.05 * max(0, len(active_assumption_items) - 1))
    if open_question_items:
        confidence -= 0.05 if can_continue_without_input else 0.1
    confidence = max(0.05, min(0.95, confidence))
    if isinstance(memory_confidence, (int, float)):
        confidence = max(confidence, min(0.95, float(memory_confidence)))
    confidence_label = "low" if confidence < 0.4 else "moderate" if confidence < 0.7 else "high"
    confidence_reduction = round(max(0.0, baseline_confidence - confidence), 2)

    if not memory_latest_summary:
        if latest_run:
            memory_latest_summary = str(latest_run.get("summary") or "").strip()
        if not memory_latest_summary and manifest:
            memory_latest_summary = str(manifest.get("summary") or "").strip()
        if not memory_latest_summary and objective:
            memory_latest_summary = f"Mission focused on {objective}."
    if not memory_latest_summary:
        memory_latest_summary = "No structured summary is available yet."

    confirmed_facts = fact_summary_lines(confirmed_fact_items)
    active_assumptions = assumption_summary_lines(active_assumption_items)
    open_questions = question_summary_lines(open_question_items)
    deferred_questions = question_summary_lines(deferred_question_items)
    blocking_questions = blocking_question_lines(open_question_items, latest_packet)
    parked = str(parking_status.get("status") or "active") == "parked"
    parking_reason = str(parking_status.get("reason") or "").strip()
    parking_resume_hint = str(parking_status.get("resume_hint") or "").strip()
    sufficient_to_proceed, sufficiency_reason = is_sufficient_to_proceed(
        objective,
        mission_inputs,
        current_state,
        latest_packet,
    )

    summary_operating_status = operating_status
    if not summary_operating_status:
        if current_state in {"MISSION_CLOSED", "ARCHIVE_REVIEW"}:
            summary_operating_status = "idle"
        elif current_state in {"PACKAGE_READY", "BRIDGE_CONSIDERATION"}:
            summary_operating_status = "ready_for_review"
        elif not can_continue_without_input:
            summary_operating_status = "blocked"
        elif current_state in {"CLARIFICATION_NEEDED", "RECONSIDERATION_REQUESTED"} and open_questions:
            summary_operating_status = "needs_clarification_but_continuing"
        elif confidence < 0.35:
            summary_operating_status = "low_confidence_continue"
        else:
            summary_operating_status = "proceeding_with_assumptions"

    if parked:
        operator_posture = "parked"
        operator_posture_reason = parking_reason or "The mission is parked in the mission console until new operator input arrives."
        triage_bucket = "parked"
    elif current_state in {"MISSION_CLOSED", "ARCHIVE_REVIEW"}:
        operator_posture = "active"
        operator_posture_reason = "The mission is not waiting on operator clarification."
        triage_bucket = "do_now"
        can_continue_without_input = True
    elif current_state in {"PACKAGE_READY", "BRIDGE_CONSIDERATION"}:
        operator_posture = "ready_for_review"
        operator_posture_reason = "A package or review artifact exists, so the next operator step is review."
        triage_bucket = "review"
        can_continue_without_input = True
    elif sufficient_to_proceed:
        if current_state in {"CLARIFICATION_NEEDED", "RECONSIDERATION_REQUESTED"}:
            summary_operating_status = "proceeding_with_assumptions"
            operator_posture = "proceed_with_assumptions"
            operator_posture_reason = "The objective is already sufficient to proceed without additional operator input."
        else:
            operator_posture = "active"
            operator_posture_reason = "The mission is available for work and does not need immediate operator intervention."
        triage_bucket = "do_now"
        can_continue_without_input = True
        blocking_questions = []
        open_questions = []
        deferred_questions = []
        blocked_reason = ""
    else:
        summary_operating_status = "blocked"
        operator_posture = "needs_operator_answer"
        operator_posture_reason = sufficiency_reason
        triage_bucket = "waiting"
        can_continue_without_input = False
        blocked_reason = sufficiency_reason
        blocking_questions = [sufficiency_reason]
        open_questions = [sufficiency_reason]
        deferred_questions = []

    if operator_posture == "parked":
        clarification_reason = operator_posture_reason
    elif operator_posture == "needs_operator_answer":
        clarification_reason = sufficiency_reason
    elif operator_posture == "ready_for_review":
        clarification_reason = "The mission is ready for review."
    else:
        clarification_reason = (
            "The mission is active and can continue through the normal path."
            if sufficiency_reason == "self_contained_objective"
            else "The mission is sufficient to proceed without additional clarification."
        )

    next_question = ""
    if operator_posture == "parked":
        next_question = parking_resume_hint or (blocking_questions[0] if blocking_questions else open_questions[0] if open_questions else "")
    elif blocking_questions:
        next_question = blocking_questions[0]
    elif open_questions:
        next_question = open_questions[0]
    elif operator_posture == "ready_for_review":
        next_question = "Do you want me to open the review preview and keep it pending?"
    elif summary_operating_status == "low_confidence_continue":
        next_question = "What extra detail would most reduce uncertainty?"

    next_best_operator_answer = ""
    if operator_posture == "parked":
        next_best_operator_answer = parking_resume_hint or "Send fresh mission input when you want this expedition to resume."
    elif operator_posture == "needs_operator_answer" and blocking_questions:
        next_best_operator_answer = blocking_questions[0]
    elif next_question:
        next_best_operator_answer = next_question
    elif active_assumptions:
        next_best_operator_answer = "No immediate reply is required; the mission can continue with the current assumptions."
    else:
        next_best_operator_answer = "Add more context if you want to reduce uncertainty."

    options = operator_options(
        operator_posture=operator_posture,
        blocking_questions=blocking_questions,
        has_review_preview=bool(record_object(latest_draft, "review_preview") or latest_draft),
        parking_status=parking_status,
    )

    if operator_posture == "needs_operator_answer":
        what_we_need_from_you = [sufficiency_reason]
    elif operator_posture == "parked":
        what_we_need_from_you = [parking_resume_hint or next_question or "Send fresh mission input when you want this expedition to resume."]
    elif open_questions:
        what_we_need_from_you = open_questions[:2]
        if can_continue_without_input:
            what_we_need_from_you = [f"Optional: {item}" for item in what_we_need_from_you]
    elif operator_posture == "ready_for_review":
        what_we_need_from_you = ["Confirm whether the review preview should be opened."]
    else:
        what_we_need_from_you = ["No immediate input is required."]

    crew_status = "recalled" if operator_posture == "parked" else str(working_memory.get("crew_status") or "active").strip() or "active"
    expedition_activity = "paused" if operator_posture == "parked" else str(working_memory.get("expedition_activity") or "running").strip() or "running"
    parked_at = str(parking_status.get("parked_at") or "").strip()
    wake_hint = parking_resume_hint or str(working_memory.get("wake_hint") or next_question or blocked_reason or "").strip()

    if current_state in {"RELEASE_REQUESTED", "RELEASE_PREPARED", "EXPEDITION_ACTIVE"}:
        recommended_next_step = "Continue the run, then refresh mission detail for the latest state."
    elif operator_posture == "parked":
        recommended_next_step = "Leave the mission quiet until new input arrives, then resume it with a fresh operator message."
    elif operator_posture == "needs_operator_answer":
        recommended_next_step = "Answer the top blocking question before continuing."
    elif operator_posture == "ready_for_review":
        recommended_next_step = "Open the review preview and decide whether to submit the draft."
    elif active_assumptions or summary_operating_status == "needs_clarification_but_continuing":
        recommended_next_step = "Continue under the current assumptions and answer the top question when ready."
    elif summary_operating_status == "low_confidence_continue":
        recommended_next_step = "Continue cautiously and add context if it would reduce uncertainty."
    elif current_state in {"MISSION_CLOSED", "ARCHIVE_REVIEW"}:
        recommended_next_step = "Review the archive summary or reopen the mission if new work is needed."
    else:
        recommended_next_step = "Proceed with the current assumptions and add more context only if it will improve confidence."

    summary_text = f"{operator_posture.replace('_', ' ')} mission for {mission_id}."
    if objective:
        summary_text = f"{summary_text[:-1]} focused on {objective}."

    last_operator_reply_at = str(working_memory.get("last_operator_reply_at") or "")

    return {
        "mission_id": mission_id,
        "life_cycle_state": current_state,
        "status": summary_operating_status,
        "operating_status": summary_operating_status,
        "can_continue_without_input": can_continue_without_input,
        "blocked_reason": blocked_reason,
        "summary": summary_text,
        "latest_summary": memory_latest_summary,
        "what_we_believe": believed or [objective or "No objective recorded yet."],
        "confirmed_facts": confirmed_facts,
        "active_assumptions": active_assumptions,
        "assumptions_active": active_assumptions,
        "assumption_count": len(dict_list(assumption_entries)),
        "active_assumption_count": len(active_assumption_items),
        "assumptions_last_updated": assumptions_last_updated(dict_list(assumption_entries)),
        "assumption_review_needed": any(str(item.get("operator_status") or "unreviewed") == "unreviewed" for item in active_assumption_items),
        "open_questions": open_questions,
        "deferred_questions": deferred_questions,
        "blocking_questions": blocking_questions,
        "confidence": round(confidence, 2),
        "confidence_label": confidence_label,
        "confidence_reduction": round(confidence_reduction, 2),
        "what_we_need_from_you": what_we_need_from_you[:4],
        "clarification_reason": clarification_reason,
        "next_question": next_question,
        "next_best_operator_answer": next_best_operator_answer,
        "quick_replies": options[:5],
        "operator_posture": operator_posture,
        "operator_posture_reason": operator_posture_reason,
        "operator_options": options[:5],
        "triage_bucket": triage_bucket,
        "recommended_next_step": recommended_next_step,
        "last_operator_reply_at": last_operator_reply_at,
        "crew_status": crew_status,
        "expedition_activity": expedition_activity,
        "parked_at": parked_at,
        "wake_hint": wake_hint,
    }


def _build_control_tower_summary(
    *,
    mission_id: str,
    manifest: dict[str, Any] | None,
    summary_preview: dict[str, Any],
    autonomy_status: dict[str, Any],
    latest_trigger: dict[str, Any] | None,
    trigger_handoff: dict[str, Any],
    retry_ledger: dict[str, Any],
    parking_status: dict[str, Any],
    agent_runs: list[dict[str, Any]],
    runner_returns: list[dict[str, Any]],
    mirror_notes: list[dict[str, Any]],
    helpers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    helpers = helpers or {}
    pending_runner_return_sync_count = _helper(helpers, "pending_runner_return_sync_count")
    read_operator_interventions = _helper(helpers, "read_operator_interventions")
    safe_operator_actions = _helper(helpers, "safe_operator_actions")

    latest_agent_run = agent_runs[0] if agent_runs else None
    latest_runner_return = runner_returns[0] if runner_returns else None
    latest_mirror_note = mirror_notes[0] if mirror_notes else None
    decision_log = retry_ledger.get("decision_log") if isinstance(retry_ledger.get("decision_log"), list) else []
    last_retry_decision = decision_log[-1] if decision_log else {}
    parked = str(parking_status.get("status") or "active").strip() == "parked"
    active_handoff = None
    if not parked and str(trigger_handoff.get("status") or "").strip() in {"pending", "active", "blocked"}:
        active_handoff = {
            "target_role": str(trigger_handoff.get("target_role") or "").strip(),
            "allowed_action": str(trigger_handoff.get("allowed_action") or "").strip(),
            "status": str(trigger_handoff.get("status") or "").strip(),
            "reason": str(trigger_handoff.get("reason") or "").strip(),
            "updated_at": str(trigger_handoff.get("updated_at") or "").strip(),
        }

    pending_helper_syncs = pending_runner_return_sync_count(mission_id, runner_returns)
    blocked_questions = [str(item).strip() for item in summary_preview.get("blocking_questions", []) if str(item).strip()]
    operator_attention_reason = (
        str(autonomy_status.get("last_blocked_reason") or "").strip()
        or (blocked_questions[0] if blocked_questions else "")
        or str(summary_preview.get("operator_posture_reason") or "").strip()
        or str((latest_mirror_note or {}).get("summary") or "").strip()
    )
    latest_role_activity = _latest_role_activity(
        latest_agent_run=latest_agent_run,
        latest_runner_return=latest_runner_return,
        latest_mirror_note=latest_mirror_note,
        trigger_handoff=trigger_handoff,
        manifest=manifest,
        parked=parked,
        helpers=helpers,
    )
    recent_interventions = read_operator_interventions(mission_id)[:5]

    return {
        "autonomy_state": str(autonomy_status.get("autonomy_status") or autonomy_status.get("status") or "ready").strip(),
        "last_trigger": (
            {
                "trigger_kind": str(latest_trigger.get("trigger_kind") or "").strip(),
                "status": str(latest_trigger.get("status") or "").strip(),
                "created_at": str(latest_trigger.get("created_at") or "").strip(),
                "reason": str(latest_trigger.get("reason") or "").strip(),
            }
            if isinstance(latest_trigger, dict) and latest_trigger
            else None
        ),
        "last_trigger_outcome": str(autonomy_status.get("last_trigger_outcome") or "").strip(),
        "retry_budget": int(retry_ledger.get("retry_budget_total") or 0),
        "retry_used": int(retry_ledger.get("retry_budget_used") or 0),
        "last_retry_reason": str(
            last_retry_decision.get("retry_reason")
            or last_retry_decision.get("why_retried")
            or retry_ledger.get("last_failure_reason")
            or ""
        ).strip(),
        "last_blocked_reason": str(autonomy_status.get("last_blocked_reason") or "").strip(),
        "active_role_handoff": active_handoff,
        "latest_role_activity": latest_role_activity,
        "operator_attention_reason": operator_attention_reason,
        "recent_operator_interventions": recent_interventions,
        "safe_operator_actions": safe_operator_actions(
            parking_status=parking_status,
            summary_preview=summary_preview,
            last_blocked_reason=str(autonomy_status.get("last_blocked_reason") or "").strip(),
            retry_ledger=retry_ledger,
            latest_runner_return=latest_runner_return,
            latest_mirror_note=latest_mirror_note,
            pending_helper_syncs=pending_helper_syncs,
            active_handoff=active_handoff,
        ),
    }


def _build_expedition_detail(mission_id: str, *, helpers: dict[str, Any] | None = None) -> dict[str, Any]:
    helpers = helpers or {}
    read_mission_agent_profile = _helper(helpers, "read_mission_agent_profile")
    mission_chat_messages = _helper(helpers, "mission_chat_messages")
    latest_run_summary = _helper(helpers, "latest_run_summary")
    latest_draft_summary = _helper(helpers, "latest_draft_summary")
    latest_clarification_summary = _helper(helpers, "latest_clarification_summary")
    read_assumption_ledger_entries = _helper(helpers, "read_assumption_ledger_entries")
    assumptions_last_updated = _helper(helpers, "assumptions_last_updated")
    latest_assumption_changes = _helper(helpers, "latest_assumption_changes")
    mission_status_badge = _helper(helpers, "mission_status_badge")
    queue_hygiene_flags = _helper(helpers, "queue_hygiene_flags")
    normalize_mission_objective = _helper(helpers, "normalize_mission_objective")
    safe_operator_actions = _helper(helpers, "safe_operator_actions")
    pending_runner_return_sync_count = _helper(helpers, "pending_runner_return_sync_count")
    read_prompt_translations = _helper(helpers, "read_prompt_translations")
    root = _helper(helpers, "root")

    mission = normalize_mission_id(mission_id)
    mission_dir = mission_storage._mission_root(mission)
    brief = read_mission_brief(mission) or {}
    state = read_state(mission)
    manifest = mission_storage._mission_manifest_payload(mission)
    mission_agent = read_mission_agent_profile(mission)
    artifact_index = read_artifact_index(mission)
    artifact_items = list(artifact_index.get("items") or [])
    latest_run_id = str(brief.get("latest_run_id") or (manifest or {}).get("run_id") or "").strip()
    current_state = str(state.get("current_state") or "MISSION_DEFINED").strip() or "MISSION_DEFINED"
    objective = str(brief.get("objective") or brief.get("task_text") or "").strip()
    mission_inputs = mission_storage._mission_inputs(mission)
    mission_chat = mission_chat_messages(mission)
    latest_run = latest_run_summary(mission)
    latest_draft = latest_draft_summary(mission)
    latest_packet = latest_clarification_summary(mission)
    agent_runs = mission_storage._read_agent_runs(mission)
    runner_returns = mission_storage._read_runner_returns(mission)
    latest_runner_return = runner_returns[0] if runner_returns else None
    mirror_notes = mission_storage._read_mirror_notes(mission)
    prompt_translations = read_prompt_translations(mission)
    latest_prompt_translation = prompt_translations[0] if prompt_translations else None
    trigger_records = mission_storage._read_trigger_records(mission)
    latest_trigger = trigger_records[0] if trigger_records else None
    pending_triggers = [item for item in trigger_records if str(item.get("status") or "") == "pending"]
    trigger_handoff = mission_storage._read_trigger_handoff(mission)
    retry_ledger = mission_storage._read_retry_ledger(mission)
    assumption_entries = read_assumption_ledger_entries(mission)
    working_memory = read_working_memory(mission)
    parking_status = mission_storage._read_parking_status(mission)
    return_all = read_return_all_state()
    nanny = read_nanny_state()
    workbench_files = mission_storage._workbench_files(mission)
    workbench_folders = []
    for folder_name in ["intake", "scratch", "code", "test_runs", "notes", "outputs"]:
        folder_path = mission_storage._workbench_root(mission) / folder_name
        folder_files = [item for item in workbench_files if item.get("folder") == folder_name]
        newest_modified_at = ""
        if folder_files:
            newest_modified_at = max(str(item.get("modified_at") or "") for item in folder_files)
        workbench_folders.append({
            "name": folder_name,
            "path": folder_path.relative_to(root).as_posix(),
            "available": folder_path.exists(),
            "file_count": len(folder_files),
            "newest_modified_at": newest_modified_at,
        })
    manifest_status = str((manifest or {}).get("status") or "").strip()
    summary_preview = _mission_summary_payload(
        mission_id=mission,
        objective=objective,
        current_state=current_state,
        manifest=manifest if isinstance(manifest, dict) else None,
        latest_run=latest_run if isinstance(latest_run, dict) else None,
        latest_draft=latest_draft if isinstance(latest_draft, dict) else None,
        latest_packet=latest_packet if isinstance(latest_packet, dict) else None,
        latest_runner_return=latest_runner_return if isinstance(latest_runner_return, dict) else None,
        mission_inputs=mission_inputs,
        assumption_entries=assumption_entries,
        working_memory=working_memory,
        parking_status=parking_status,
        helpers=helpers,
    )
    autonomy_status = build_autonomy_status_view(
        mission_id=mission,
        latest_trigger=latest_trigger,
        trigger_handoff=trigger_handoff,
        retry_ledger=retry_ledger,
        parking_status=parking_status,
        mission_summary=summary_preview,
        return_all_enabled=bool(return_all.get("enabled")),
        nanny_cooling=str(nanny.get("temperature") or "cool") in {"warm", "hot"} or bool(nanny.get("cooldown_active")),
    )
    control_tower_summary = _build_control_tower_summary(
        mission_id=mission,
        manifest=manifest if isinstance(manifest, dict) else None,
        summary_preview=summary_preview,
        autonomy_status=autonomy_status,
        latest_trigger=latest_trigger,
        trigger_handoff=trigger_handoff,
        retry_ledger=retry_ledger,
        parking_status=parking_status,
        agent_runs=agent_runs,
        runner_returns=runner_returns,
        mirror_notes=mirror_notes,
        helpers=helpers,
    )
    status_badge = mission_status_badge(
        current_state,
        manifest_status,
        latest_run_id,
        len(mission_inputs),
        str(summary_preview.get("operating_status") or ""),
        str(summary_preview.get("operator_posture") or ""),
        str(summary_preview.get("triage_bucket") or ""),
    )
    last_updated = mission_storage._latest_mtime([
        mission_dir / "state.json",
        mission_dir / "mission_brief.json",
        mission_dir / "artifact_index.json",
        mission_dir / "mission_manifest.json",
        mission_dir / "working_memory.json",
        *[root / str(item.get("path") or "") for item in workbench_files if str(item.get("path") or "").strip()],
    ])
    queue_hygiene = queue_hygiene_flags(
        {
            "mission_id": mission,
            "objective": objective,
            "current_state": current_state,
            "status_badge": status_badge,
            "created_at": str(brief.get("created_at") or (manifest or {}).get("created_at") or ""),
            "last_updated": last_updated,
            "mission_summary": summary_preview,
            "operator_posture": str(summary_preview.get("operator_posture") or ""),
            "triage_bucket": str(summary_preview.get("triage_bucket") or ""),
            "parking_status": parking_status,
            "control_tower_summary": control_tower_summary,
        },
        duplicate_count=1,
        duplicate_rank=1,
        primary_mission_id=mission,
        primary_last_updated=last_updated,
        normalized_objective=normalize_mission_objective(objective),
    )
    control_tower_summary["safe_operator_actions"] = safe_operator_actions(
        parking_status=parking_status,
        summary_preview=summary_preview,
        queue_hygiene=queue_hygiene,
        last_blocked_reason=str(control_tower_summary.get("last_blocked_reason") or ""),
        retry_ledger=retry_ledger,
        latest_runner_return=latest_runner_return,
        latest_mirror_note=mirror_notes[0] if mirror_notes else None,
        pending_helper_syncs=pending_runner_return_sync_count(mission),
        active_handoff=trigger_handoff,
    )

    return {
        "mission_id": mission,
        "objective": objective,
        "current_state": current_state,
        "status_badge": status_badge,
        "latest_run_id": latest_run_id,
        "last_updated": last_updated,
        "created_at": str(brief.get("created_at") or (manifest or {}).get("created_at") or ""),
        "mission_brief": brief,
        "state": state,
        "manifest": manifest,
        "mission_agent": mission_agent,
        "artifact_index": artifact_index,
        "artifact_refs": (manifest or {}).get("artifact_refs") if isinstance(manifest, dict) else [],
        "latest_hermes_run": latest_run,
        "latest_draft": latest_draft,
        "latest_clarification_packet": latest_packet,
        "latest_runner_return": latest_runner_return,
        "latest_agent_run": agent_runs[0] if agent_runs else None,
        "runner_return_count": len(runner_returns),
        "agent_run_count": len(agent_runs),
        "triggers": trigger_records[:20],
        "latest_trigger": latest_trigger,
        "trigger_count": len(trigger_records),
        "pending_trigger_count": len(pending_triggers),
        "trigger_handoff": trigger_handoff,
        "retry_ledger": retry_ledger,
        "autonomy_status": autonomy_status,
        "control_tower_summary": control_tower_summary,
        "assumptions": assumption_entries,
        "active_assumption_count": len([item for item in assumption_entries if str(item.get("status") or "") in {"active", "accepted"}]),
        "assumption_count": len(assumption_entries),
        "assumptions_last_updated": assumptions_last_updated(assumption_entries),
        "assumption_review_needed": any(
            str(item.get("status") or "") == "active"
            and str(((item.get("confirmation") or {}) if isinstance(item.get("confirmation"), dict) else {}).get("operator_status") or "unreviewed") == "unreviewed"
            for item in assumption_entries
        ),
        "latest_assumption_changes": latest_assumption_changes(assumption_entries),
        "working_memory": working_memory,
        "parking_status": parking_status,
        "operator_posture": str(summary_preview.get("operator_posture") or ""),
        "operator_posture_reason": str(summary_preview.get("operator_posture_reason") or ""),
        "assumptions_active": list(summary_preview.get("assumptions_active") or []),
        "blocking_questions": list(summary_preview.get("blocking_questions") or []),
        "operator_options": list(summary_preview.get("operator_options") or []),
        "triage_bucket": str(summary_preview.get("triage_bucket") or ""),
        "queue_hygiene": queue_hygiene,
        "mission_summary": summary_preview,
        "mirror_notes": mirror_notes[:10],
        "agent_runs": agent_runs[:10],
        "latest_prompt_translation": latest_prompt_translation,
        "prompt_translation_count": len(prompt_translations),
        "prompt_translations": prompt_translations[:10],
        "mission_inputs": mission_inputs,
        "mission_chat": mission_chat,
        "workbench": {
            "root": mission_storage._workbench_root(mission).relative_to(root).as_posix(),
            "folders": workbench_folders,
            "files": workbench_files,
        },
        "artifact_count": len(artifact_items),
        "input_count": len(mission_inputs),
        "chat_count": len(mission_chat),
    }


def _list_expeditions(*, helpers: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    helpers = helpers or {}
    normalize_mission_objective = _helper(helpers, "normalize_mission_objective")
    queue_summary_from_items = _helper(helpers, "queue_summary_from_items")
    queue_sort_timestamp = _helper(helpers, "queue_sort_timestamp")
    queue_hygiene_flags = _helper(helpers, "queue_hygiene_flags")

    if not mission_storage.EXPEDITIONS_ACTIVE_DIR.exists():
        return [], {
            "total_missions": 0,
            "total_groups": 0,
            "duplicate_groups": 0,
            "duplicate_candidates": 0,
            "hidden_duplicate_count": 0,
            "queue_summary": queue_summary_from_items([]),
        }

    missions: list[dict[str, Any]] = []
    for mission_dir in sorted((path for path in mission_storage.EXPEDITIONS_ACTIVE_DIR.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime, reverse=True):
        mission_id = mission_dir.name
        try:
            detail = _build_expedition_detail(mission_id, helpers=helpers)
        except Exception:
            continue
        missions.append({
            "mission_id": detail["mission_id"],
            "objective": detail["objective"],
            "objective_normalized": normalize_mission_objective(detail["objective"]),
            "current_state": detail["current_state"],
            "status_badge": detail["status_badge"],
            "latest_run_id": detail["latest_run_id"],
            "last_updated": detail["last_updated"],
            "created_at": detail["created_at"],
            "artifact_count": detail["artifact_count"],
            "input_count": detail["input_count"],
            "summary": str((detail.get("mission_summary") or {}).get("summary") or (detail.get("manifest") or {}).get("summary") or ""),
            "manifest_status": str((detail.get("manifest") or {}).get("status") or ""),
            "operator_posture": str(detail.get("operator_posture") or ""),
            "triage_bucket": str(detail.get("triage_bucket") or ""),
            "operator_posture_reason": str(detail.get("operator_posture_reason") or ""),
            "mission_summary": detail.get("mission_summary") if isinstance(detail.get("mission_summary"), dict) else {},
            "parking_status": detail.get("parking_status") if isinstance(detail.get("parking_status"), dict) else {},
            "control_tower_summary": detail.get("control_tower_summary") if isinstance(detail.get("control_tower_summary"), dict) else {},
            "path": mission_dir.relative_to(mission_storage.ROOT).as_posix(),
        })

    grouped: dict[str, list[dict[str, Any]]] = {}
    parked_missions: list[dict[str, Any]] = []
    for mission in missions:
        if _is_parked_mission_item(mission):
            parked_missions.append(mission)
            continue
        group_key = mission["objective_normalized"] or mission["mission_id"]
        grouped.setdefault(group_key, []).append(mission)

    grouped_counts = {
        "total_missions": len(missions),
        "total_groups": len(grouped),
        "duplicate_groups": 0,
        "duplicate_candidates": 0,
        "hidden_duplicate_count": 0,
    }

    for group_key, items in grouped.items():
        items.sort(key=lambda item: (queue_sort_timestamp(item), str(item.get("created_at") or ""), str(item.get("mission_id") or "")), reverse=True)
        duplicate_count = len(items)
        if duplicate_count > 1:
            grouped_counts["duplicate_groups"] += 1
            grouped_counts["duplicate_candidates"] += duplicate_count
            grouped_counts["hidden_duplicate_count"] += duplicate_count - 1
        primary = items[0]
        for rank, item in enumerate(items, start=1):
            item["duplicate_group_key"] = group_key
            item["duplicate_count"] = duplicate_count
            item["duplicate_rank"] = rank
            item["is_duplicate_candidate"] = duplicate_count > 1
            item["is_group_primary"] = rank == 1
            item["duplicate_of_mission_id"] = None if rank == 1 else items[0]["mission_id"]
            item["queue_hygiene"] = queue_hygiene_flags(
                item,
                duplicate_count=duplicate_count,
                duplicate_rank=rank,
                primary_mission_id=str(primary.get("mission_id") or ""),
                primary_last_updated=queue_sort_timestamp(primary),
                normalized_objective=str(item.get("objective_normalized") or ""),
            )
            item["recommended_queue_action"] = str((item["queue_hygiene"] or {}).get("recommended_action") or "")
            item["queue_action_reason"] = str((item["queue_hygiene"] or {}).get("recommendation_reason") or "")

    for item in parked_missions:
        item["duplicate_group_key"] = item["mission_id"]
        item["duplicate_count"] = 1
        item["duplicate_rank"] = 1
        item["is_duplicate_candidate"] = False
        item["is_group_primary"] = True
        item["duplicate_of_mission_id"] = None
        item["queue_hygiene"] = queue_hygiene_flags(
            item,
            duplicate_count=1,
            duplicate_rank=1,
            primary_mission_id=str(item.get("mission_id") or ""),
            primary_last_updated=queue_sort_timestamp(item),
            normalized_objective=str(item.get("objective_normalized") or ""),
        )
        item["recommended_queue_action"] = str((item["queue_hygiene"] or {}).get("recommended_action") or "")
        item["queue_action_reason"] = str((item["queue_hygiene"] or {}).get("recommendation_reason") or "")

    missions.sort(key=lambda item: (queue_sort_timestamp(item), str(item.get("created_at") or ""), str(item.get("mission_id") or "")), reverse=True)
    missions.sort(key=lambda item: (0 if item.get("is_group_primary") else 1, str(item.get("duplicate_group_key") or ""), str(item.get("duplicate_rank") or 0)))
    grouped_counts["queue_summary"] = queue_summary_from_items(missions)
    return missions, grouped_counts
