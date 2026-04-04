import json
from datetime import datetime, timezone

payload = {
  "ok": True,
  "expert": "linguist",
  "timestamp": "",
  "recommendations": [
    {
      "task_class": "dispatch_triage",
      "current_model": "local_production_qwen2_5_coder_14b",
      "suggested_model": "local_onboarding_gemma4_e4b_4k",
      "reason": "candidate onboarding check against a lighter local model",
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
