from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG = ROOT / "logs" / "topology" / "events.jsonl"
MEMORY_DIR = ROOT / "memory"
HONCHO_BASE = "http://127.0.0.1:8000"
WORKSPACE_ID = "shared-coordination"
IN_MEMORY_EVENTS: list[dict[str, Any]] = []
IN_MEMORY_EVENTS_MAX = 200

KNOWN_PEERS = [
    {"id": "desktop", "metadata": {"created_by": "system"}},
    {"id": "laptop", "metadata": {"created_by": "system"}},
]

app = Flask(__name__)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_event(raw: dict[str, Any]) -> dict[str, Any]:
    allowed_types = {
        "hermes_write",
        "watcher_scan",
        "promote",
        "approve",
        "honcho_bridge",
        "hopper_clean",
        "honcho_bridge_file",
        "honcho_bridge_watcher",
    }
    allowed_statuses = {
        "created",
        "promotable",
        "success",
        "error",
        "skipped",
        "partial",
        "archived",
        "quarantined",
    }
    raw_type = raw.get("event_type") or "watcher_scan"
    raw_status = raw.get("status") or "created"
    return {
        "timestamp": str(raw.get("timestamp") or iso_now()),
        "event_type": raw_type if raw_type in allowed_types else "watcher_scan",
        "record_name": str(raw.get("record_name") or "unknown"),
        "status": raw_status if raw_status in allowed_statuses else "created",
        "detail": str(raw.get("detail") or ""),
        "machine": str(raw.get("machine") or "local"),
    }


def read_recent_events(limit: int = 50) -> list[dict]:
    rows: list[dict] = []
    if EVENT_LOG.exists():
        lines = EVENT_LOG.read_text(encoding="utf-8").splitlines()
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    if IN_MEMORY_EVENTS:
        rows.extend(IN_MEMORY_EVENTS[-limit:])
    if not rows and MEMORY_DIR.exists():
        # Minimal fallback: surface memory directory presence as a scan event
        rows.append({
            "timestamp": iso_now(),
            "event_type": "watcher_scan",
            "record_name": "memory_dir",
            "status": "success",
            "detail": f"memory files: {len(list(MEMORY_DIR.glob('*')))}",
            "machine": "local",
        })
    normalized = [normalize_event(row) for row in rows]
    return normalized[-limit:]


def honcho_post(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        HONCHO_BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def safe_honcho_post(path: str, payload: dict) -> dict:
    try:
        return honcho_post(path, payload)
    except Exception as e:
        return {"error": str(e)}


def normalize_session(raw: dict[str, Any]) -> dict[str, Any]:
    meta = raw.get("metadata") or {}
    return {
        "id": str(raw.get("id") or "unknown"),
        "is_active": bool(raw.get("is_active", False)),
        "metadata": {
            "agent_id": str(meta.get("agent_id") or "unknown"),
            "workspace": str(meta.get("workspace") or WORKSPACE_ID),
        },
        "created_at": str(raw.get("created_at") or iso_now()),
    }


def normalize_peer(raw: dict[str, Any]) -> dict[str, Any]:
    meta = raw.get("metadata") or {}
    return {
        "id": str(raw.get("id") or "unknown"),
        "metadata": {
            "created_by": str(meta.get("created_by") or "system"),
        },
    }


def get_sessions(limit: int = 10) -> tuple[int, list[dict]]:
    sessions = safe_honcho_post(f"/v3/workspaces/{WORKSPACE_ID}/sessions/list", {})
    items = sessions.get("items") if isinstance(sessions, dict) else None
    if isinstance(items, list) and items:
        normalized = [normalize_session(row) for row in items[:limit]]
        total = sessions.get("total", len(items))
        return int(total or 0), normalized
    return 0, []


def get_peers(limit: int = 10) -> tuple[int, list[dict]]:
    peers = safe_honcho_post(f"/v3/workspaces/{WORKSPACE_ID}/peers/list", {})
    items = peers.get("items") if isinstance(peers, dict) else None
    if isinstance(items, list) and items:
        normalized = [normalize_peer(row) for row in items[:limit]]
        total = peers.get("total", len(items))
        return int(total or 0), normalized
    normalized = [normalize_peer(row) for row in KNOWN_PEERS[:limit]]
    return len(normalized), normalized


def get_events(limit: int = 50) -> list[dict]:
    return read_recent_events(limit)


@app.get("/api/status")
def api_status():
    sessions_total, sessions_items = get_sessions(10)
    peers_total, peers_items = get_peers(10)

    return jsonify({
        "ok": True,
        "workspace_id": WORKSPACE_ID,
        "honcho_sessions_total": sessions_total,
        "honcho_peers_total": peers_total,
        "honcho_sessions": sessions_items,
        "honcho_peers": peers_items,
        "events_recent": get_events(50),
    })


@app.get("/api/events")
def api_events():
    return jsonify({
        "ok": True,
        "items": get_events(200)
    })


@app.post("/api/event")
def api_event_create():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    event = normalize_event(payload)
    IN_MEMORY_EVENTS.append(event)
    if len(IN_MEMORY_EVENTS) > IN_MEMORY_EVENTS_MAX:
        del IN_MEMORY_EVENTS[:-IN_MEMORY_EVENTS_MAX]
    return jsonify({
        "ok": True,
        "item": event,
        "total": len(IN_MEMORY_EVENTS),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5051, debug=False)
