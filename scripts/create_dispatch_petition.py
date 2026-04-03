from __future__ import annotations

import argparse
import hashlib
import json
import socket
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISPATCH_DIR = ROOT / "memory" / "dispatch"
GOVERNANCE_DIR = ROOT / "logs" / "governance"


def read_return_all_state() -> dict:
    path = GOVERNANCE_DIR / "return_all.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "enabled": bool(data.get("enabled", False)),
                "allow_custodial_bypass": bool(data.get("allow_custodial_bypass", False)),
            }
        except Exception:
            pass
    return {"enabled": False, "allow_custodial_bypass": False}


def build_petition_id(agent_id: str, workspace: str, task: str, summary: str, stamp: str) -> str:
    seed = f"{agent_id}|{workspace}|{task}|{summary}|{stamp}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6]
    return f"{agent_id}_{stamp}_{digest}"


def should_bypass_return_all(spawn_authority: str, dispatch_mode: str, entry_class: str, return_all: dict) -> bool:
    return (
        return_all.get("enabled")
        and return_all.get("allow_custodial_bypass")
        and spawn_authority == "custodial"
        and dispatch_mode == "rapid"
        and entry_class in {"self_heal", "repair"}
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("status", choices=["pending", "approved", "deferred", "rejected"])
    parser.add_argument("agent_id")
    parser.add_argument("workspace")
    parser.add_argument("task")
    parser.add_argument("summary")
    parser.add_argument("--ask-count", type=int, default=1)
    parser.add_argument("--spawn-authority", default="emissary", choices=["operator", "custodial", "emissary"])
    parser.add_argument("--dispatch-mode", default="normal", choices=["normal", "rapid"])
    parser.add_argument("--operator-id", default="")
    parser.add_argument(
        "--entry-class",
        default="normal",
        choices=["normal", "self_heal", "repair", "artifact_return", "anomaly_review"],
    )
    args = parser.parse_args()

    status = args.status.strip().lower()
    agent_id = args.agent_id.strip()
    workspace = args.workspace.strip()
    task = args.task.strip()
    summary = args.summary.strip()

    target_dir = DISPATCH_DIR / status
    target_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    petition_id = build_petition_id(agent_id, workspace, task, summary, stamp)
    record_name = f"dispatch_{petition_id}_{status}.json"
    now_iso = datetime.now(timezone.utc).isoformat()
    ask_count = max(1, int(args.ask_count))
    requires_operator_approval = ask_count > 1
    source_host = socket.gethostname()
    return_all = read_return_all_state()

    if return_all.get("enabled") and not should_bypass_return_all(
        args.spawn_authority, args.dispatch_mode, args.entry_class, return_all
    ):
        status = "deferred"
        target_dir = DISPATCH_DIR / status
        target_dir.mkdir(parents=True, exist_ok=True)
        record_name = f"dispatch_{petition_id}_{status}.json"
        requires_operator_approval = True

    payload = {
        "petition_id": petition_id,
        "record_name": record_name,
        "agent_id": agent_id,
        "workspace": workspace,
        "source": "dispatch_petition",
        "timestamp_created": now_iso,
        "summary": summary,
        "task": task,
        "confidence": 0.5,
        "promotion_candidate": False,
        "payload_type": "pattern",
        "urgency": "normal",
        "requires_emissary": True,
        "ask_count": ask_count,
        "requires_operator_approval": requires_operator_approval,
        "spawn_authority": args.spawn_authority,
        "dispatch_mode": args.dispatch_mode,
        "operator_id": args.operator_id,
        "status_updated_at": now_iso,
        "source_host": source_host,
        "entry_class": args.entry_class,
    }

    path = target_dir / record_name
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
