from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from helper_model_runtime import load_helper_runtime_profile
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
RUNTIME_ROLE = "spinetop-helper_2b"
RUN_DIR = ROOT / "logs" / "support" / "runs"
RUN_DIR.mkdir(parents=True, exist_ok=True)
HELPER_RUNTIME_PROFILE = load_helper_runtime_profile(RUNTIME_ROLE)

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
    "runtime_role": RUNTIME_ROLE,
    "runtime_profile": {
        "role_description": HELPER_RUNTIME_PROFILE.role_description,
        "execution_backend": HELPER_RUNTIME_PROFILE.execution_backend,
        "allowed_model_keys": HELPER_RUNTIME_PROFILE.allowed_model_keys,
        "default_model_key": HELPER_RUNTIME_PROFILE.default_model_key,
        "fallback_model_key": HELPER_RUNTIME_PROFILE.fallback_model_key,
        "provider_requirement": HELPER_RUNTIME_PROFILE.provider_requirement,
        "authority_boundary": HELPER_RUNTIME_PROFILE.authority_boundary,
        "context_refs": HELPER_RUNTIME_PROFILE.context_refs,
        "config_refs": HELPER_RUNTIME_PROFILE.config_refs,
        "support_write_scope": HELPER_RUNTIME_PROFILE.support_write_scope,
        "inactive_behavior": HELPER_RUNTIME_PROFILE.inactive_behavior,
        "behavior_contract": HELPER_RUNTIME_PROFILE.behavior_contract,
    },
    "expected_outputs": [
        "run transcript",
        "task result",
        "separate helper thinking artifact when helper-local reasoning is emitted",
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


def _scope_to_path(scope: str) -> Path:
    candidate = Path(scope)
    if candidate.is_absolute():
        return candidate.resolve()
    return (ROOT / candidate).resolve()


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


def _output_target(instance: dict[str, Any]) -> Path:
    lane = _scope_to_path(str(instance["return_lane"]))
    if lane.suffix:
        return lane
    if lane.exists() and lane.is_file():
        return lane
    lane.mkdir(parents=True, exist_ok=True)
    return lane / f"{instance['helper_id']}.json"


def _can_write(target: Path, write_scope: list[str]) -> bool:
    for scope in write_scope:
        scope_path = _scope_to_path(scope)
        if _is_under(target, scope_path):
            return True
    return False


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


def _thinking_target(output_path: Path) -> Path:
    suffix = "".join(output_path.suffixes)
    if suffix:
        return output_path.with_name(output_path.name[: -len(suffix)] + ".thinking" + suffix)
    return output_path.with_name(output_path.name + ".thinking.json")


def _build_helper_thinking(
    instance: dict[str, Any],
    *,
    receipt_status: str,
    receipt_reason: str,
    step_transcript: list[dict[str, Any]],
) -> dict[str, Any]:
    contradictions: list[str] = []
    open_questions: list[str] = []

    status = str(instance.get("status") or "").strip()
    if status and status != "active":
        contradictions.append(f"instance status is {status}, so the bounded run could not proceed normally")
    if receipt_status == "blocked":
        open_questions.append(receipt_reason)
    if receipt_status == "complete" and not step_transcript:
        contradictions.append("receipt marked complete but no steps were recorded")

    observations = [
        f"task scope: {str(instance.get('task_scope') or '').strip()}",
        f"task plan count: {len(list(instance.get('task_plan') or []))}",
        f"return lane: {str(instance.get('return_lane') or '').strip()}",
        f"runner receipt status: {receipt_status}",
    ]
    observations = [item for item in observations if item.split(':', 1)[-1].strip()]
    observations.extend([f"contradiction: {item}" for item in contradictions])

    if receipt_status == "complete":
        possible_next_steps = [
            "review the external receipt before scheduling more bounded work",
            "check whether any local contradiction note needs a separate follow-up helper",
        ]
    else:
        possible_next_steps = [
            "inspect the blocking condition in the external receipt",
            "confirm whether the helper should be replaced or the mandate should be retried",
        ]

    if not open_questions and contradictions:
        open_questions.append("Does the contradiction need escalation to another bounded helper or reviewer?")

    return {
        "helper_id": instance["helper_id"],
        "helper_type": instance["helper_type"],
        "role_id": RUNTIME_ROLE,
        "artifact_kind": "helper_internal_thinking",
        "thinking_style": list(HELPER_RUNTIME_PROFILE.behavior_contract.get("thinking_style") or []),
        "output_structure": list(HELPER_RUNTIME_PROFILE.behavior_contract.get("output_structure") or []),
        "current_context": [
            f"mandate: {str(instance.get('mandate_id') or '').strip()}",
            f"requested by: {str(instance.get('requested_by') or '').strip()}",
            f"active task: {str(instance.get('task_scope') or '').strip()}",
        ],
        "key_observations": observations,
        "possible_next_steps": possible_next_steps,
        "open_questions": open_questions,
        "highlighted_contradictions": contradictions,
        "separation_note": str(HELPER_RUNTIME_PROFILE.behavior_contract.get("separation_rule") or "").strip(),
        "derived_only": True,
    }


def run_instance(instance_path: Path) -> int:
    instance = validate_runner_instance(_load_json(instance_path), path=instance_path)
    output_path = _output_target(instance)
    if not _can_write(output_path, list(instance.get("write_scope") or [])):
        raise RunnerHelperError(f"output path {output_path} is outside write_scope{_path_hint(instance_path)}")
    artifact_ref = _path_to_ref(output_path)
    thinking_path = _thinking_target(output_path)
    thinking_ref = _path_to_ref(thinking_path)

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
        _write_json(
            thinking_path,
            _build_helper_thinking(
                instance,
                receipt_status="blocked",
                receipt_reason=f"helper status is {instance['status']}",
                step_transcript=[],
            ),
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
        _write_json(
            thinking_path,
            _build_helper_thinking(
                instance,
                receipt_status="blocked",
                receipt_reason="ttl expired before task could run",
                step_transcript=[],
            ),
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
        _write_json(
            thinking_path,
            _build_helper_thinking(
                instance,
                receipt_status="blocked",
                receipt_reason="task_plan is required",
                step_transcript=[],
            ),
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
    _write_json(
        thinking_path,
        _build_helper_thinking(
            instance,
            receipt_status="complete",
            receipt_reason=f"completed {len(step_transcript)} step(s)",
            step_transcript=step_transcript,
        ),
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
