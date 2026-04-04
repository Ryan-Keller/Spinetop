from __future__ import annotations

import argparse
import copy
import json
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import support_orchestration
import support_validation


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "support_orchestration_contracts"
CATEGORY_ORDER = ["valid", "shape", "boundary", "replacement", "lifecycle"]
BASE_REQUEST = {
    "request_type": "spawn",
    "helper_type": "retrieval_helper_2b",
    "requested_by": "stress_scout",
    "mandate_id": "support_contract_mandate_001",
    "task_scope": "bounded support orchestration stress test",
    "ttl_seconds": 600,
    "return_lane": "logs/support/orchestration/",
    "write_scope": ["logs/support/orchestration/", "logs/support/retrieval/"],
}


@dataclass(frozen=True)
class Case:
    category: str
    source_file: Path
    payload: dict[str, Any]

    @property
    def case_id(self) -> str:
        return str(self.payload.get("id") or self.source_file.stem)


@dataclass(frozen=True)
class CaseResult:
    category: str
    case_id: str
    expected: str
    actual: str
    reason: str

    @property
    def bucket(self) -> str:
        if self.actual == self.expected == "validly_accepted":
            return "validly_accepted"
        if self.actual == self.expected == "correctly_blocked":
            return "correctly_blocked"
        if self.actual == "validly_accepted":
            return "unexpected_accept"
        return "unexpected_error"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_cases() -> Iterable[Case]:
    if not FIXTURE_ROOT.exists():
        return []
    ordered_dirs = [FIXTURE_ROOT / name for name in CATEGORY_ORDER if (FIXTURE_ROOT / name).is_dir()]
    ordered_dirs.extend(
        sorted(
            path
            for path in FIXTURE_ROOT.iterdir()
            if path.is_dir() and path.name not in CATEGORY_ORDER
        )
    )
    cases: list[Case] = []
    for category_dir in ordered_dirs:
        for fixture_path in sorted(category_dir.glob("*.json")):
            payload = load_json(fixture_path)
            if isinstance(payload, list):
                for item in payload:
                    if not isinstance(item, dict):
                        raise TypeError(f"{fixture_path} contains a non-object case")
                    cases.append(Case(category_dir.name, fixture_path, item))
            elif isinstance(payload, dict):
                cases.append(Case(category_dir.name, fixture_path, payload))
            else:
                raise TypeError(f"{fixture_path} must contain an object or list of objects")
    return cases


def merge_payload(base: dict[str, Any], *, overrides: dict[str, Any] | None = None, removes: list[str] | None = None) -> dict[str, Any]:
    payload = copy.deepcopy(base)
    for field in removes or []:
        payload.pop(field, None)
    for key, value in (overrides or {}).items():
        payload[key] = value
    return payload


def _support_temp_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="support_contracts_"))
    for directory in [
        root / "logs" / "support" / "orchestration" / "requests",
        root / "logs" / "support" / "orchestration" / "instances",
        root / "logs" / "support" / "orchestration" / "artifacts",
        root / "logs" / "support" / "orchestration" / "support",
        root / "logs" / "support" / "orchestration",
        root / "logs" / "support" / "retrieval",
        root / "logs" / "support" / "runner",
        root / "memory" / "drafts",
    ]:
        directory.mkdir(parents=True, exist_ok=True)
    return root


@contextmanager
def patched_support_root(temp_root: Path):
    patches = [
        (support_validation, "ROOT", temp_root),
        (support_orchestration, "ROOT", temp_root),
        (support_orchestration, "ORCH_ROOT", temp_root / "logs" / "support" / "orchestration"),
        (support_orchestration, "REQUEST_DIR", temp_root / "logs" / "support" / "orchestration" / "requests"),
        (support_orchestration, "INSTANCE_DIR", temp_root / "logs" / "support" / "orchestration" / "instances"),
        (support_orchestration, "ARTIFACT_DIR", temp_root / "logs" / "support" / "orchestration" / "artifacts"),
        (support_orchestration, "EVENT_LOG", temp_root / "logs" / "support" / "orchestration" / "events.jsonl"),
    ]
    originals = [(module, name, getattr(module, name)) for module, name, _ in patches]
    try:
        for module, name, value in patches:
            setattr(module, name, value)
        yield
    finally:
        for module, name, value in originals:
            setattr(module, name, value)


