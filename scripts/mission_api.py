from __future__ import annotations

from typing import Any

from flask import jsonify, request

import mirror_api
import save_api


def _normalized_existing_mission(api: Any, mission_id: str):
    try:
        mission = api.normalize_mission_id(mission_id)
    except Exception as exc:
        return None, (jsonify({"ok": False, "error": str(exc)}), 400)
    if not api._mission_exists(mission):
        return None, (jsonify({"ok": False, "error": "mission not found"}), 404)
    return mission, None


def _request_payload(*, force: bool = True) -> dict[str, Any]:
    try:
        payload = request.get_json(force=force) or {}
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def handle_expeditions_list(api: Any):
    items, grouped_counts = api._list_expeditions()
    return jsonify({
        "ok": True,
        "source_root": api._safe_relative_path(api.EXPEDITIONS_ACTIVE_DIR),
        "items": items,
        "grouped_counts": grouped_counts,
        "queue_summary": grouped_counts.get("queue_summary") if isinstance(grouped_counts, dict) else api._queue_summary_from_items([]),
    })


def handle_expedition_detail(api: Any, mission_id: str):
    try:
        exists = api._mission_exists(mission_id)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "available": False,
            "error": str(exc),
            "item": None,
        }), 400
    if not exists:
        return jsonify({
            "ok": False,
            "available": False,
            "error": "mission not found",
            "item": None,
        }), 404
    try:
        item = api._build_expedition_detail(mission_id)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "available": False,
            "error": str(exc),
            "item": None,
        }), 400
    return jsonify({
        "ok": True,
        "available": True,
        "item": item,
    })


def handle_expedition_state(api: Any, mission_id: str):
    try:
        exists = api._mission_exists(mission_id)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not exists:
        return jsonify({"ok": False, "error": "mission not found"}), 404
    try:
        item = api._expedition_state_api_item(api._build_expedition_detail(mission_id))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "item": item})


def handle_expedition_timeline(api: Any, mission_id: str):
    try:
        exists = api._mission_exists(mission_id)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not exists:
        return jsonify({"ok": False, "error": "mission not found"}), 404
    try:
        item = api._expedition_timeline_api_item(mission_id)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "item": item})


def handle_expedition_sync_runner_returns(api: Any, mission_id: str):
    try:
        exists = api._mission_exists(mission_id)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not exists:
        return jsonify({"ok": False, "error": "mission not found"}), 404
    try:
        sync = api._sync_runner_returns_result(mission_id)
        item = api._build_expedition_detail(mission_id)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "sync": sync, "item": item})


def handle_expedition_invoke_role(api: Any, mission_id: str):
    mission, error = _normalized_existing_mission(api, mission_id)
    if error:
        return error
    payload = _request_payload()
    role_id = str(payload.get("role_id") or "").strip()
    input_payload = payload.get("input_payload")
    if not role_id:
        return jsonify({"ok": False, "error": "role_id is required"}), 400
    if input_payload is None:
        input_payload = {}
    if not isinstance(input_payload, dict):
        return jsonify({"ok": False, "error": "input_payload must be an object"}), 400
    if "trigger_reason" not in input_payload and payload.get("trigger_reason") is not None:
        input_payload = dict(input_payload)
        input_payload["trigger_reason"] = str(payload.get("trigger_reason") or "").strip()

    try:
        result = api.invoke_role(role_id, mission, input_payload)
        api.log_topology_event(
            "operator_intervention",
            f"{result['role']}:{mission}",
            "success" if result.get("ok") else str(result.get("status") or "created"),
            str(((result.get("output") or {}) if isinstance(result.get("output"), dict) else {}).get("result") or "").strip(),
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    record = result.get("record") if isinstance(result.get("record"), dict) else {}
    return jsonify({
        "ok": True,
        "mission_id": mission,
        "role": str(result.get("role") or "").strip(),
        "status": str(result.get("status") or "").strip(),
        "runtime_active": bool(record.get("runtime_active")),
        "artifact_path": str(result.get("artifact_path") or "").strip(),
        "output": result.get("output") if isinstance(result.get("output"), dict) else {},
    })


def handle_expedition_refresh_assumptions(api: Any, mission_id: str):
    mission, error = _normalized_existing_mission(api, mission_id)
    if error:
        return error
    try:
        refresh = api._refresh_assumption_ledger(mission)
        item = api._build_expedition_detail(mission)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "refresh": refresh, "item": item})


def _handle_assumption_update(api: Any, mission_id: str, assumption_id: str, *, operator_status: str):
    mission, error = _normalized_existing_mission(api, mission_id)
    if error:
        return error
    payload = _request_payload()
    operator_note = str(payload.get("operator_note") or payload.get("note") or "").strip()
    try:
        assumption = api._update_assumption_confirmation(
            mission,
            assumption_id,
            operator_status=operator_status,
            operator_note=operator_note,
        )
        item = api._build_expedition_detail(mission)
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "assumption not found"}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "assumption": assumption, "item": item})


