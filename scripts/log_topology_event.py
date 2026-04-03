from __future__ import annotations

import json
import sys
from datetime import datetime

from repo_paths import repo_root


if len(sys.argv) < 4:
    print("Usage: log_topology_event.py <event_type> <record_name> <status> [detail]", file=sys.stderr)
    sys.exit(1)

event_type = sys.argv[1]
record_name = sys.argv[2]
status = sys.argv[3]
detail = sys.argv[4] if len(sys.argv) >= 5 else ""

root = repo_root()
log_dir = root / "logs" / "topology"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "events.jsonl"

event = {
    "timestamp": datetime.now().isoformat(timespec="seconds"),
    "machine": "Spinetop",
    "event_type": event_type,
    "record_name": record_name,
    "status": status,
    "detail": detail,
}

with log_file.open("a", encoding="utf-8") as f:
    f.write(json.dumps(event, ensure_ascii=False) + "\n")

print(f"[topology] logged {event_type} {record_name} {status}")
