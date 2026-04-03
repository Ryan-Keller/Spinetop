from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from governance_utils import can_bridge_to_honcho, read_nanny_state, read_return_all_state
from repo_paths import repo_root


BASE_URL = "http://127.0.0.1:8000"
WORKSPACE_ID = "shared-coordination"
DEFAULT_PEER_ID = "peer-hermes-desktop"

ROOT = repo_root()
COLLECTIVE = ROOT / "memory" / "collective"
QUARANTINE_DIR = COLLECTIVE / "_quarantine"
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
    created_at = record.get("admitted_at") or record.get("created_at") or record.get("timestamp_created")
    content = {
        "record_type": record.get("record_type"),
        "record_id": record.get("record_id"),
        "source": record.get("source"),
        "expert_name": record.get("expert_name"),
        "task": record.get("task"),
        "summary": record.get("summary"),
        "key_findings": record.get("key_findings"),
        "confidence": record.get("confidence"),
        "recommended_action": record.get("recommended_action"),
        "promotion_candidate": record.get("promotion_candidate"),
        "governance_approval_ref": record.get("governance_approval_ref"),
    }

    return {
        "content": json.dumps(content, ensure_ascii=False),
        "peer_id": peer_id,
        "metadata": {
            "bridge_source": "filesystem_collective",
            "record_name": record.get("_record_name"),
            "record_id": record.get("record_id"),
            "agent_id": record.get("agent_id"),
            "workspace": record.get("workspace"),
            "timestamp_created": created_at,
            "governance_approval_ref": record.get("governance_approval_ref"),
        },
        "configuration": {},
        "created_at": created_at,
    }


def send_record(path: Path) -> None:
    record = json.loads(path.read_text(encoding="utf-8"))
    record["_record_name"] = path.name

    gate = can_bridge_to_honcho(
        record,
        return_all=read_return_all_state(),
        nanny=read_nanny_state(),
    )
    if not gate.allowed:
        raise RuntimeError(f"governance deferred: {gate.reason}")

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


def process_files(files: list[Path]) -> tuple[int, int]:
    sent = load_sent()
    success_count = 0
    error_count = 0

    if not files:
        print("[honcho-bridge] no collective files")
        return success_count, error_count

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
            success_count += 1
        except RuntimeError as exc:
            detail = str(exc)[:500]
            print(f"[honcho-bridge] deferred {path.name}: {detail}")
            log_event("honcho_bridge", path.name, "skipped", detail)
        except Exception as exc:
            print(f"[honcho-bridge] ERROR {path.name}: {exc}")
            print("[honcho-bridge] detail:", str(exc)[:1000])
            detail = str(exc)[:500]
            if "missing session_id" in detail:
                try:
                    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
                    target = QUARANTINE_DIR / path.name
                    if target.exists():
                        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        target = QUARANTINE_DIR / f"{path.stem}_{stamp}{path.suffix}"
                    path.rename(target)
                    reason_path = target.with_suffix(target.suffix + ".reason.txt")
                    reason_path.write_text(
                        "missing session_id\n",
                        encoding="utf-8",
                    )
                    detail = f"missing session_id; quarantined to {target.name}"
                except Exception as move_exc:
                    detail = f"missing session_id; quarantine failed: {move_exc}"
            log_event("honcho_bridge", path.name, "error", detail)
            error_count += 1

    return success_count, error_count


def main() -> int:
    args = [arg for arg in sys.argv[1:] if arg.strip()]
    if args:
        files = [Path(arg) for arg in args]
    else:
        files = sorted(COLLECTIVE.glob("*.json"))

    success_count, error_count = process_files(files)
    if error_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