def handle_expedition_confirm_assumption(api: Any, mission_id: str, assumption_id: str):
    return _handle_assumption_update(api, mission_id, assumption_id, operator_status="accepted")


def handle_expedition_reject_assumption(api: Any, mission_id: str, assumption_id: str):
    return _handle_assumption_update(api, mission_id, assumption_id, operator_status="rejected")


def handle_expeditions_create(api: Any):
    payload = _request_payload()
    objective = str(payload.get("objective") or payload.get("task_text") or "").strip()
    if not objective:
        return jsonify({"ok": False, "error": "objective is required"}), 400

    mission_id = api._generate_mission_id()
    mission_dir = api._mission_root(mission_id)
    mission_dir.mkdir(parents=True, exist_ok=True)
    api._ensure_workbench_structure(mission_id)
    api.write_state(mission_id, "MISSION_DEFINED")
    api._create_mission_brief(mission_id, objective)
    api._create_mission_agent_identity(mission_id, objective)
    api._refresh_working_memory(mission_id)

    detail = api._build_expedition_detail(mission_id)
    return jsonify({"ok": True, "item": detail})


def handle_expedition_input(api: Any, mission_id: str):
    mission, error = _normalized_existing_mission(api, mission_id)
    if error:
        return error
    data = _request_payload()
    raw_text = api._operator_raw_text(data).strip()

    save_result = save_api.build_operator_save_result(mission_id=mission, raw_text=raw_text)
    if save_result is not None:
        status_code, body = save_result
        return jsonify(body), status_code

    content = raw_text
    if not content:
        return jsonify({"ok": False, "error": "content is required"}), 400

    brief = api.read_mission_brief(mission) or {}
    state = api.read_state(mission)
    objective = str(brief.get("objective") or brief.get("task_text") or "").strip()
    latest_packet = api._latest_clarification_summary(mission)
    before_inputs = api._mission_inputs(mission)
    before_sufficient, _ = api._is_sufficient_to_proceed(
        objective,
        before_inputs,
        str(state.get("current_state") or "MISSION_DEFINED"),
        latest_packet,
    )
    item = api._write_mission_input(mission, content)
    translation = None
    if api.PROMPT_TRANSLATOR_ACTIVE:
        translation = api.translate_and_store_prompt(content, mission_id=mission)
    api._refresh_working_memory(mission, operator_text=content, operator_reply_at=str(item.get("created_at") or ""), source="mission intake")
    after_sufficient, _ = api._is_sufficient_to_proceed(
        objective,
        api._mission_inputs(mission),
        str(state.get("current_state") or "MISSION_DEFINED"),
        latest_packet,
    )
    trigger = None
    if not before_sufficient and after_sufficient:
        trigger = api._create_trigger_record(
            mission,
            trigger_kind="sufficiency_unblocked_on_input",
            reason="mission input flipped the sufficiency gate from blocked to sufficient",
            source=f"mission_input:{item['input_id']}",
        )

    return jsonify({
        "ok": True,
        "item": item,
        "translation": translation,
        "trigger": trigger,
        "mission": api._build_expedition_detail(mission),
    })


def handle_expedition_translate_prompt(api: Any, mission_id: str):
    mission, error = _normalized_existing_mission(api, mission_id)
    if error:
        return error
    payload = _request_payload()
    content = str(payload.get("content") or payload.get("text") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "content is required"}), 400
    if not api.PROMPT_TRANSLATOR_ACTIVE:
        return jsonify({"ok": False, "error": "prompt translator is disabled for now"}), 409
    translation = api.translate_and_store_prompt(content, mission_id=mission)
    return jsonify({"ok": True, "translation": translation, "mission": api._build_expedition_detail(mission)})


def handle_expedition_parking(api: Any, mission_id: str):
    mission, error = _normalized_existing_mission(api, mission_id)
    if error:
        return error
    payload = _request_payload()
    status = str(payload.get("status") or "").strip().lower()
    if status not in {"active", "parked"}:
        return jsonify({"ok": False, "error": "status must be active or parked"}), 400
    reason = str(payload.get("reason") or "").strip()
    resume_hint = str(payload.get("resume_hint") or "").strip()
    existing = api._read_parking_status(mission)
    record = api._write_parking_status(mission, status=status, reason=reason, parked_by="operator", resume_hint=resume_hint)
    if status == "parked":
        api._clear_parked_mission_handoff(mission, reason=reason or "mission parked by operator")
    trigger = None
    if str(existing.get("status") or "active") == "parked" and status == "active":
        trigger = api._create_trigger_record(
            mission,
            trigger_kind="mission_resumed",
            reason=reason or "operator explicitly resumed the parked mission",
            source="operator_resume",
        )
    return jsonify({"ok": True, "parking_status": record, "trigger": trigger, "item": api._build_expedition_detail(mission)})


