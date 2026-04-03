from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_DIR = ROOT / "logs" / "governance"
STATE_PATH = GOVERNANCE_DIR / "return_all.json"

DEFAULT_STATE = {
    "ok": True,
    "enabled": False,
    "issued_by": "",
    "issued_at": "",
    "reason": "",
    "allow_custodial_bypass": False,
}


def build_state(
    *,
    enabled: bool,
    issued_by: str,
    reason: str,
    allow_custodial_bypass: bool,
    timestamp: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "enabled": enabled,
        "issued_by": issued_by,
        "issued_at": timestamp or datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "allow_custodial_bypass": bool(allow_custodial_bypass) if enabled else False,
    }


def read_state(path: Path = STATE_PATH) -> dict[str, Any]:
    try:
        if not path.exists():
            return dict(DEFAULT_STATE)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return dict(DEFAULT_STATE)
        merged = dict(DEFAULT_STATE)
        merged.update(payload)
        merged["enabled"] = bool(merged.get("enabled"))
        merged["allow_custodial_bypass"] = bool(merged.get("allow_custodial_bypass"))
        return merged
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_STATE)


def write_state(payload: dict[str, Any], path: Path = STATE_PATH) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def set_return_all(
    *,
    enabled: bool,
    issued_by: str = "operator",
    reason: str = "",
    allow_custodial_bypass: bool = False,
    path: Path = STATE_PATH,
) -> dict[str, Any]:
    payload = build_state(
        enabled=enabled,
        issued_by=issued_by,
        reason=reason,
        allow_custodial_bypass=allow_custodial_bypass,
    )
    return write_state(payload, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["enable", "disable"])
    parser.add_argument("--reason", default="")
    parser.add_argument("--issued-by", default="operator")
    parser.add_argument("--allow-custodial-bypass", action="store_true")
    args = parser.parse_args()

    enabled = args.mode == "enable"
    payload = set_return_all(
        enabled=enabled,
        issued_by=args.issued_by,
        reason=args.reason,
        allow_custodial_bypass=args.allow_custodial_bypass,
    )
    print(json.dumps({"ok": True, "state_path": str(STATE_PATH), "enabled": enabled, "state": payload}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
