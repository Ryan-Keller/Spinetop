from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repo_paths import repo_root
from run_hermes_v1 import validate_response_object


ROOT = repo_root()
DRAFTS_DIR = ROOT / "memory" / "drafts"
CREATED_BY = "hermes_spinetop_v1"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_input(path_text: str) -> dict[str, Any]:
    if path_text == "-" or not path_text.strip():
        raw_text = sys.stdin.read()
        source_label = "stdin"
    else:
        source_path = Path(path_text)
        raw_text = source_path.read_text(encoding="utf-8")
        source_label = str(source_path)

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON from {source_label}: {exc}") from exc

    if not isinstance(payload, dict):
        raise SystemExit(f"input must be a JSON object from {source_label}")
    return payload


def validate_hermes_run(run: dict[str, Any]) -> dict[str, Any]:
    run_id = run.get("run_id")
    mode = run.get("mode")
    if not isinstance(run_id, str) or not run_id.strip():
        raise SystemExit("Sentinel run is missing a non-empty run_id")
    if not isinstance(mode, str) or not mode.strip():
        raise SystemExit("Sentinel run is missing a non-empty mode")

    ok, reason = validate_response_object(run, run_id, mode)
    if not ok:
        raise SystemExit(f"Sentinel run validation failed: {reason}")
    return run


def _short_digest(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6]


def build_petition_id(run: dict[str, Any]) -> str:
    stamp = utc_stamp()
    seed = f"{run['run_id']}|{run['mode']}|{run['recommended_action']}|{run['summary']}|{stamp}"
    return f"draft_{stamp}_{_short_digest(seed)}"


def derive_petition_type(run: dict[str, Any]) -> str:
    petition_kind = str(run.get("petition_kind") or "").strip()
    if petition_kind:
        return petition_kind

    action = str(run.get("recommended_action") or "").strip()
    mode = str(run.get("mode") or "").strip()
    if action in {"operator_review", "defer"}:
        return "operator_review"
    if action == "create_dispatch_petition":
        if mode == "repair_check":
            return "repair_request"
        if mode in {"anomaly_review", "repetition_review"}:
            return "anomaly_review"
        return "operator_review"
    return "operator_review"


def build_draft(run: dict[str, Any]) -> dict[str, Any] | None:
    action = str(run["recommended_action"]).strip()
    if action == "none":
        return None

    petition_kind = derive_petition_type(run)
    draft: dict[str, Any] = {
        "petition_id": build_petition_id(run),
        "created_by": CREATED_BY,
        "mode": run["mode"],
        "petition_kind": petition_kind,
        "petition_type": petition_kind,
        "status": "draft",
        "summary": str(run["summary"]).strip(),
        "evidence_refs": [str(item).strip() for item in run["evidence_refs"]],
        "requested_action": action,
        "confidence": run["confidence"],
        "source_run_id": run["run_id"],
        "notes": "Generated from Hermes output. Not submitted.",
    }
    if action == "defer":
        draft["low_priority"] = True
    return draft


def draft_path_for(draft: dict[str, Any]) -> Path:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    return DRAFTS_DIR / f"{draft['petition_id']}.json"


def write_draft(draft: dict[str, Any]) -> Path:
    path = draft_path_for(draft)
    path.write_text(json.dumps(draft, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a Sentinel v1 run into a draft petition JSON.")
    parser.add_argument("input", nargs="?", default="-", help="Sentinel run JSON file path or - for stdin")
    parser.add_argument("--write", action="store_true", help="Save the draft JSON under memory/drafts/")
    args = parser.parse_args()

    run = validate_hermes_run(load_input(args.input))
    draft = build_draft(run)
    if draft is None:
        return 0

    if args.write:
        write_draft(draft)

    json.dump(draft, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