def handle_expedition_triggers_create(api: Any, mission_id: str):
    mission, error = _normalized_existing_mission(api, mission_id)
    if error:
        return error
    payload = _request_payload()
    trigger_kind = str(payload.get("trigger_kind") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    if trigger_kind not in {"operator_refresh_requested", "do_now_first_pass_requested"}:
        return jsonify({"ok": False, "error": "trigger_kind must be operator_refresh_requested or do_now_first_pass_requested"}), 400
    if not reason:
        return jsonify({"ok": False, "error": "reason is required"}), 400
    trigger = api._create_trigger_record(mission, trigger_kind=trigger_kind, reason=reason, source="operator_action")
    return jsonify({"ok": True, "trigger": trigger, "item": api._build_expedition_detail(mission)})


def handle_expedition_interventions(api: Any, mission_id: str):
    mission, error = _normalized_existing_mission(api, mission_id)
    if error:
        return error
    payload = _request_payload()
    action = str(payload.get("action") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    note = str(payload.get("note") or "").strip()
    if not action:
        return jsonify({"ok": False, "error": "action is required"}), 400
    try:
        result = api._apply_control_tower_intervention(mission, action=action, reason=reason, note=note)
    except ValueError as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
            "allowed_actions": [
                "resume_mission",
                "retry_bounded_action",
                "refresh_assumptions",
                "sync_helper_returns",
                "clear_stale_pending_handoff",
                "mark_archive_candidate",
            ],
        }), 400
    if not result["ok"]:
        return jsonify(result), 409
    return jsonify(result)


def handle_expedition_respond(api: Any, mission_id: str):
    return handle_expedition_chat(api, mission_id)


def handle_expedition_chat_get(api: Any, mission_id: str):
    mission, error = _normalized_existing_mission(api, mission_id)
    if error:
        return error
    return jsonify({
        "ok": True,
        "item": api._build_expedition_detail(mission),
        "messages": api._mission_chat_messages(mission),
        "source_root": api._safe_relative_path(api._mission_chat_path(mission).parent),
    })


def handle_expedition_chat(api: Any, mission_id: str):
    mission, error = _normalized_existing_mission(api, mission_id)
    if error:
        return error
    data = _request_payload()
    raw_text = api._operator_raw_text(data).strip()

    save_result = save_api.build_operator_save_result(mission_id=mission, raw_text=raw_text)
    if save_result is not None:
        status_code, body = save_result
        return jsonify(body), status_code

    content = raw_text
    if not content:
        return jsonify({"ok": False, "error": "content is required"}), 400

    quick_reply = str(data.get("quick_reply") or data.get("preset") or "").strip() or None
    retrieval = mirror_api.concierge_mirror_retrieval_result(api, mission, content, quick_reply)
    if retrieval:
        detail = api._build_expedition_detail(mission)
        assistant = {
            "sender": "assistant",
            "role": "concierge",
            "tone": "info",
            "message": str(retrieval.get("message") or "").strip(),
            "kind": "concierge_mirror_retrieval",
        }
        user_item, assistant_item = api._build_chat_exchange_items(mission, content, assistant)
        current_messages = api._mission_chat_messages(mission)
        retrieval_message = str(retrieval.get("message") or "").strip()
        matches = retrieval.get("matches") if isinstance(retrieval.get("matches"), list) else []
        return jsonify({
            "ok": True,
            "kind": "concierge_mirror_retrieval",
            "mission_id": str(retrieval.get("mission_id") or "").strip(),
            "query": str(retrieval.get("query") or "").strip(),
            "mode": str(retrieval.get("mode") or "").strip(),
            "matches": matches,
            "message": retrieval_message,
            "item": detail,
            "messages": [*current_messages, user_item, assistant_item],
            "exchange": {
                "messages": [user_item, assistant_item],
                "path": "",
                "summary": "",
                "persisted": False,
                "retrieval": retrieval,
            },
            "response": {
                "kind": "concierge_mirror_retrieval",
                "summary": retrieval_message,
                "answer": retrieval_message,
                "message": retrieval_message,
                "tone": "info",
                "questions": [],
                "artifact": "mirror_retrieval",
                "mission_id": str(retrieval.get("mission_id") or "").strip(),
                "query": str(retrieval.get("query") or "").strip(),
                "mode": str(retrieval.get("mode") or "").strip(),
                "matches": matches,
            },
        })

    exchange = api._append_chat_exchange(mission, content, quick_reply=quick_reply)
    assistant_message = ""
    assistant_tone = "info"
    if isinstance(exchange, dict):
        messages = exchange.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict):
                assistant_message = str(last.get("message") or "")
                assistant_tone = str(last.get("tone") or "info")
    detail = api._build_expedition_detail(mission)
    working_memory = detail.get("working_memory") if isinstance(detail, dict) else {}
    return jsonify({
        "ok": True,
        "item": detail,
        "messages": api._mission_chat_messages(mission),
        "exchange": exchange,
        "response": {
            "kind": "chat",
            "summary": assistant_message or "Mission chat updated.",
            "answer": assistant_message,
            "message": assistant_message,
            "tone": assistant_tone,
            "questions": api._question_summary_lines(api._dict_list(working_memory.get("open_questions"))) if isinstance(working_memory, dict) else [],
            "artifact": "mission_chat",
        },
    })
