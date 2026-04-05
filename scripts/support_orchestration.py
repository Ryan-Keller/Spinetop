from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from helper_model_runtime import load_helper_runtime_profile
from repo_paths import repo_root
from support_validation import (
    validate_support_event_record,
    validate_support_request,
    require_object,
    require_string,
)


ROOT = repo_root()
ORCH_ROOT = ROOT / "logs" / "support" / "orchestration"
REQUEST_DIR = ORCH_ROOT / "requests"
INSTANCE_DIR = ORCH_ROOT / "instances"
ARTIFACT_DIR = ORCH_ROOT / "artifacts"
EVENT_LOG = ORCH_ROOT / "events.jsonl"
HELPER_2B_RUNTIME_PROFILE = load_helper_runtime_profile("helper_2b")

HELPER_CATALOG: dict[str, dict[str, Any]] = {
    "retrieval_helper_2b": {
        "purpose": "Fetch references, assemble retrieval bundles, and return full sets or explicit none-found results.",
        "allowed_actions": [
            "read approved retrieval sources",
            "assemble retrieval bundles",
            "return evidence refs",
            "report complete, partial, none_found, blocked, or failed",
        ],
        "forbidden_actions": [
            "write to collective",
            "write to approved dispatch",
            "write to Honcho",
            "decide legitimacy",
            "hide conflicting evidence",
            "rank truth unless explicitly instructed",
        ],
        "allowed_write_scope": [
            "logs/support/orchestration/",
            "logs/support/retrieval/",
            "memory/drafts/",
        ],
        "default_ttl_seconds": 900,
        "runtime_role": "helper_2b",
        "runtime_profile": {
            "execution_backend": HELPER_2B_RUNTIME_PROFILE.execution_backend,
            "allowed_model_keys": HELPER_2B_RUNTIME_PROFILE.allowed_model_keys,
            "default_model_key": HELPER_2B_RUNTIME_PROFILE.default_model_key,
            "fallback_model_key": HELPER_2B_RUNTIME_PROFILE.fallback_model_key,
            "provider_requirement": HELPER_2B_RUNTIME_PROFILE.provider_requirement,
        },
        "expected_outputs": [
            "support log receipt",
            "retrieval bundle artifact",
            "none-found result artifact",
        ],
    },
    "runner_helper_2b": {
        "purpose": "Run one bounded procedural support task and return an operational receipt.",
        "allowed_actions": [
            "run a bounded procedure",
            "report step completion",
            "bundle results",
            "report blocked or failed status",
        ],
        "forbidden_actions": [
            "write to collective",
            "write to approved dispatch",
            "write to Honcho",
            "decide legitimacy",
            "become a strategist",
            "become a hidden control layer",
        ],
        "allowed_write_scope": [
            "logs/support/orchestration/",
            "logs/support/runs/",
            "memory/drafts/",
        ],
        "required_request_fields": [
            "task_plan",
        ],
        "task_plan": {
            "type": "list[string]",
            "min_items": 1,
            "max_items": 12,
        },
        "default_ttl_seconds": 1200,
        "runtime_role": "helper_2b",
        "runtime_profile": {
            "execution_backend": HELPER_2B_RUNTIME_PROFILE.execution_backend,
            "allowed_model_keys": HELPER_2B_RUNTIME_PROFILE.allowed_model_keys,
            "default_model_key": HELPER_2B_RUNTIME_PROFILE.default_model_key,
            "fallback_model_key": HELPER_2B_RUNTIME_PROFILE.fallback_model_key,
            "provider_requirement": HELPER_2B_RUNTIME_PROFILE.provider_requirement,
        },
        "expected_outputs": [
            "support log receipt",
            "run receipt artifact",
            "blocked or failed receipt when the task cannot proceed",
        ],
    },
}

ALLOWED_REQUEST_TYPES = {"spawn", "replace"}
ALLOWED_STATUSES = {"active", "complete", "failed", "blocked", "replaced", "expired"}
ALLOWED_REPLACEMENT_REASONS = {"timeout", "drift", "inconsistent_output", "overload"}
SUPPORT_LANES = ("logs/support/", "memory/drafts/")
TERMINAL_STATUSES = {"complete", "failed", "blocked", "expired", "replaced"}

