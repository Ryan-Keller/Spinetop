from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import dashboard_api
import mission_storage
from state_machine import normalize_mission_id


SANDBOX_MARKER_FILENAME = "role_test_sandbox.json"
DEFAULT_OBJECTIVE_SUFFIX = "helper_2b -> Expeditioner -> Mirror"
SANDBOX_OBJECTIVE_PREFIX = "Sandbox role validation:"
DEFAULT_ROLE_SEQUENCE = [
    "spinetop-helper_2b",
    "spinetop_expeditioner",
    "spinetop-mirror",
]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    dashboard_api.app.config["TESTING"] = True
    with dashboard_api.app.test_client() as client:
        response = client.post(path, json=payload)
    body = response.get_json(silent=True) or {}
    if response.status_code >= 400:
        raise RuntimeError(f"POST {path} failed with HTTP {response.status_code}: {body}")
    if not body.get("ok", False):
        raise RuntimeError(f"POST {path} returned a non-ok payload: {body}")
    return body


def _marker_path(mission_id: str) -> Path:
    mission = normalize_mission_id(mission_id)
    return mission_storage._workbench_notes_root(mission, ensure=True) / SANDBOX_MARKER_FILENAME


def _marker_payload(mission_id: str, objective: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    return {
        "marker_kind": "role_test_sandbox",
        "mission_id": mission,
        "created_at": dashboard_api.iso_now(),
        "objective": objective,
        "operator_pattern": "fresh mission for explicit manual role invocation",
        "intended_role_sequence": DEFAULT_ROLE_SEQUENCE,
        "governance": {
            "mission_local_only": True,
            "no_truth_writes": True,
            "no_autonomy_loops": True,
            "no_hidden_behavior": True,
        },
    }


def _read_jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def inspect_sandbox_mission(mission_id: str) -> dict[str, Any]:
    mission = normalize_mission_id(mission_id)
    if not ((mission_storage._mission_root(mission).exists()) or (mission_storage._workbench_root(mission).exists())):
        raise ValueError(f"mission not found: {mission}")

    marker_path = _marker_path(mission)
    marker = mission_storage._load_json(marker_path) if marker_path.exists() else None
    parking_status = mission_storage._read_parking_status(mission)
    trigger_records = mission_storage._read_trigger_records(mission)
    trigger_handoff = mission_storage._read_trigger_handoff(mission)
    retry_ledger = mission_storage._read_retry_ledger(mission)
    agent_runs = mission_storage._read_agent_runs(mission)
    runner_returns = mission_storage._read_runner_returns(mission)
    mirror_notes = mission_storage._read_mirror_notes(mission)
    chat_count = _read_jsonl_count(mission_storage._mission_chat_path(mission))
    input_count = len(mission_storage._mission_inputs(mission))

    clean_checks = {
        "not_parked": str(parking_status.get("status") or "active").strip() == "active",
        "no_trigger_records": len(trigger_records) == 0,
        "no_pending_trigger_handoff": str(trigger_handoff.get("status") or "idle").strip() == "idle",
        "retry_budget_unused": int(retry_ledger.get("retry_budget_used") or 0) == 0,
        "no_retry_decisions": len(retry_ledger.get("decision_log") or []) == 0,
        "no_chat_history": chat_count == 0,
        "no_operator_inputs": input_count == 0,
        "no_agent_runs": len(agent_runs) == 0,
        "no_runner_returns": len(runner_returns) == 0,
        "no_mirror_notes": len(mirror_notes) == 0,
    }

    return {
        "mission_id": mission,
        "objective": str((dashboard_api.read_mission_brief(mission) or {}).get("objective") or "").strip(),
        "marker_path": marker_path.relative_to(mission_storage.ROOT).as_posix() if marker_path.exists() else "",
        "is_marked_sandbox": isinstance(marker, dict) and str(marker.get("marker_kind") or "") == "role_test_sandbox",
        "is_clean": all(clean_checks.values()),
        "clean_checks": clean_checks,
        "parking_status": parking_status,
        "counts": {
            "trigger_records": len(trigger_records),
            "retry_budget_used": int(retry_ledger.get("retry_budget_used") or 0),
            "retry_decisions": len(retry_ledger.get("decision_log") or []),
            "chat_messages": chat_count,
            "operator_inputs": input_count,
            "agent_runs": len(agent_runs),
            "runner_returns": len(runner_returns),
            "mirror_notes": len(mirror_notes),
        },
    }


def create_sandbox_mission(objective_suffix: str = DEFAULT_OBJECTIVE_SUFFIX) -> dict[str, Any]:
    suffix = str(objective_suffix or "").strip() or DEFAULT_OBJECTIVE_SUFFIX
    objective = f"{SANDBOX_OBJECTIVE_PREFIX} {suffix}"
    created = _post_json("/api/expeditions", {"objective": objective})
    item = created.get("item") if isinstance(created.get("item"), dict) else {}
    mission_id = str(item.get("mission_id") or "").strip()
    if not mission_id:
        raise RuntimeError(f"mission create response did not contain mission_id: {created}")
    _write_json(_marker_path(mission_id), _marker_payload(mission_id, objective))
    inspection = inspect_sandbox_mission(mission_id)
    return {
        "mission_id": mission_id,
        "objective": objective,
        "marker_path": inspection.get("marker_path"),
        "inspection": inspection,
    }


def _print_human_create(result: dict[str, Any]) -> None:
    inspection = result.get("inspection") if isinstance(result.get("inspection"), dict) else {}
    print(f"mission_id={result['mission_id']}")
    print(f"objective={result['objective']}")
    print(f"marker={result.get('marker_path')}")
    print(f"is_clean={inspection.get('is_clean')}")
    print("recommended_sequence=spinetop-helper_2b -> spinetop_expeditioner -> spinetop-mirror")
    print("invoke_example=python scripts/agent_invocation.py spinetop-helper_2b <mission_id> --input-json '{\"trigger_reason\":\"role_test_sandbox\"}'")


def _print_human_check(result: dict[str, Any]) -> None:
    print(f"mission_id={result['mission_id']}")
    print(f"objective={result['objective']}")
    print(f"is_marked_sandbox={result['is_marked_sandbox']}")
    print(f"is_clean={result['is_clean']}")
    for key, value in result.get("clean_checks", {}).items():
        print(f"{key}={value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or inspect a clean mission-local sandbox for explicit role testing.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a fresh role-test sandbox mission.")
    create_parser.add_argument(
        "--objective-suffix",
        default=DEFAULT_OBJECTIVE_SUFFIX,
        help="Suffix appended after the sandbox objective prefix.",
    )
    create_parser.add_argument("--json", action="store_true", help="Print JSON instead of key=value lines.")

    check_parser = subparsers.add_parser("check", help="Inspect whether an existing mission is still clean for role testing.")
    check_parser.add_argument("mission_id")
    check_parser.add_argument("--json", action="store_true", help="Print JSON instead of key=value lines.")

    args = parser.parse_args()

    if args.command == "create":
        result = create_sandbox_mission(args.objective_suffix)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            _print_human_create(result)
        return 0 if bool((result.get("inspection") or {}).get("is_clean")) else 1

    result = inspect_sandbox_mission(args.mission_id)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_human_check(result)
    return 0 if bool(result.get("is_clean")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