def write_request(temp_root: Path, name: str, payload: dict[str, Any]) -> Path:
    request_dir = temp_root / "logs" / "support" / "orchestration" / "requests"
    request_dir.mkdir(parents=True, exist_ok=True)
    path = request_dir / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def spawn_request(temp_root: Path, payload: dict[str, Any], name: str) -> tuple[bool, str, str, dict[str, Any] | None]:
    path = write_request(temp_root, name, payload)
    try:
        helper, _ = support_orchestration.spawn(path)
        return True, str(path), "", helper
    except Exception as exc:  # noqa: BLE001
        return False, str(path), str(exc), None


def replace_request(temp_root: Path, payload: dict[str, Any], name: str) -> tuple[bool, str, str, dict[str, Any] | None]:
    path = write_request(temp_root, name, payload)
    try:
        helper, _ = support_orchestration.replace(path)
        return True, str(path), "", helper
    except Exception as exc:  # noqa: BLE001
        return False, str(path), str(exc), None


def mark_request(helper_id: str, status: str, *, note: str = "", output_ref: str | None = None) -> tuple[bool, str]:
    try:
        kwargs: dict[str, Any] = {"note": note}
        if output_ref:
            kwargs["outputs_refs"] = [output_ref]
        support_orchestration.mark_status(helper_id, status, **kwargs)
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def sweep_expired() -> None:
    support_orchestration.sweep_expired()


def base_request(**overrides: Any) -> dict[str, Any]:
    request = copy.deepcopy(BASE_REQUEST)
    request.update(overrides)
    return request


