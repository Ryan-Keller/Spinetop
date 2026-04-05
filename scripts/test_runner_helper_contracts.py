from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

import runner_helper
import support_orchestration
import support_validation


ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _support_temp_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="runner_helper_contracts_"))
    for directory in [
        root / "logs" / "support" / "orchestration" / "requests",
        root / "logs" / "support" / "orchestration" / "instances",
        root / "logs" / "support" / "orchestration" / "artifacts",
        root / "logs" / "support" / "runs",
        root / "memory" / "drafts",
    ]:
        directory.mkdir(parents=True, exist_ok=True)
    return root


@contextmanager
def patched_support_root(temp_root: Path):
    orch_root = temp_root / "logs" / "support" / "orchestration"
    run_root = temp_root / "logs" / "support" / "runs"
    patches = [
        (support_validation, "ROOT", temp_root),
        (support_orchestration, "ROOT", temp_root),
        (support_orchestration, "ORCH_ROOT", orch_root),
        (support_orchestration, "REQUEST_DIR", orch_root / "requests"),
        (support_orchestration, "INSTANCE_DIR", orch_root / "instances"),
        (support_orchestration, "ARTIFACT_DIR", orch_root / "artifacts"),
        (support_orchestration, "EVENT_LOG", orch_root / "events.jsonl"),
        (runner_helper, "ROOT", temp_root),
        (runner_helper, "RUN_DIR", run_root),
    ]
    originals = [(module, name, getattr(module, name)) for module, name, _ in patches]
    try:
        for module, name, value in patches:
            setattr(module, name, value)
        yield
    finally:
        for module, name, value in originals:
            setattr(module, name, value)


def _spawn_request(return_lane: str, write_scope: list[str]) -> dict[str, object]:
    return {
        "request_type": "spawn",
        "helper_type": "runner_helper_2b",
        "requested_by": "contract_test",
        "mandate_id": "runner_contract_mandate_001",
        "task_scope": "runner helper contract check",
        "ttl_seconds": 600,
        "return_lane": return_lane,
        "write_scope": write_scope,
        "task_plan": ["step one", "step two"],
    }


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _run_case(temp_root: Path, *, case_name: str, return_lane: str, write_scope: list[str]) -> None:
    request_path = temp_root / "logs" / "support" / "orchestration" / "requests" / f"{case_name}.json"
    _write_json(request_path, _spawn_request(return_lane, write_scope))

    helper, instance_path = support_orchestration.spawn(request_path)
    rc = runner_helper.run_instance(instance_path)
    _assert(rc == 0, f"{case_name}: runner_helper.run_instance returned {rc}")

    expected_output = (
        temp_root / return_lane / f"{helper['helper_id']}.json"
        if not Path(return_lane).suffix
        else temp_root / return_lane
    )
    _assert(expected_output.exists(), f"{case_name}: expected output not found at {expected_output}")

    payload = json.loads(expected_output.read_text(encoding="utf-8"))
    _assert(payload.get("helper_id") == helper["helper_id"], f"{case_name}: helper_id mismatch")
    _assert(payload.get("return_lane") == return_lane, f"{case_name}: return_lane mismatch")
    thinking_path = expected_output.with_name(f"{expected_output.stem}.thinking{expected_output.suffix}")
    _assert(thinking_path.exists(), f"{case_name}: expected internal thinking artifact not found at {thinking_path}")
    thinking_payload = json.loads(thinking_path.read_text(encoding="utf-8"))
    _assert(thinking_payload.get("artifact_kind") == "helper_internal_thinking", f"{case_name}: thinking artifact kind mismatch")
    _assert(
        thinking_payload.get("output_structure") == [
            "current context",
            "key observations",
            "possible next steps",
            "open questions",
        ],
        f"{case_name}: thinking artifact output structure mismatch",
    )
    _assert(
        thinking_payload.get("highlighted_contradictions") == [],
        f"{case_name}: complete run should not invent contradictions",
    )

    event_log = temp_root / "logs" / "support" / "orchestration" / "events.jsonl"
    lines = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    complete_events = [line for line in lines if line.get("helper_id") == helper["helper_id"] and line.get("event_type") == "complete"]
    _assert(complete_events, f"{case_name}: missing complete event")
    _assert(
        complete_events[-1].get("outputs_refs") == [expected_output.relative_to(temp_root).as_posix()],
        f"{case_name}: outputs_refs did not point at return artifact",
    )


def main() -> int:
    temp_root = _support_temp_root()
    with patched_support_root(temp_root):
        _run_case(
            temp_root,
            case_name="orchestration_lane",
            return_lane="logs/support/orchestration/",
            write_scope=["logs/support/orchestration/"],
        )
        _run_case(
            temp_root,
            case_name="mission_local_draft_lane",
            return_lane="memory/drafts/",
            write_scope=["logs/support/orchestration/", "memory/drafts/"],
        )
    print("runner_helper_contracts_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
