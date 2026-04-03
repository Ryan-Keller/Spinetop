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
DISPATCH_DIR = MEMORY_DIR / "dispatch"
GOVERNANCE_DIR = ROOT / "logs" / "governance"
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
        "dispatch_petition",
        "item_world_nanny",
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
        "pending",
        "approved",
        "deferred",
        "rejected",
        "cool",
        "warm",
        "hot",
        "paused",
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


def log_topology_event(event_type: str, record_name: str, status: str, detail: str) -> None:
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": iso_now(),
        "machine": "Spinetop",
        "event_type": event_type,
        "record_name": record_name,
        "status": status,
        "detail": detail,
    }
    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_return_all_state() -> dict[str, Any]:
    path = GOVERNANCE_DIR / "return_all.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "ok": True,
                "enabled": bool(data.get("enabled", False)),
                "issued_by": str(data.get("issued_by") or "operator"),
                "issued_at": str(data.get("issued_at") or ""),
                "reason": str(data.get("reason") or ""),
                "allow_custodial_bypass": bool(data.get("allow_custodial_bypass", False)),
            }
        except Exception:
            pass
    return {
        "ok": True,
        "enabled": False,
        "issued_by": "operator",
        "issued_at": "",
        "reason": "",
        "allow_custodial_bypass": False,
    }


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def is_bypass_allowed(petition: dict[str, Any], return_all: dict[str, Any]) -> bool:
    if not return_all.get("allow_custodial_bypass"):
        return False
    spawn_authority = str(petition.get("spawn_authority") or "")
    dispatch_mode = str(petition.get("dispatch_mode") or "")
    entry_class = str(petition.get("entry_class") or "")
    return (
        spawn_authority == "custodial"
        and dispatch_mode == "rapid"
        and entry_class in {"self_heal", "repair"}
    )


def normalize_petition(raw: dict[str, Any], status: str, filename: str, return_all: dict[str, Any]) -> dict[str, Any]:
    petition_id = str(raw.get("petition_id") or "").strip()
    if not petition_id:
        petition_id = f"legacy:{filename}"
        log_topology_event("dispatch_petition", filename, "error", "missing petition_id")

    ask_count = raw.get("ask_count")
    if ask_count is None:
        asks = raw.get("asks")
        if isinstance(asks, list):
            ask_count = len(asks)
        else:
            ask_count = 1
    ask_count = int(ask_count)

    requires_operator_approval = raw.get("requires_operator_approval")
    if requires_operator_approval is None:
        requires_operator_approval = ask_count > 1

    spawn_authority = str(raw.get("spawn_authority") or "emissary")
    dispatch_mode = str(raw.get("dispatch_mode") or "normal")
    operator_id = str(raw.get("operator_id") or "")
    status_updated_at = str(raw.get("status_updated_at") or raw.get("timestamp_created") or iso_now())
    source_host = str(raw.get("source_host") or "unknown")
    entry_class = str(raw.get("entry_class") or "normal")

    petition_status = status
    if return_all.get("enabled") and status == "pending" and not is_bypass_allowed(raw, return_all):
        issued_at = parse_iso(str(return_all.get("issued_at") or ""))
        updated_at = parse_iso(status_updated_at) or datetime.now(timezone.utc)
        if not issued_at or updated_at >= issued_at:
            petition_status = "deferred"
            requires_operator_approval = True

    return {
        "petition_id": petition_id,
        "record_name": str(raw.get("record_name") or filename),
        "agent_id": str(raw.get("agent_id") or "unknown"),
        "workspace": str(raw.get("workspace") or "unknown"),
        "source": str(raw.get("source") or "dispatch"),
        "timestamp_created": str(raw.get("timestamp_created") or iso_now()),
        "summary": str(raw.get("summary") or ""),
        "task": str(raw.get("task") or ""),
        "confidence": float(raw.get("confidence") or 0.0),
        "promotion_candidate": bool(raw.get("promotion_candidate", False)),
        "payload_type": str(raw.get("payload_type") or "pattern"),
        "urgency": str(raw.get("urgency") or "normal"),
        "requires_emissary": bool(raw.get("requires_emissary", True)),
        "petition_status": petition_status,
        "ask_count": ask_count,
        "requires_operator_approval": bool(requires_operator_approval),
        "spawn_authority": spawn_authority,
        "dispatch_mode": dispatch_mode,
        "operator_id": operator_id,
        "status_updated_at": status_updated_at,
        "source_host": source_host,
        "entry_class": entry_class,
    }


def read_dispatch_petitions() -> list[dict]:
    folders = [
        ("pending", DISPATCH_DIR / "pending"),
        ("approved", DISPATCH_DIR / "approved"),
        ("deferred", DISPATCH_DIR / "deferred"),
        ("rejected", DISPATCH_DIR / "rejected"),
    ]
    petitions: list[dict] = []
    seen_ids: dict[str, int] = {}
    logged_duplicates: set[str] = set()
    return_all = read_return_all_state()
    for status, folder in folders:
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                log_topology_event(
                    "dispatch_petition",
                    path.name,
                    "error",
                    "malformed json",
                )
                continue
            petition = normalize_petition(raw, status, path.name, return_all)
            pid = petition["petition_id"]
            if pid in seen_ids:
                seen_ids[pid] += 1
                if pid not in logged_duplicates:
                    log_topology_event(
                        "dispatch_petition",
                        path.name,
                        "error",
                        "duplicate petition_id across dispatch folders",
                    )
                    logged_duplicates.add(pid)
            else:
                seen_ids[pid] = 1
            petitions.append(petition)
    return petitions


def read_item_world_status() -> dict[str, Any]:
    status_path = ROOT / "logs" / "nanny" / "item_world_status.json"
    if status_path.exists():
        try:
            return json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "ok": True,
        "temperature": "cool",
        "burst_score": 0,
        "error_score": 0,
        "active_agent_warnings": [],
        "recommended_actions": [],
        "global_cooldown_seconds": 0,
    }


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


@app.get("/api/dispatch")
def api_dispatch():
    return jsonify({
        "ok": True,
        "petitions": read_dispatch_petitions(),
    })


@app.get("/api/governance/return-all")
def api_governance_return_all():
    return jsonify(read_return_all_state())


@app.get("/api/item-world-status")
def api_item_world_status():
    return jsonify(read_item_world_status())


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