CONTRACT = {
    "request_types": sorted(ALLOWED_REQUEST_TYPES),
    "lifecycle": [
        "spawn -> active",
        "active -> complete",
        "active -> failed",
        "active -> blocked",
        "active -> expired",
        "active -> replaced",
        "replaced -> active (replacement spawn)",
    ],
    "request_fields": [
        "request_type",
        "helper_type",
        "requested_by",
        "mandate_id",
        "task_scope",
        "ttl_seconds",
        "return_lane",
        "write_scope",
    ],
    "helper_fields": [
        "helper_id",
        "helper_type",
        "created_at",
        "expires_at",
        "mandate_id",
        "task_scope",
        "write_scope",
        "status",
    ],
    "allowed_statuses": sorted(ALLOWED_STATUSES),
    "replacement_reasons": sorted(ALLOWED_REPLACEMENT_REASONS),
    "helper_catalog": HELPER_CATALOG,
    "write_boundaries": {
        "allowed_support_lanes": list(SUPPORT_LANES),
        "forbidden": [
            "memory/collective/",
            "memory/dispatch/approved/",
            "Honcho",
        ],
    },
    "event_log": "logs/support/orchestration/events.jsonl",
}


class SupportOrchestrationError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")


def _path_hint(path: Path | None) -> str:
    return f" ({path})" if path else ""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise SupportOrchestrationError(f"Missing file{_path_hint(path)}") from exc
    except json.JSONDecodeError as exc:
        raise SupportOrchestrationError(f"Malformed JSON{_path_hint(path)}: {exc}") from exc


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False) + "\n")


def _path_to_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except Exception:
        return path.resolve().as_posix()


def _build_helper_id(*, helper_type: str, requested_by: str, mandate_id: str, task_scope: str, ttl_seconds: int) -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    digest = hashlib.sha1(
        f"{helper_type}|{requested_by}|{mandate_id}|{task_scope}|{ttl_seconds}|{stamp}".encode("utf-8")
    ).hexdigest()[:8]
    return f"{helper_type}_{stamp}_{digest}"


def _helper_paths(helper_id: str) -> tuple[Path, Path, Path]:
    instance_path = INSTANCE_DIR / f"{helper_id}.json"
    receipt_path = ARTIFACT_DIR / f"{helper_id}.json"
    return instance_path, receipt_path, EVENT_LOG


def _validate_request(data: Any, *, path: Path | None = None) -> dict[str, Any]:
    record = require_object(data, path=path, error_cls=SupportOrchestrationError)
    request_type = require_string(record, "request_type", path=path, error_cls=SupportOrchestrationError)
    if request_type not in ALLOWED_REQUEST_TYPES:
        raise SupportOrchestrationError(f"request_type must be one of {sorted(ALLOWED_REQUEST_TYPES)}{_path_hint(path)}")

    helper_type = require_string(record, "helper_type", path=path, error_cls=SupportOrchestrationError)
    if helper_type not in HELPER_CATALOG:
        raise SupportOrchestrationError(f"helper_type must be one of {sorted(HELPER_CATALOG)}{_path_hint(path)}")

    normalized = validate_support_request(
        record,
        allowed_helper_types=HELPER_CATALOG.keys(),
        allowed_write_scope=HELPER_CATALOG[helper_type]["allowed_write_scope"],
        required_write_scope=["logs/support/orchestration/"],
        path=path,
        error_cls=SupportOrchestrationError,
    )

    normalized["request_type"] = request_type

    if helper_type == "runner_helper_2b":
        task_plan = record.get("task_plan")
        if not isinstance(task_plan, list) or not task_plan:
            raise SupportOrchestrationError(f"Field 'task_plan' must be a non-empty list{_path_hint(path)}")
        normalized_task_plan: list[str] = []
        for idx, item in enumerate(task_plan):
            if not isinstance(item, str):
                raise SupportOrchestrationError(f"Field 'task_plan' item {idx} must be a string{_path_hint(path)}")
            text = item.strip()
            if not text:
                raise SupportOrchestrationError(f"Field 'task_plan' item {idx} must not be empty{_path_hint(path)}")
            normalized_task_plan.append(text)
        if len(normalized_task_plan) > 12:
            raise SupportOrchestrationError(f"Field 'task_plan' must contain at most 12 steps{_path_hint(path)}")
        normalized["task_plan"] = normalized_task_plan
        normalized["task_plan_count"] = len(normalized_task_plan)

    if request_type == "replace":
        replaced_helper_id = require_string(record, "replaces_helper_id", path=path, error_cls=SupportOrchestrationError)
        replacement_reason = require_string(record, "replacement_reason", path=path, error_cls=SupportOrchestrationError)
        if replacement_reason not in ALLOWED_REPLACEMENT_REASONS:
            raise SupportOrchestrationError(
                f"replacement_reason must be one of {sorted(ALLOWED_REPLACEMENT_REASONS)}{_path_hint(path)}"
            )
        normalized["replaces_helper_id"] = replaced_helper_id
        normalized["replacement_reason"] = replacement_reason

    return normalized