def run_case(case: Case) -> CaseResult:
    temp_root = _support_temp_root()
    with patched_support_root(temp_root):
        scenario = str(case.payload.get("scenario") or "spawn")
        expected = str(case.payload.get("expected") or "correctly_blocked")

        if scenario == "spawn":
            request = merge_payload(base_request(), overrides=case.payload.get("overrides"))
            ok, _, reason, helper = spawn_request(temp_root, request, case.case_id)
            actual = "validly_accepted" if ok else "correctly_blocked"
            if ok and helper is None:
                actual = "unexpected_error"
                reason = "spawn returned no helper"
            return CaseResult(case.category, case.case_id, expected, actual, reason or ("helper spawned" if ok else "spawn blocked"))

        if scenario == "duplicate_spawn":
            request = merge_payload(base_request(), overrides=case.payload.get("overrides"))
            ok1, _, reason1, helper1 = spawn_request(temp_root, request, f"{case.case_id}_one")
            ok2, _, reason2, helper2 = spawn_request(temp_root, request, f"{case.case_id}_two")
            if not ok1 or not ok2:
                reason = reason1 or reason2 or "duplicate spawn blocked"
                return CaseResult(case.category, case.case_id, expected, "correctly_blocked", reason)
            helper_id_1 = str(helper1["helper_id"]) if helper1 else ""
            helper_id_2 = str(helper2["helper_id"]) if helper2 else ""
            if not helper_id_1 or not helper_id_2:
                return CaseResult(case.category, case.case_id, expected, "unexpected_error", "duplicate spawn returned incomplete helper IDs")
            if helper_id_1 == helper_id_2:
                return CaseResult(case.category, case.case_id, expected, "unexpected_accept", f"duplicate spawn collided on helper_id {helper_id_1}")
            return CaseResult(case.category, case.case_id, expected, "validly_accepted", f"spawned distinct helpers {helper_id_1} and {helper_id_2}")

        if scenario == "replacement_after_timeout":
            spawn_payload = base_request(ttl_seconds=1)
            ok, _, reason, helper = spawn_request(temp_root, spawn_payload, f"{case.case_id}_spawn")
            if not ok or helper is None:
                return CaseResult(case.category, case.case_id, expected, "correctly_blocked", reason or "spawn blocked")
            helper_id = str(helper["helper_id"])
            time.sleep(1.2)
            sweep_expired()
            replace_payload = base_request(
                helper_type=spawn_payload["helper_type"],
                ttl_seconds=600,
                request_type="replace",
                replaces_helper_id=helper_id,
                replacement_reason="timeout",
            )
            ok2, _, reason2, replacement = replace_request(temp_root, replace_payload, f"{case.case_id}_replace")
            if ok2 and replacement is not None:
                return CaseResult(case.category, case.case_id, expected, "validly_accepted", f"{reason2 or 'replacement accepted'}; old helper {helper_id} expired then replaced")
            return CaseResult(case.category, case.case_id, expected, "correctly_blocked", reason2 or "replacement blocked")

        if scenario == "replacement_after_inconsistent_output":
            spawn_payload = base_request()
            ok, _, reason, helper = spawn_request(temp_root, spawn_payload, f"{case.case_id}_spawn")
            if not ok or helper is None:
                return CaseResult(case.category, case.case_id, expected, "correctly_blocked", reason or "spawn blocked")
            helper_id = str(helper["helper_id"])
            replace_payload = base_request(
                request_type="replace",
                replaces_helper_id=helper_id,
                replacement_reason="inconsistent_output",
            )
            ok2, _, reason2, replacement = replace_request(temp_root, replace_payload, f"{case.case_id}_replace")
            if ok2 and replacement is not None:
                return CaseResult(case.category, case.case_id, expected, "validly_accepted", f"{reason2 or 'replacement accepted'}; replaced helper {helper_id}")
            return CaseResult(case.category, case.case_id, expected, "correctly_blocked", reason2 or "replacement blocked")

        if scenario == "expired_completion":
            spawn_payload = base_request(ttl_seconds=1)
            ok, _, reason, helper = spawn_request(temp_root, spawn_payload, f"{case.case_id}_spawn")
            if not ok or helper is None:
                return CaseResult(case.category, case.case_id, expected, "correctly_blocked", reason or "spawn blocked")
            helper_id = str(helper["helper_id"])
            time.sleep(1.2)
            sweep_expired()
            ok2, reason2 = mark_request(helper_id, "complete", note="expired helper attempted completion")
            if ok2:
                return CaseResult(case.category, case.case_id, expected, "unexpected_accept", f"expired helper {helper_id} completed after expiration")
            return CaseResult(case.category, case.case_id, expected, "correctly_blocked", reason2)

        raise ValueError(f"Unsupported scenario: {scenario}")


def print_case(index: int, result: CaseResult) -> None:
    print(
        f"{index:02d} [{result.category}] {result.case_id} :: {result.bucket} "
        f"(expected={result.expected}, actual={result.actual})"
    )
    print(f"    reason: {result.reason}")


def summarize(results: list[CaseResult]) -> Counter[str]:
    counts = Counter(result.bucket for result in results)
    total = len(results)
    print("== totals ==")
    print(
        f"total={total} correctly_blocked={counts['correctly_blocked']} "
        f"validly_accepted={counts['validly_accepted']} unexpected_accept={counts['unexpected_accept']} "
        f"unexpected_error={counts['unexpected_error']}"
    )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Red-team the bounded support orchestration layer.")
    parser.add_argument("--category", action="append", dest="categories", help="Limit execution to specific categories.")
    args = parser.parse_args()

    cases = list(iter_cases())
    if args.categories:
        wanted = {item.strip() for item in args.categories if item.strip()}
        cases = [case for case in cases if case.category in wanted]

    if not cases:
        print("No support contract fixtures found.")
        return 1

    results = [run_case(case) for case in cases]
    results.sort(
        key=lambda item: (
            CATEGORY_ORDER.index(item.category) if item.category in CATEGORY_ORDER else len(CATEGORY_ORDER),
            item.case_id,
        )
    )

    for index, result in enumerate(results, start=1):
        print_case(index, result)

    counts = summarize(results)
    return 0 if counts["unexpected_accept"] == 0 and counts["unexpected_error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
