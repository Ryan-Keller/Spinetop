from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repo_paths import repo_root


ROOT = repo_root()
ORCH_SCRIPT = ROOT / "scripts" / "support_orchestration.py"
REPORT_DIR = ROOT / "logs" / "support" / "orchestration" / "stress"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class TestResult:
    name: str
    expected: str
    actual: str
    passed: bool
    detail: str = ""


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_request(payload: dict[str, Any], prefix: str) -> Path:
    path = Path(tempfile.gettempdir()) / f"{prefix}_{utc_stamp()}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def run_support(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ORCH_SCRIPT), *args],
        text=True,
        capture_output=True,
        cwd=str(ROOT),
    )


def request_ok(payload: dict[str, Any], prefix: str) -> tuple[bool, str, str]:
    req = write_request(payload, prefix)
    proc = run_support("spawn", str(req)) if payload["request_type"] == "spawn" else run_support("replace", str(req))
    stdout = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    stderr = proc.stderr.strip()
    ok = proc.returncode == 0
    return ok, stdout, stderr


def mark(helper_id: str, status: str, *, note: str = "", output_ref: str | None = None) -> tuple[bool, str, str]:
    args = ["mark", helper_id, status]
    if note:
        args.extend(["--note", note])
    if output_ref:
        args.extend(["--output-ref", output_ref])
    proc = run_support(*args)
    stdout = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    stderr = proc.stderr.strip()
    return proc.returncode == 0, stdout, stderr


def sweep() -> tuple[bool, str, str]:
    proc = run_support("sweep")
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    return proc.returncode == 0, stdout, stderr


def snapshot_targets() -> dict[str, list[str]]:
    targets = {
        "collective": ROOT / "memory" / "collective",
        "approved_dispatch": ROOT / "memory" / "dispatch" / "approved",
    }
    snapshot: dict[str, list[str]] = {}
    for name, path in targets.items():
        if path.exists():
            snapshot[name] = sorted(str(item.relative_to(ROOT)) for item in path.rglob("*") if item.is_file())
        else:
            snapshot[name] = []
    return snapshot


def make_spawn_request(helper_type: str, ttl_seconds: int, request_type: str = "spawn") -> dict[str, Any]:
    if helper_type == "retrieval_helper_2b":
        write_scope = ["logs/support/orchestration/", "logs/support/retrieval/"]
    elif helper_type == "runner_helper_2b":
        write_scope = ["logs/support/orchestration/", "logs/support/runner/"]
    else:
        write_scope = ["logs/support/orchestration/"]
    return {
        "request_type": request_type,
        "helper_type": helper_type,
        "requested_by": "stress_scout",
        "mandate_id": "stress_mandate_001",
        "task_scope": f"stress-test-{helper_type}",
        "ttl_seconds": ttl_seconds,
        "return_lane": "logs/support/orchestration/",
        "write_scope": write_scope,
    }


