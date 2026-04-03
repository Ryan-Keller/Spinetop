from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISPATCH_DIR = ROOT / "memory" / "dispatch"


def usage() -> None:
    print(
        "Usage: python3 create_dispatch_petition.py <pending|approved|deferred|rejected> "
        "<agent_id> <workspace> <task> <summary>"
    )


def main() -> int:
    if len(sys.argv) < 6:
        usage()
        return 1

    status = sys.argv[1].strip().lower()
    agent_id = sys.argv[2].strip()
    workspace = sys.argv[3].strip()
    task = sys.argv[4].strip()
    summary = " ".join(sys.argv[5:]).strip()

    if status not in {"pending", "approved", "deferred", "rejected"}:
        print(f"Invalid status: {status}")
        usage()
        return 1

    target_dir = DISPATCH_DIR / status
    target_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    record_name = f"dispatch_{agent_id}_{stamp}_{status}.json"
    payload = {
        "record_name": record_name,
        "agent_id": agent_id,
        "workspace": workspace,
        "source": "dispatch_petition",
        "timestamp_created": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "task": task,
        "confidence": 0.5,
        "promotion_candidate": False,
        "payload_type": "pattern",
        "urgency": "normal",
        "requires_emissary": True,
    }

    path = target_dir / record_name
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
