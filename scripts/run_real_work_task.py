from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_clarification_packet import build_clarification_packet, write_clarification_packet
import hermes_to_petition
import review_and_submit_petition
import run_hermes_v1 as hermes_runner
from load_expert_policy import load_runtime_policy
from repo_paths import repo_root
from state_machine import advance_state, normalize_mission_id, upsert_artifact_index_entry, write_mission_brief
from validate_clarification_packet import validate_clarification_packet


ROOT = repo_root()
EXPERT_ID = "hermes-spinetop"
RUNS_DIR = ROOT / "logs" / "hermes" / "runs"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_digest(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6]


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _path_hint(path: Path | None) -> str:
    return f" ({path})" if path else ""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing file{_path_hint(path)}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Malformed JSON{_path_hint(path)}: {exc}") from exc


def _format_command(draft_path: Path) -> str:
    return f"python scripts/review_and_submit_petition.py review {draft_path.as_posix()}"


def load_task_text(task_text: str | None, task_file: Path | None) -> tuple[str, str]:
    if task_file is not None:
        if task_text is not None and task_text.strip():
            raise RuntimeError("use either task or --task-file, not both")
        path = task_file.expanduser()
        if not path.exists():
            raise RuntimeError(f"Missing task file: {path}")
        if not path.is_file():
            raise RuntimeError(f"Task file must be a file: {path}")
        text = path.read_text(encoding="utf-8-sig").strip()
        if not text:
            raise RuntimeError(f"Task file is empty: {path}")
        return text, str(path)

    if task_text is None:
        raise RuntimeError("task or --task-file is required")

    text = task_text.strip()
    if not text:
        raise RuntimeError("task must not be empty")
    return text, "inline"


def resolve_mission_id(provided_mission_id: str | None, task_text: str, mode: str) -> str:
    if provided_mission_id:
        return normalize_mission_id(provided_mission_id)
    stamp = utc_stamp()
    seed = f"{task_text}|{mode}|{stamp}"
    return normalize_mission_id(f"mission_{stamp}_{_short_digest(seed)}")


def _task_requires_clarification(task_text: str, hermes_result: dict[str, Any]) -> bool:
    task_lower = f" {task_text.strip().lower()} "
    personal_or_open = (
        " my " in task_lower
        or " this " in task_lower
        or task_lower.strip().startswith("my ")
        or task_lower.strip().startswith("this ")
        or task_lower.strip().startswith("how ")
        or task_lower.strip().startswith("what ")
        or task_lower.strip().startswith("why ")
        or task_lower.strip().startswith("can you ")
        or task_lower.strip().startswith("could you ")
        or task_lower.strip().startswith("should i ")
        or task_lower.strip().startswith("please ")
        or task_lower.strip().startswith("review ")
        or task_lower.strip().startswith("analyze ")
        or task_lower.strip().startswith("analyse ")
        or task_lower.strip().startswith("assess ")
        or task_lower.strip().startswith("suggest ")
        or task_lower.strip().startswith("teach ")
        or task_lower.strip().startswith("help ")
        or task_lower.strip().startswith("explain ")
    )
    trigger_state = (
        str(hermes_result.get("recommended_action") or "").strip() == "defer"
        or hermes_result.get("petition_kind") is None
        or str(hermes_result.get("status") or "").strip() == "summary_only"
    )
    return bool(personal_or_open and trigger_state)