def main() -> int:
    results: list[TestResult] = []
    unexpected_accepts: list[str] = []
    accepted = 0
    rejected = 0
    bypass_found = False
    before = snapshot_targets()

    def record(name: str, expected: str, actual: str, passed: bool, detail: str = "") -> None:
        nonlocal accepted, rejected, bypass_found
        results.append(TestResult(name=name, expected=expected, actual=actual, passed=passed, detail=detail))
        if actual == "accepted":
            accepted += 1
        elif actual == "rejected":
            rejected += 1
        if not passed:
            bypass_found = True
            if expected == "rejected" and actual == "accepted":
                unexpected_accepts.append(name)

    # 1. normal spawn
    ok, stdout, stderr = request_ok(make_spawn_request("retrieval_helper_2b", 600), "stress_spawn_normal")
    record("normal_spawn", "accepted", "accepted" if ok else "rejected", ok, stdout or stderr)
    normal_helper = Path(stdout).stem if ok and stdout else ""

    # 2. duplicate spawn
    ok2, stdout2, stderr2 = request_ok(make_spawn_request("retrieval_helper_2b", 600), "stress_spawn_duplicate")
    record("duplicate_spawn", "accepted", "accepted" if ok2 else "rejected", ok2, stdout2 or stderr2)
    duplicate_helper = Path(stdout2).stem if ok2 and stdout2 else ""
    if normal_helper and duplicate_helper and normal_helper == duplicate_helper:
        record("duplicate_spawn_id_collision", "distinct_ids", "collision", False, "helper_id collision")
    elif normal_helper and duplicate_helper:
        record("duplicate_spawn_id_collision", "distinct_ids", "distinct_ids", True, f"{normal_helper} != {duplicate_helper}")

    # 3. burst spawn
    burst_ids: list[str] = []
    burst_ok = True
    for idx in range(8):
        helper_type = "retrieval_helper_2b" if idx % 2 == 0 else "runner_helper_2b"
        okb, outb, errb = request_ok(make_spawn_request(helper_type, 600), f"stress_burst_{idx}")
        burst_ok = burst_ok and okb
        if okb and outb:
            burst_ids.append(Path(outb).stem)
    record("burst_spawn", "accepted", "accepted" if burst_ok else "rejected", burst_ok, f"spawned {len(burst_ids)} helpers")

    # 4. invalid helper_type
    invalid_helper = make_spawn_request("not_a_helper", 600)
    ok, stdout, stderr = request_ok(invalid_helper, "stress_invalid_helper")
    record("invalid_helper_type", "rejected", "accepted" if ok else "rejected", not ok, stderr or stdout)

    # 5. invalid write_scope
    bad_scope = make_spawn_request("retrieval_helper_2b", 600)
    bad_scope["write_scope"] = ["logs/support/orchestration/", "memory/collective/"]
    req = write_request(bad_scope, "stress_invalid_scope")
    proc = run_support("spawn", str(req))
    record("invalid_write_scope", "rejected", "accepted" if proc.returncode == 0 else "rejected", proc.returncode != 0, proc.stderr.strip())

    # 6. hidden governance attempt
    bad_request_type = make_spawn_request("retrieval_helper_2b", 600, request_type="approve")
    bad_request_type["request_type"] = "approve"
    req = write_request(bad_request_type, "stress_invalid_request_type")
    proc = run_support("spawn", str(req))
    record("hidden_governance_request_type", "rejected", "accepted" if proc.returncode == 0 else "rejected", proc.returncode != 0, proc.stderr.strip())

    # 7. replacement after inconsistent_output
    ok, spawn_stdout, spawn_stderr = request_ok(make_spawn_request("runner_helper_2b", 600), "stress_replace_inconsistent_spawn")
    helper_id = Path(spawn_stdout).stem if ok and spawn_stdout else ""
    replace_req = {
        "request_type": "replace",
        "helper_type": "runner_helper_2b",
        "requested_by": "stress_scout",
        "mandate_id": "stress_mandate_001",
        "task_scope": "stress-test-runner_helper_2b",
        "ttl_seconds": 600,
        "return_lane": "logs/support/orchestration/",
        "write_scope": ["logs/support/orchestration/", "logs/support/runner/"],
        "replaces_helper_id": helper_id,
        "replacement_reason": "inconsistent_output",
    }
    req = write_request(replace_req, "stress_replace_inconsistent")
    proc = run_support("replace", str(req))
    record("replacement_after_inconsistent_output", "accepted", "accepted" if proc.returncode == 0 else "rejected", proc.returncode == 0, proc.stderr.strip() or proc.stdout.strip())
    replaced_runner_id = Path(proc.stdout.strip().splitlines()[-1]).stem if proc.returncode == 0 and proc.stdout.strip() else ""

    # 8. replacement after timeout
    timeout_spawn = make_spawn_request("retrieval_helper_2b", 1)
    ok, timeout_spawn_stdout, timeout_spawn_stderr = request_ok(timeout_spawn, "stress_timeout_spawn")
    timeout_helper_id = Path(timeout_spawn_stdout).stem if ok and timeout_spawn_stdout else ""
    time.sleep(1.4)
    sweep_ok, sweep_stdout, sweep_stderr = sweep()
    timeout_replace = {
        "request_type": "replace",
        "helper_type": "retrieval_helper_2b",
        "requested_by": "stress_scout",
        "mandate_id": "stress_mandate_001",
        "task_scope": "stress-test-retrieval_helper_2b",
        "ttl_seconds": 600,
        "return_lane": "logs/support/orchestration/",
        "write_scope": ["logs/support/orchestration/", "logs/support/retrieval/"],
        "replaces_helper_id": timeout_helper_id,
        "replacement_reason": "timeout",
    }
    req = write_request(timeout_replace, "stress_replace_timeout")
    proc = run_support("replace", str(req))
    record(
        "replacement_after_timeout",
        "accepted",
        "accepted" if proc.returncode == 0 else "rejected",
        proc.returncode == 0,
        proc.stderr.strip() or proc.stdout.strip(),
    )
    timeout_replacement_id = Path(proc.stdout.strip().splitlines()[-1]).stem if proc.returncode == 0 and proc.stdout.strip() else ""

    # 9. expired helper completion attempt
    expired_spawn = make_spawn_request("retrieval_helper_2b", 1)
    ok, expired_spawn_stdout, expired_spawn_stderr = request_ok(expired_spawn, "stress_expire_spawn")
    expired_helper_id = Path(expired_spawn_stdout).stem if ok and expired_spawn_stdout else ""
    time.sleep(1.4)
    sweep_ok2, sweep_stdout2, sweep_stderr2 = sweep()
    ok, stdout, stderr = mark(expired_helper_id, "complete", note="should be blocked")
    record("expired_helper_completion_attempt", "rejected", "accepted" if ok else "rejected", not ok, stderr or stdout)

    # 10. helper tries to write outside support lane
    outside_ok, outside_stdout, outside_stderr = mark(
        timeout_replacement_id,
        "complete",
        note="attempt forbidden output ref",
        output_ref="memory/collective/forbidden.json",
    )
    record("support_lane_boundary_on_output_ref", "rejected", "accepted" if outside_ok else "rejected", not outside_ok, outside_stderr or outside_stdout)

    after = snapshot_targets()
    if before != after:
        bypass_found = True
        record(
            "forbidden_truth_lane_mutation_check",
            "unchanged",
            "changed" if before != after else "unchanged",
            before == after,
            "truth lane snapshot changed",
        )
    else:
        record(
            "forbidden_truth_lane_mutation_check",
            "unchanged",
            "unchanged",
            True,
            "no collective/approved-dispatch file changes",
        )

    summary = {
        "total": len(results),
        "passed": sum(1 for item in results if item.passed),
        "failed": sum(1 for item in results if not item.passed),
        "accepted": accepted,
        "rejected": rejected,
        "unexpected_accepts": unexpected_accepts,
        "policy_bypass_found": bypass_found,
        "tests": [asdict(item) for item in results],
    }

    report_path = REPORT_DIR / f"stress_report_{utc_stamp()}.json"
    report_path.write_text(json.dumps(summary, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")

    print(report_path)
    return 0 if summary["failed"] == 0 and not unexpected_accepts and not bypass_found else 1


if __name__ == "__main__":
    raise SystemExit(main())
