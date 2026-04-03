from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"
WORKSPACE_ID = "shared-coordination"
DEFAULT_PEER_ID = "peer-hermes-desktop"

ROOT = Path("/mnt/d/spine_desk/Spinetop")
COLLECTIVE = ROOT / "memory" / "collective"
STATE_DIR = ROOT / "logs" / "honcho_bridge"
STATE_DIR.mkdir(parents=True, exist_ok=True)
SENT_FILE = STATE_DIR / "sent_files.json"
EVENT_LOG = ROOT / "logs" / "topology" / "events.jsonl"


def log_event(event_type: str, record_name: str, status: str, detail: str = "") -> None:
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "machine": "Spinetop",
        "event_type": event_type,
        "record_name": record_name,
        "status": status,
        "detail": detail,
    }
    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_sent() -> dict[str, float]:
    if not SENT_FILE.exists():
        return {}
    try:
        return json.loads(SENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_sent(sent: dict[str, float]) -> None:
    SENT_FILE.write_text(json.dumps(sent, indent=2), encoding="utf-8")


def api_request(method: str, path: str, payload: dict | None = None) -> tuple[int, str]:
    url = BASE_URL + path
    data = None
    headers = {"Content-Type": "application/json"}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())

    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body
    except Exception as e:
        return 0, str(e)


def ensure_workspace() -> None:
    status, body = api_request(
        "POST",
        "/v3/workspaces",
        {
            "id": WORKSPACE_ID,
            "metadata": {"created_by": "honcho_bridge", "machine": "Spinetop"},
            "configuration": {},
        },
    )
    if status not in (200, 201, 409):
        raise RuntimeError(f"workspace create failed: {status} {body[:500]}")


def infer_peer_id(record: dict) -> str:
    agent_id = str(record.get("agent_id", "")).strip()
    if agent_id == "hermes-laptop":
        return "peer-hermes-laptop"
    return DEFAULT_PEER_ID


def ensure_peer(peer_id: str) -> None:
    status, body = api_request(
        "POST",
        f"/v3/workspaces/{WORKSPACE_ID}/peers",
        {
            "id": peer_id
        },
    )
    if status not in (200, 201, 409):
        raise RuntimeError(f"peer create failed: {status} {body[:500]}")


def ensure_session(session_id: str, peer_id: str, record: dict) -> None:
    status, body = api_request(
        "POST",
        f"/v3/workspaces/{WORKSPACE_ID}/sessions",
        {
            "id": session_id,
            "metadata": {
                "created_by": "honcho_bridge",
                "workspace": record.get("workspace", "spinetop"),
                "agent_id": record.get("agent_id", "hermes-desktop"),
            },
            "peers": {
                peer_id: {}
            },
            "configuration": {},
        },
    )
    if status not in (200, 201, 409):
        raise RuntimeError(f"session create failed: {status} {body[:500]}")


def build_message(record: dict, peer_id: str) -> dict:
    content = {
        "source": record.get("source"),
        "expert_name": record.get("expert_name"),
        "task": record.get("task"),
        "summary": record.get("summary"),
        "key_findings": record.get("key_findings"),
        "confidence": record.get("confidence"),
        "recommended_action": record.get("recommended_action"),
        "promotion_candidate": record.get("promotion_candidate"),
    }

    return {
        "content": json.dumps(content, ensure_ascii=False),
        "peer_id": peer_id,
        "metadata": {
            "bridge_source": "filesystem_collective",
            "record_name": record.get("_record_name"),
            "agent_id": record.get("agent_id"),
            "workspace": record.get("workspace"),
            "timestamp_created": record.get("timestamp_created"),
        },
        "configuration": {},
        "created_at": record.get("timestamp_created"),
    }


def send_record(path: Path) -> None:
    record = json.loads(path.read_text(encoding="utf-8"))
    record["_record_name"] = path.name

    peer_id = infer_peer_id(record)
    session_id = str(record.get("session_id", "")).strip()
    if not session_id:
        raise RuntimeError(f"missing session_id in {path}")

    ensure_workspace()
    ensure_peer(peer_id)
    ensure_session(session_id, peer_id, record)

    payload = {"messages": [build_message(record, peer_id)]}
    status, body = api_request(
        "POST",
        f"/v3/workspaces/{WORKSPACE_ID}/sessions/{session_id}/messages",
        payload,
    )
    if status not in (200, 201):
        raise RuntimeError(f"message send failed: {status} {body[:500]}")


def main() -> None:
    sent = load_sent()
    files = sorted(COLLECTIVE.glob("*.json"))

    if not files:
        print("[honcho-bridge] no collective files")
        return

    for path in files:
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            continue

        previous = sent.get(path.name)
        if previous is not None and mtime <= previous:
            continue

        try:
            send_record(path)
            sent[path.name] = mtime
            save_sent(sent)
            print(f"[honcho-bridge] sent {path.name}")
            log_event("honcho_bridge", path.name, "success", "mirrored to honcho")
        except Exception as exc:
            print(f"[honcho-bridge] ERROR {path.name}: {exc}")
            print("[honcho-bridge] detail:", str(exc)[:1000])
            log_event("honcho_bridge", path.name, "error", str(exc)[:500])


if __name__ == "__main__":
    main()
