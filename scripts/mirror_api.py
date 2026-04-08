from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from flask import jsonify, request


def _chat_semantic_text(message: str) -> str:
    text = str(message or "").strip()
    if not text:
        return ""
    text = re.sub(r"^\[(observer|concierge|mirror|system|expedition)\]\s*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^(observer|concierge|mirror|system|expedition)\s*[:,\-]\s*", "", text, flags=re.IGNORECASE).strip()
    return text


def _clean_mirror_query_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^[\"'`\s]+|[\"'`\s\.\!\?]+$", "", text).strip()
    text = re.sub(r"\b(?:in this mission|from this mission|mirror notes?|saved notes?)\b$", "", text, flags=re.IGNORECASE).strip(" ,.;:!?")
    return " ".join(text.split())


def build_mirror_retrieval_plan(api: Any, message: str, quick_reply: str | None = None) -> dict[str, Any]:
    text = _chat_semantic_text(message)
    normalized = api._normalize_question_text(text)
    if not text or str(quick_reply or "").strip():
        return {"is_mirror_retrieval": False, "query_text": "", "mode": "all"}
    if api._operator_save_text(text) is not None or api._operator_invoke_role_text(text, quick_reply) is not None:
        return {"is_mirror_retrieval": False, "query_text": "", "mode": "all"}

    retrieval_markers = (
        "what have i saved",
        "what did i save",
        "show what i saved",
        "show me what i saved",
        "show my saved notes",
        "what have i written",
        "what did i write",
        "what have i wrote",
        "saved notes",
        "mirror notes",
    )
    if not any(marker in normalized for marker in retrieval_markers):
        return {"is_mirror_retrieval": False, "query_text": "", "mode": "all"}

    recent_markers = ("saved recently", "save recently", "written recently", "wrote recently", "recent saved", "latest saved")
    if any(marker in normalized for marker in recent_markers):
        return {"is_mirror_retrieval": True, "query_text": "", "mode": "recent"}

    query_match = re.search(r"\b(?:about|regarding|on)\s+(.+)$", text, flags=re.IGNORECASE)
    if query_match:
        query_text = _clean_mirror_query_text(query_match.group(1))
        if query_text:
            return {"is_mirror_retrieval": True, "query_text": query_text, "mode": "semantic_match"}

    if normalized in {
        "what have i saved",
        "what did i save",
        "show what i saved",
        "show me what i saved",
        "show my saved notes",
        "what have i written",
        "what did i write",
    }:
        return {"is_mirror_retrieval": True, "query_text": "", "mode": "all"}

    return {"is_mirror_retrieval": False, "query_text": "", "mode": "all"}


def _mirror_token_forms(token: str) -> set[str]:
    base = re.sub(r"[^a-z0-9]+", "", str(token or "").lower())
    if not base:
        return set()
    forms = {base}
    if len(base) > 4 and base.endswith("ies"):
        forms.add(base[:-3] + "y")
    if len(base) > 3 and base.endswith("es"):
        forms.add(base[:-2])
    if len(base) > 3 and base.endswith("s"):
        forms.add(base[:-1])
    if len(base) > 5 and base.endswith("ing"):
        stem = base[:-3]
        forms.add(stem)
        if len(stem) > 2 and stem[-1] == stem[-2]:
            forms.add(stem[:-1])
    if len(base) > 4 and base.endswith("ed"):
        forms.add(base[:-2])
    return {item for item in forms if item}


def _mirror_query_tokens(api: Any, query_text: str) -> list[str]:
    stopwords = {
        "the",
        "and",
        "about",
        "regarding",
        "what",
        "have",
        "did",
        "show",
        "saved",
        "save",
        "notes",
        "note",
        "written",
        "write",
        "wrote",
        "mirror",
        "recent",
        "latest",
        "this",
        "mission",
        "that",
        "with",
        "from",
        "into",
        "your",
        "my",
    }
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in api._normalize_question_text(query_text).split():
        for token in _mirror_token_forms(raw):
            if len(token) < 2 or token in stopwords or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    return tokens


