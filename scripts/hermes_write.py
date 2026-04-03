from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime

if len(sys.argv) < 3:
    print("Usage: hermes_write.py <task> <summary> [promote]", file=sys.stderr)
    sys.exit(1)

task = sys.argv[1]
summary = sys.argv[2]
promote_flag = len(sys.argv) >= 4 and sys.argv[3].strip().lower() == "promote"

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "memory" / "inbox"
INBOX.mkdir(parents=True, exist_ok=True)

record = {
    "source": "hermes-runtime",
    "expert_name": "hermes",
    "task": task,
    "summary": summary,
    "key_findings": [],
    "confidence": 0.75,
    "recommended_action": "pending_review",
    "promotion_candidate": promote_flag
}

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"hermes_{stamp}.json"
path = INBOX / filename

path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

print(f"[Hermes] wrote → {path}")
print(f"[Hermes] promotion_candidate = {promote_flag}")

log_path = ROOT / "logs" / "topology" / "events.jsonl"
log_path.parent.mkdir(parents=True, exist_ok=True)
event = {
    "timestamp": datetime.now().isoformat(timespec="seconds"),
    "machine": "Spinetop",
    "event_type": "hermes_write",
    "record_name": filename,
    "status": "created",
    "detail": f"promotion_candidate={promote_flag}"
}
with log_path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(event, ensure_ascii=False) + "\n")
