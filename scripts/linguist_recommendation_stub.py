import json
from datetime import datetime, timezone

payload = {
  "ok": True,
  "expert": "linguist",
  "timestamp": "",
  "recommendations": [
    {
      "task_class": "dispatch_triage",
      "current_model": "local_deep",
      "suggested_model": "local_fast",
      "reason": "lower latency with sufficient quality",
      "confidence": 0.74
    }
  ],
  "notes": [
    "recommendations are advisory only",
    "operator approval required for production changes"
  ]
}

payload["timestamp"] = datetime.now(timezone.utc).isoformat()
print(json.dumps(payload, indent=2))