def _mirror_note_match_score(api: Any, note_text: str, query_text: str) -> int:
    normalized_note = api._normalize_question_text(note_text)
    normalized_query = api._normalize_question_text(query_text)
    if not normalized_note or not normalized_query:
        return 0
    if normalized_query in normalized_note:
        return 100 + len(normalized_query)
    note_tokens: set[str] = set()
    for raw in normalized_note.split():
        note_tokens.update(_mirror_token_forms(raw))
    query_tokens = _mirror_query_tokens(api, query_text)
    if not query_tokens:
        return 0
    return sum(1 for token in query_tokens if token in note_tokens or token in normalized_note)


def _compact_mirror_note_text(text: str, limit: int = 180) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _display_mirror_timestamp(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
        return stamp.strftime("%b %d %H:%M UTC")
    except Exception:
        return text


def concierge_mirror_retrieval_result(api: Any, mission_id: str, message: str, quick_reply: str | None = None) -> dict[str, Any] | None:
    plan = build_mirror_retrieval_plan(api, message, quick_reply)
    if not bool(plan.get("is_mirror_retrieval")):
        return None

    mission = api.normalize_mission_id(mission_id)
    api._sync_mission_storage()
    notes = [item for item in api._read_mirror_notes(mission) if isinstance(item, dict)]
    mode = str(plan.get("mode") or "all").strip() or "all"
    query_text = str(plan.get("query_text") or "").strip()

    if mode == "recent":
        matches = notes[:5]
    elif mode == "semantic_match":
        scored: list[tuple[int, dict[str, Any]]] = []
        for note in notes:
            score = _mirror_note_match_score(api, str(note.get("text") or note.get("summary") or ""), query_text)
            if score > 0:
                scored.append((score, note))
        scored.sort(key=lambda item: (item[0], str(item[1].get("created_at") or ""), str(item[1].get("artifact_id") or "")), reverse=True)
        matches = [item for _, item in scored[:5]]
    else:
        matches = notes[:10]

    normalized_matches = [
        {
            "artifact_id": str(item.get("artifact_id") or item.get("note_id") or "").strip(),
            "text": str(item.get("text") or item.get("summary") or "").strip(),
            "created_at": str(item.get("created_at") or "").strip(),
            "artifact_kind": str(item.get("artifact_kind") or item.get("kind") or "").strip(),
        }
        for item in matches
    ]

    if mode == "recent":
        if normalized_matches:
            prefix = f"I found {len(normalized_matches)} recent saved mirror note{'s' if len(normalized_matches) != 1 else ''} in this mission."
        else:
            prefix = "I do not see any saved mirror notes in this mission."
        query_label = "recent"
    elif mode == "semantic_match":
        if normalized_matches:
            prefix = f"I found {len(normalized_matches)} saved mirror note{'s' if len(normalized_matches) != 1 else ''} about {query_text} in this mission."
        else:
            prefix = f"I do not see any saved mirror notes about {query_text} in this mission."
        query_label = query_text
    else:
        if normalized_matches:
            prefix = f"I found {len(normalized_matches)} saved mirror note{'s' if len(normalized_matches) != 1 else ''} in this mission."
        else:
            prefix = "I do not see any saved mirror notes in this mission."
        query_label = "all"

    detail_lines = [
        f'- {_display_mirror_timestamp(str(item.get("created_at") or ""))}: "{_compact_mirror_note_text(str(item.get("text") or ""))}"'
        for item in normalized_matches[:3]
    ]
    message_text = prefix if not detail_lines else prefix + "\n" + "\n".join(detail_lines)

    return {
        "ok": True,
        "kind": "concierge_mirror_retrieval",
        "mission_id": mission,
        "query": query_label,
        "mode": mode,
        "matches": normalized_matches,
        "message": message_text,
    }


def _normalized_existing_mission(api: Any, mission_id: str):
    try:
        mission = api.normalize_mission_id(mission_id)
    except Exception as exc:
        return None, (jsonify({"ok": False, "error": str(exc)}), 400)
    if not api._mission_exists(mission):
        return None, (jsonify({"ok": False, "error": "mission not found"}), 404)
    return mission, None


def handle_expedition_interpretation(api: Any, mission_id: str):
    try:
        exists = api._mission_exists(mission_id)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not exists:
        return jsonify({"ok": False, "error": "mission not found"}), 404
    mode_error = api._interpretation_mode_error(request.args.get("mode", ""))
    if mode_error:
        return jsonify({"ok": False, "error": mode_error}), 400
    try:
        item = api._expedition_interpretation_api_item(mission_id)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if item is None:
        return jsonify({
            "ok": True,
            "available": False,
            "reason": "no existing Mirror-derived interpretation artifact is available for this mission",
            "item": None,
        })
    return jsonify({"ok": True, "available": True, "item": item})


def handle_expedition_mirror_notes(api: Any, mission_id: str):
    mission, error = _normalized_existing_mission(api, mission_id)
    if error:
        return error
    try:
        api._sync_mission_storage()
        items = [
            {
                "artifact_id": str(item.get("artifact_id") or item.get("note_id") or "").strip(),
                "text": str(item.get("text") or item.get("summary") or "").strip(),
                "created_at": str(item.get("created_at") or "").strip(),
                "artifact_kind": str(item.get("artifact_kind") or item.get("kind") or "").strip(),
            }
            for item in api._read_mirror_notes(mission)
            if isinstance(item, dict)
        ]
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "items": items})


