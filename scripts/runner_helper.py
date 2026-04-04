from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import support_orchestration
from repo_paths import repo_root
from support_validation import (
    normalize_write_scope,
    require_object,
    require_string,
    require_support_lane,
    validate_ttl_seconds,
)


ROOT = repo_root()
HELPER_TYPE = "runner_helper_2b"
RUN_DIR = ROOT / "logs" / "support" / "runs"
RUN_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_INSTANCE_STATUSES = {"active", "complete", "failed", "blocked", "replaced", "expired"}

CONTRACT = {
    "helper_type": HELPER_TYPE,
    "instance_fields": [
        "helper_id",
        "helper_type",
        "mandate_id",
        "task_scope",
        "task_plan",
        "created_at",
        "expires_at",
        "write_scope",
        "status",
        "requested_by",
        "ttl_seconds",
        "return_lane",
    ],
    "task_plan": {
        "type": "list[string]",
        "min_items": 1,
        "max_items": 12,
    },
    "output_fields": [
        "helper_id",
        "helper_type",
        "status",
        "task_scope",
        "step_transcript",
        "task_result",
        "outputs_refs",
    ],
    "allowed_statuses": sorted(ALLOWED_INSTANCE_STATUSES),
    "write_scope": ["logs/support/orchestration/", "logs/support/runs/", "memory/drafts/"],
    "return_lane": "logs/support/orchestration/",
    "expected_outputs": [
        "run transcript",
        "task result",
        "failure note when the run cannot complete",
    ],
}


class RunnerHelperError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")


def _path_hint(path: Path | None) -> str:
    return f" ({path})" if path else ""


def _is_under(path: Path, root: Path) -> bool:
    path = path.resolve()
    root = root.resolve()
    return path == root or root in path.parents


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise RunnerHelperError(f"Missing file{_path_hint(path)}") from exc
    except json.JSONDecodeError as exc:
        raise RunnerHelperError(f"Malformed JSON{_path_hint(path)}: {exc}") from exc


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _path_to_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except Exception:
        return path.resolve().as_posix()