def _build_instance(request: dict[str, Any], *, status: str = "active", replaced_helper_id: str = "") -> dict[str, Any]:
    created_at = utc_now()
    expires_at = created_at + timedelta(seconds=int(request["ttl_seconds"]))
    helper_id = _build_helper_id(
        helper_type=request["helper_type"],
        requested_by=request["requested_by"],
        mandate_id=request["mandate_id"],
        task_scope=request["task_scope"],
        ttl_seconds=int(request["ttl_seconds"]),
    )
    return {
        "helper_id": helper_id,
        "helper_type": request["helper_type"],
        "created_at": created_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "mandate_id": request["mandate_id"],
        "task_scope": request["task_scope"],
        "write_scope": request["write_scope"],
        "status": status,
        "requested_by": request["requested_by"],
        "request_type": request["request_type"],
        "ttl_seconds": int(request["ttl_seconds"]),
        "return_lane": request["return_lane"],
        "replaced_helper_id": replaced_helper_id,
        "replacement_reason": request.get("replacement_reason", ""),
        "task_plan": list(request.get("task_plan") or []),
        "task_plan_count": int(request.get("task_plan_count") or len(request.get("task_plan") or [])),
    }


def _event_record(
    *,
    event_type: str,
    helper: dict[str, Any],
    request_ref: str,
    outputs_refs: list[str] | None = None,
    inputs_refs: list[str] | None = None,
    note: str = "",
    old_helper_id: str = "",
) -> dict[str, Any]:
    return {
        "support_event_id": _build_helper_id(
            helper_type=helper["helper_type"],
            requested_by=helper["requested_by"],
            mandate_id=helper["mandate_id"],
            task_scope=helper["task_scope"],
            ttl_seconds=int(helper["ttl_seconds"]),
        ),
        "event_type": event_type,
        "requested_by": helper["requested_by"],
        "helper_id": helper["helper_id"],
        "helper_type": helper["helper_type"],
        "mandate_id": helper["mandate_id"],
        "task_scope": helper["task_scope"],
        "status": helper["status"],
        "created_at": utc_now_iso(),
        "expires_at": helper["expires_at"],
        "ttl_seconds": int(helper["ttl_seconds"]),
        "return_lane": helper["return_lane"],
        "write_scope": helper["write_scope"],
        "request_ref": request_ref,
        "inputs_refs": inputs_refs or [],
        "outputs_refs": outputs_refs or [],
        "note": note,
        "replaces_helper_id": old_helper_id or helper.get("replaced_helper_id", ""),
        "replacement_reason": helper.get("replacement_reason", ""),
    }


