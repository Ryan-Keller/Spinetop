from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_DIR = ROOT / "logs" / "governance"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["enable", "disable"])
    parser.add_argument("--reason", default="")
    parser.add_argument("--issued-by", default="operator")
    parser.add_argument("--allow-custodial-bypass", action="store_true")
    args = parser.parse_args()

    enabled = args.mode == "enable"
    payload = {
        "ok": True,
        "enabled": enabled,
        "issued_by": args.issued_by,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "reason": args.reason,
        "allow_custodial_bypass": bool(args.allow_custodial_bypass),
    }

    GOVERNANCE_DIR.mkdir(parents=True, exist_ok=True)
    path = GOVERNANCE_DIR / "return_all.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