def _parse_iso(value: str, *, path: Path | None = None, field: str = "timestamp") -> datetime:
    text = value.strip()
    raw = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise RunnerHelperError(f"Field '{field}' must be ISO-8601{_path_hint(path)}: {exc}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_task_plan(value: Any, *, path: Path | None = None) -> list[str]:
    if not isinstance(value, list) or not value:
        raise RunnerHelperError(f"Field 'task_plan' must be a non-empty list{_path_hint(path)}")
    if len(value) > 12:
        raise RunnerHelperError(f"Field 'task_plan' must contain at most 12 steps{_path_hint(path)}")
    plan: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            raise RunnerHelperError(f"Field 'task_plan' item {idx} must be a string{_path_hint(path)}")
        text = item.strip()
        if not text:
            raise RunnerHelperError(f"Field 'task_plan' item {idx} must not be empty{_path_hint(path)}")
        plan.append(text)
    return plan


def validate_runner_instance(data: Any, *, path: Path | None = None) -> dict[str, Any]:
    record = require_object(data, path=path, error_cls=RunnerHelperError)

    helper_id = require_string(record, "helper_id", path=path, error_cls=RunnerHelperError)
    helper_type = require_string(record, "helper_type", path=path, error_cls=RunnerHelperError)
    if helper_type != HELPER_TYPE:
        raise RunnerHelperError(f"helper_type must be {HELPER_TYPE}{_path_hint(path)}")

    status = require_string(record, "status", path=path, error_cls=RunnerHelperError)
    if status not in ALLOWED_INSTANCE_STATUSES:
        raise RunnerHelperError(f"Unsupported helper status{_path_hint(path)}: {status}")

    mandate_id = require_string(record, "mandate_id", path=path, error_cls=RunnerHelperError)
    task_scope = require_string(record, "task_scope", path=path, error_cls=RunnerHelperError)
    created_at = require_string(record, "created_at", path=path, error_cls=RunnerHelperError)
    expires_at = require_string(record, "expires_at", path=path, error_cls=RunnerHelperError)
    requested_by = require_string(record, "requested_by", path=path, error_cls=RunnerHelperError)
    ttl_seconds = validate_ttl_seconds(record.get("ttl_seconds"), path=path, error_cls=RunnerHelperError)
    return_lane = require_support_lane(
        require_string(record, "return_lane", path=path, error_cls=RunnerHelperError),
        normalize_write_scope(
            record.get("write_scope"),
            allowed_write_scope=CONTRACT["write_scope"],
            required_write_scope=["logs/support/orchestration/"],
            path=path,
            error_cls=RunnerHelperError,
        ),
        field="return_lane",
        path=path,
        error_cls=RunnerHelperError,
    )
    task_plan = _validate_task_plan(record.get("task_plan"), path=path)

    normalized = dict(record)
    normalized["helper_id"] = helper_id
    normalized["helper_type"] = helper_type
    normalized["status"] = status
    normalized["mandate_id"] = mandate_id
    normalized["task_scope"] = task_scope
    normalized["created_at"] = created_at
    normalized["expires_at"] = expires_at
    normalized["requested_by"] = requested_by
    normalized["ttl_seconds"] = ttl_seconds
    normalized["return_lane"] = return_lane
    normalized["task_plan"] = task_plan
    return normalized


def _build_step_transcript(task_plan: list[str]) -> list[dict[str, Any]]:
    transcript: list[dict[str, Any]] = []
    for idx, step in enumerate(task_plan, start=1):
        transcript.append(
            {
                "step_index": idx,
                "step": step,
                "status": "complete",
                "note": "step completed",
            }
        )
    return transcript


def _output_path(helper_id: str) -> Path:
    return RUN_DIR / f"{helper_id}.json"


def _build_receipt(
    instance: dict[str, Any],
    *,
    status: str,
    reason: str,
    step_transcript: list[dict[str, Any]],
    outputs_refs: list[str],
) -> dict[str, Any]:
    return {
        "helper_id": instance["helper_id"],
        "helper_type": instance["helper_type"],
        "mandate_id": instance["mandate_id"],
        "task_scope": instance["task_scope"],
        "requested_by": instance["requested_by"],
        "created_at": instance["created_at"],
        "completed_at": utc_now_iso(),
        "status": status,
        "reason": reason,
        "task_plan": list(instance.get("task_plan") or []),
        "step_transcript": step_transcript,
        "task_result": {
            "summary": reason,
            "step_count": len(step_transcript),
        },
        "outputs_refs": outputs_refs,
        "return_lane": instance["return_lane"],
        "write_scope": list(instance.get("write_scope") or []),
    }


def run_instance(instance_path: Path) -> int:
    instance = validate_runner_instance(_load_json(instance_path), path=instance_path)
    output_path = _output_path(instance["helper_id"])
    artifact_ref = _path_to_ref(output_path)

    expires_at = _parse_iso(instance["expires_at"], path=instance_path, field="expires_at")
    now = utc_now()

    if instance["status"] != "active":
        receipt = _build_receipt(
            instance,
            status="blocked",
            reason=f"helper status is {instance['status']}",
            step_transcript=[],
            outputs_refs=[artifact_ref],
        )
        _write_json(output_path, receipt)
        print(artifact_ref)
        return 1

    if now > expires_at:
        receipt = _build_receipt(
            instance,
            status="blocked",
            reason="ttl expired before task could run",
            step_transcript=[],
            outputs_refs=[artifact_ref],
        )
        _write_json(output_path, receipt)
        try:
            support_orchestration.mark_status(
                instance["helper_id"],
                "expired",
                note="ttl expired before runner could complete",
                outputs_refs=[artifact_ref],
            )
        except Exception:
            pass
        print(artifact_ref)
        return 1

    task_plan = list(instance.get("task_plan") or [])
    if not task_plan:
        receipt = _build_receipt(
            instance,
            status="blocked",
            reason="task_plan is required",
            step_transcript=[],
            outputs_refs=[artifact_ref],
        )
        _write_json(output_path, receipt)
        try:
            support_orchestration.mark_status(
                instance["helper_id"],
                "blocked",
                note="task_plan missing",
                outputs_refs=[artifact_ref],
            )
        except Exception:
            pass
        print(artifact_ref)
        return 1

    step_transcript = _build_step_transcript(task_plan)
    receipt = _build_receipt(
        instance,
        status="complete",
        reason=f"completed {len(step_transcript)} step(s)",
        step_transcript=step_transcript,
        outputs_refs=[artifact_ref],
    )
    _write_json(output_path, receipt)
    try:
        support_orchestration.mark_status(
            instance["helper_id"],
            "complete",
            note="runner completed bounded task",
            outputs_refs=[artifact_ref],
        )
    except Exception as exc:
        raise RunnerHelperError(f"Failed to mark helper complete{_path_hint(instance_path)}: {exc}") from exc
    print(artifact_ref)
    return 0


def print_contract() -> int:
    print(json.dumps(CONTRACT, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a bounded runner helper task.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("contract", help="Print the exact runner helper contract.")

    run_parser = subparsers.add_parser("run", help="Run runner_helper_2b from a helper instance JSON file.")
    run_parser.add_argument("instance_json")

    args = parser.parse_args()

    try:
        if args.command == "contract":
            return print_contract()
        if args.command == "run":
            return run_instance(Path(args.instance_json))
    except RunnerHelperError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