def handle_expedition_signals(api: Any, mission_id: str):
    try:
        exists = api._mission_exists(mission_id)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not exists:
        return jsonify({"ok": False, "error": "mission not found"}), 404
    try:
        item = api._expedition_signals_api_item(mission_id)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "item": item})


def handle_expedition_replay_window(api: Any, mission_id: str):
    try:
        exists = api._mission_exists(mission_id)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not exists:
        return jsonify({"ok": False, "error": "mission not found"}), 404
    payload = request.get_json(silent=True) or {}
    try:
        item = api._build_replay_window(mission_id, payload.get("mode"), payload.get("value"))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "item": item})


def handle_expedition_replay_cursor(api: Any, mission_id: str):
    try:
        exists = api._mission_exists(mission_id)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not exists:
        return jsonify({"ok": False, "error": "mission not found"}), 404
    payload = request.get_json(silent=True) or {}
    replay_window_id = str(payload.get("replay_window_id") or "").strip()
    if not replay_window_id:
        return jsonify({"ok": False, "error": "replay_window_id is required"}), 400
    try:
        item = api._build_replay_cursor_state(
            mission_id,
            replay_window_id,
            payload.get("action"),
            cursor_position=payload.get("cursor_position"),
            cursor_time=str(payload.get("cursor_time") or "").strip(),
            direction=str(payload.get("direction") or "").strip(),
            speed=payload.get("speed"),
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "item": item})


def handle_expedition_replay_frame(api: Any, mission_id: str):
    try:
        exists = api._mission_exists(mission_id)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not exists:
        return jsonify({"ok": False, "error": "mission not found"}), 404
    replay_window_id = str(request.args.get("replay_window_id", "")).strip()
    if not replay_window_id:
        return jsonify({"ok": False, "error": "replay_window_id is required"}), 400
    cursor_index = request.args.get("cursor_index")
    cursor_time = str(request.args.get("cursor_time", "")).strip()
    try:
        item = api._build_replay_frame(
            mission_id,
            replay_window_id,
            cursor_index=cursor_index,
            cursor_time=cursor_time,
            direction=str(request.args.get("direction", "")).strip(),
            lens=str(request.args.get("lens", "")).strip(),
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "item": item})
