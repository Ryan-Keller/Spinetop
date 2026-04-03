from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from flask import Flask, jsonify

ROOT = Path("/mnt/d/spine_desk/Spinetop")
EVENT_LOG = ROOT / "logs" / "topology" / "events.jsonl"
HONCHO_BASE = "http://127.0.0.1:8000"
WORKSPACE_ID = "shared-coordination"

app = Flask(__name__)


def read_recent_events(limit: int = 50) -> list[dict]:
    if not EVENT_LOG.exists():
        return []
    lines = EVENT_LOG.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


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


@app.get("/api/status")
def api_status():
    sessions = safe_honcho_post(f"/v3/workspaces/{WORKSPACE_ID}/sessions/list", {})
    peers = safe_honcho_post(f"/v3/workspaces/{WORKSPACE_ID}/peers/list", {})

    return jsonify({
        "ok": True,
        "workspace_id": WORKSPACE_ID,
        "events_recent": read_recent_events(50),
        "honcho_sessions_total": sessions.get("total"),
        "honcho_peers_total": peers.get("total"),
        "honcho_sessions": sessions.get("items", [])[:10],
        "honcho_peers": peers.get("items", [])[:10],
    })


@app.get("/api/events")
def api_events():
    return jsonify({
        "ok": True,
        "items": read_recent_events(200)
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5051, debug=False)