def _write_event(event: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_support_event_record(
        event,
        allowed_helper_types=HELPER_CATALOG.keys(),
        allowed_write_scope=HELPER_CATALOG[event["helper_type"]]["allowed_write_scope"],
        required_write_scope=["logs/support/orchestration/"],
        error_cls=SupportOrchestrationError,
    )
    _append_jsonl(EVENT_LOG, normalized)
    return normalized


def _write_request_receipt(helper: dict[str, Any], request_ref: str, *, event_type: str) -> Path:
    _, receipt_path, _ = _helper_paths(helper["helper_id"])
    receipt = {
        "helper_id": helper["helper_id"],
        "helper_type": helper["helper_type"],
        "request_type": helper["request_type"],
        "status": helper["status"],
        "created_at": helper["created_at"],
        "expires_at": helper["expires_at"],
        "mandate_id": helper["mandate_id"],
        "task_scope": helper["task_scope"],
        "write_scope": helper["write_scope"],
        "requested_by": helper["requested_by"],
        "return_lane": helper["return_lane"],
        "request_ref": request_ref,
        "event_type": event_type,
        "replacement_reason": helper.get("replacement_reason", ""),
        "task_plan": list(helper.get("task_plan") or []),
    }
    _write_json(receipt_path, receipt)
    return receipt_path


def _load_instance(helper_id: str) -> dict[str, Any]:
    instance_path, _, _ = _helper_paths(helper_id)
    if not instance_path.exists():
        raise SupportOrchestrationError(f"Missing helper instance: {instance_path}")
    instance = require_object(_load_json(instance_path), path=instance_path, error_cls=SupportOrchestrationError)
    if instance.get("helper_id") != helper_id:
        raise SupportOrchestrationError(f"Helper record mismatch for {helper_id}")
    return instance


def _iter_instance_paths() -> list[Path]:
    if not INSTANCE_DIR.exists():
        return []
    return sorted(path for path in INSTANCE_DIR.glob("*.json") if path.is_file())


def _persist_instance(instance: dict[str, Any]) -> Path:
    instance_path, _, _ = _helper_paths(instance["helper_id"])
    _write_json(instance_path, instance)
    return instance_path


def spawn(request_path: Path) -> tuple[dict[str, Any], Path]:
    request = _validate_request(_load_json(request_path), path=request_path)
    helper = _build_instance(request, status="active")
    instance_path = _persist_instance(helper)
    receipt_path = _write_request_receipt(helper, request_ref=_path_to_ref(request_path), event_type="spawn")
    _write_event(
        _event_record(
            event_type="spawn",
            helper=helper,
            request_ref=_path_to_ref(request_path),
            outputs_refs=[_path_to_ref(instance_path), _path_to_ref(receipt_path)],
            note="helper spawned",
        )
    )
    return helper, instance_path


def replace(request_path: Path) -> tuple[dict[str, Any], Path]:
    request = _validate_request(_load_json(request_path), path=request_path)
    old_helper = _load_instance(request["replaces_helper_id"])
    if old_helper.get("status") not in {"active", "expired"}:
        raise SupportOrchestrationError(
            f"Helper {old_helper['helper_id']} is not replaceable from status {old_helper.get('status')}"
        )
    old_helper["replaced_at"] = utc_now_iso()
    old_helper["replaced_by"] = request["helper_type"]
    old_helper["replacement_reason"] = request["replacement_reason"]
    if old_helper.get("status") == "active":
        old_helper["status"] = "replaced"
    _persist_instance(old_helper)

    helper = _build_instance(request, status="active", replaced_helper_id=old_helper["helper_id"])
    instance_path = _persist_instance(helper)
    receipt_path = _write_request_receipt(helper, request_ref=_path_to_ref(request_path), event_type="replace")
    _write_event(
        _event_record(
            event_type="replace",
            helper=helper,
            request_ref=_path_to_ref(request_path),
            outputs_refs=[_path_to_ref(instance_path), _path_to_ref(receipt_path)],
            inputs_refs=[_path_to_ref(request_path), _path_to_ref(_helper_paths(old_helper["helper_id"])[0])],
            note=f"replaced {old_helper['helper_id']}",
            old_helper_id=old_helper["helper_id"],
        )
    )
    return helper, instance_path


def mark_status(helper_id: str, status: str, *, note: str = "", outputs_refs: list[str] | None = None) -> dict[str, Any]:
    if status not in ALLOWED_STATUSES:
        raise SupportOrchestrationError(f"status must be one of {sorted(ALLOWED_STATUSES)}")
    helper = _load_instance(helper_id)
    current_status = helper.get("status", "")
    if current_status in TERMINAL_STATUSES and status != current_status:
        raise SupportOrchestrationError(
            f"Helper {helper_id} is already terminal as {current_status} and cannot transition to {status}"
        )
    if current_status == "active" and status == "replaced":
        raise SupportOrchestrationError(
            f"Helper {helper_id} cannot self-transition to replaced; use replacement flow"
        )
    helper["status"] = status
    helper["updated_at"] = utc_now_iso()
    if note:
        helper["note"] = note
    _persist_instance(helper)
    request_ref = _path_to_ref(_helper_paths(helper_id)[0])
    normalized_event = _write_event(
        _event_record(
            event_type=status,
            helper=helper,
            request_ref=request_ref,
            outputs_refs=outputs_refs,
            note=note,
        )
    )
    validated_outputs = normalized_event.get("outputs_refs", [])
    _, receipt_path, _ = _helper_paths(helper_id)
    receipt = {
        "helper_id": helper["helper_id"],
        "helper_type": helper["helper_type"],
        "status": helper["status"],
        "updated_at": helper["updated_at"],
        "note": note,
        "outputs_refs": validated_outputs,
    }
    _write_json(receipt_path, receipt)
    return helper


def sweep_expired() -> list[dict[str, Any]]:
    now = utc_now()
    expired: list[dict[str, Any]] = []
    for path in _iter_instance_paths():
        helper = require_object(_load_json(path), path=path, error_cls=SupportOrchestrationError)
        if helper.get("helper_type") not in HELPER_CATALOG:
            continue
        if helper.get("status") != "active":
            continue
        expires_at = helper.get("expires_at")
        if not isinstance(expires_at, str) or not expires_at.strip():
            continue
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).astimezone(timezone.utc)
        if now < expires_dt:
            continue
        helper["status"] = "expired"
        helper["expired_at"] = utc_now_iso()
        helper["updated_at"] = helper["expired_at"]
        _write_json(path, helper)
        event = _event_record(
            event_type="expired",
            helper=helper,
            request_ref=_path_to_ref(path),
            note="ttl expired",
        )
        _write_event(event)
        expired.append(helper)
    return expired