def run_task(
    mode: str,
    task: str | None,
    task_file: Path | None,
    mission_id: str | None,
    onboarding_model_key: str | None,
    skip_draft: bool,
    explain: bool,
    packet_only: bool,
) -> int:
    task_text, task_source = load_task_text(task, task_file)
    emit_draft_preview = not packet_only and not skip_draft
    mission_id = resolve_mission_id(mission_id, task_text, mode)

    runtime_policy = load_runtime_policy(EXPERT_ID)
    runtime_config = hermes_runner.load_hermes_runtime_config()
    models = hermes_runner.load_model_registry()
    lifecycle = hermes_runner.load_model_lifecycle(runtime_config)
    hermes_runner.validate_model_lifecycle(runtime_policy, models, lifecycle)

    model_key = hermes_runner.resolve_runtime_model_key(
        runtime_policy,
        runtime_config,
        None,
        onboarding_model_key,
    )
    model_cfg = models.get(model_key, {})
    if not isinstance(model_cfg, dict):
        raise RuntimeError(f"Invalid model config for {model_key}")

    live_snapshot = hermes_runner.build_snapshot()
    snapshot = hermes_runner.merge_snapshot(live_snapshot, {"subject": task_text})
    run_id = str(snapshot.get("run_id") or live_snapshot["run_id"])
    advance_state(mission_id, "CITADEL_ACTIVE")
    write_mission_brief(mission_id, task_text, mode, run_id)
    prompt = hermes_runner.build_prompt(mode, snapshot, run_id)

    raw_response = hermes_runner.invoke_model(model_key, prompt, runtime_config)
    candidate = hermes_runner.extract_json_candidate(raw_response)
    if candidate is None:
        raise RuntimeError("Hermes response did not contain a JSON object")

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Hermes response is not valid JSON: {exc}") from exc

    ok, reason = hermes_runner.validate_response_object(parsed, run_id, mode)
    if not ok:
        raise RuntimeError(f"Hermes response validation failed: {reason}")

    run_record = hermes_runner.normalize_response_object(parsed)
    run_record_path = RUNS_DIR / f"{run_id}_{mode}.json"
    write_json(run_record_path, run_record)
    upsert_artifact_index_entry(mission_id, "hermes_run", run_record_path, created_at=iso_now())

    clarification_path: Path | None = None
    clarification_packet: dict[str, Any] | None = None
    draft_path: Path | None = None
    preview: dict[str, Any] | None = None
    draft: dict[str, Any] | None = None
    validated_run = hermes_to_petition.validate_hermes_run(run_record)
    if emit_draft_preview:
        draft = hermes_to_petition.build_draft(validated_run)

    clarification_triggered = _task_requires_clarification(task_text, run_record)
    next_state = "PACKAGE_READY"
    if clarification_triggered:
        next_state = "CLARIFICATION_NEEDED"
    elif emit_draft_preview and draft is not None:
        next_state = "RELEASE_REQUESTED"
    advance_state(mission_id, next_state)

    if clarification_triggered:
        packet = build_clarification_packet(task_text, run_record)
        clarification_packet = validate_clarification_packet(packet)
        clarification_path = write_clarification_packet(clarification_packet)
        upsert_artifact_index_entry(mission_id, "clarification_packet", clarification_path, created_at=clarification_packet["created_at"])

    if emit_draft_preview and draft is not None:
        validated_draft = review_and_submit_petition.validate_draft_petition(draft)
        draft_path = hermes_to_petition.write_draft(validated_draft)
        upsert_artifact_index_entry(mission_id, "draft", draft_path, created_at=iso_now())
        preview = review_and_submit_petition.build_review_payload(
            validated_draft,
            draft_path=draft_path,
            return_all=review_and_submit_petition.read_return_all_state(),
            nanny=review_and_submit_petition.read_nanny_state(),
        )

    print("=== TASK ===")
    print(f"task_source={task_source}")
    print(f"mission_id={mission_id}")
    if packet_only:
        print("packet_only=True")
    print(f"task={task_text}")
    print(f"mode={mode}")
    print(f"model_key={model_key}")
    print(f"model={str(model_cfg.get('model') or 'unknown')}")
    print("")

    print("=== HERMES RESULT ===")
    print(f"run_id={run_record.get('run_id')}")
    print(f"status={run_record.get('status')}")
    print(f"recommended_action={run_record.get('recommended_action')}")
    print(f"petition_kind={run_record.get('petition_kind')}")
    print(f"confidence={run_record.get('confidence')}")
    print(f"artifact={run_record_path.as_posix()}")
    print("")

    if emit_draft_preview or skip_draft:
        print("=== DRAFT ===")
        if draft_path is None:
            if skip_draft:
                print("created=no")
                print("reason=skip_draft flag set")
                print("next_step=none")
            else:
                print("created=no")
                print("reason=Hermes result did not require a draft")
                print("next_step=none")
        else:
            print("created=yes")
            print(f"draft_path={draft_path.as_posix()}")
            print("")
            print("=== DISPATCH PREVIEW ===")
            print(f"submission_allowed={bool(preview and preview.get('submission_allowed'))}")
            if preview:
                gate = preview.get("submission_gate") or {}
                print(f"submission_gate_status={gate.get('status')}")
                print(f"submission_gate_reason={gate.get('reason')}")
                print(f"dispatch_path={preview.get('dispatch_path')}")
            print(f"review_command={_format_command(draft_path)}")

    if clarification_path is not None and clarification_packet is not None:
        print("")
        print("=== CLARIFICATION REASONING ===")
        print(f"packet_path={clarification_path.as_posix()}")
        print(f"status={clarification_packet.get('status')}")
        if explain:
            print(json.dumps(clarification_packet, indent=2, ensure_ascii=False))
    elif packet_only:
        print("")
        print("=== CLARIFICATION REASONING ===")
        print("packet_path=none")
        print("status=not_created")
        print("reason=clarification trigger did not fire")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one manual Hermes work task through draft and dispatch preview.")
    parser.add_argument("mode", choices=sorted(hermes_runner.ALLOWED_MODES), help="Hermes mode to run.")
    parser.add_argument(
        "task",
        nargs="?",
        help="Short task description, for example: review recent anomalies and suggest action.",
    )
    parser.add_argument(
        "--task-file",
        type=Path,
        help="Read task text from a UTF-8 text file instead of typing a long shell-quoted string.",
    )
    parser.add_argument(
        "--mission-id",
        help="Reuse an existing mission container instead of creating a new one at task start.",
    )
    parser.add_argument(
        "--onboarding-model-key",
        help="Run a specific onboarding candidate instead of the production default.",
    )
    parser.add_argument(
        "--skip-draft",
        action="store_true",
        help="Stop after the validated Hermes run artifact and do not create a draft.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Pretty-print the clarification reasoning packet when one is created.",
    )
    parser.add_argument(
        "--packet-only",
        action="store_true",
        help="Skip draft and dispatch preview output and only produce the clarification packet view.",
    )
    args = parser.parse_args()

    try:
        return run_task(
            mode=args.mode,
            task=args.task,
            task_file=args.task_file,
            mission_id=args.mission_id,
            onboarding_model_key=args.onboarding_model_key,
            skip_draft=args.skip_draft,
            explain=args.explain,
            packet_only=args.packet_only,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