def print_contract() -> int:
    print(json.dumps(CONTRACT, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal support orchestration for disposable helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("contract", help="Print the exact support orchestration contract.")

    spawn_parser = subparsers.add_parser("spawn", help="Spawn a helper instance from a request JSON file.")
    spawn_parser.add_argument("request_json")

    replace_parser = subparsers.add_parser("replace", help="Replace an existing helper instance from a request JSON file.")
    replace_parser.add_argument("request_json")

    mark_parser = subparsers.add_parser("mark", help="Mark a helper instance with a terminal support status.")
    mark_parser.add_argument("helper_id")
    mark_parser.add_argument("status", choices=sorted(ALLOWED_STATUSES))
    mark_parser.add_argument("--note", default="")
    mark_parser.add_argument("--output-ref", action="append", dest="output_refs", default=[])

    sweep_parser = subparsers.add_parser("sweep", help="Mark active helpers expired when TTL has elapsed.")

    args = parser.parse_args()

    try:
        if args.command == "contract":
            return print_contract()
        if args.command == "spawn":
            helper, instance_path = spawn(Path(args.request_json))
            print(instance_path)
            return 0
        if args.command == "replace":
            helper, instance_path = replace(Path(args.request_json))
            print(instance_path)
            return 0
        if args.command == "mark":
            helper = mark_status(args.helper_id, args.status, note=args.note, outputs_refs=args.output_refs)
            print(_helper_paths(helper["helper_id"])[0])
            return 0
        if args.command == "sweep":
            expired = sweep_expired()
            print(json.dumps({"expired": [helper["helper_id"] for helper in expired]}, indent=2))
            return 0
    except SupportOrchestrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
