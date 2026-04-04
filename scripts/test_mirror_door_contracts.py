from __future__ import annotations

import argparse
import copy
import json
import tempfile
import uuid
from collections import Counter
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import governance_utils
import honcho_bridge
from record_schemas import (
    build_candidate_memory_record,
    build_collective_record_from_candidate,
    build_dispatch_petition_record,
    build_governance_decision_record,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "mirror_door_contracts"
BASE_TS = "2026-04-04T12:00:00Z"
BASE_PETITION_ID = "pet_mirror_baseline"
BASE_DECISION_ID = "dec_mirror_baseline"
BASE_RECORD_ID = "mem_mirror_baseline"
BASE_SESSION_ID = "session_mirror_baseline"
CATEGORY_ORDER = ["valid", "forged", "partial", "legacy_loophole", "weather_blocked"]


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
    attack_surface: str
    source_file: Path

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


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def iter_case_files() -> Iterable[Case]:
    if not FIXTURE_ROOT.exists():
        return []
    rows: list[Case] = []
    category_dirs = [FIXTURE_ROOT / name for name in CATEGORY_ORDER if (FIXTURE_ROOT / name).is_dir()]
    category_dirs.extend(
        sorted(
            p
            for p in FIXTURE_ROOT.iterdir()
            if p.is_dir() and p.name not in CATEGORY_ORDER
        )
    )
    for category_dir in category_dirs:
        for fixture_file in sorted(category_dir.glob("*.json")):
            payload = load_json(fixture_file)
            if isinstance(payload, list):
                for idx, item in enumerate(payload):
                    if not isinstance(item, dict):
                        raise TypeError(f"{fixture_file} case {idx} must be an object")
                    rows.append(Case(category_dir.name, fixture_file, item))
            elif isinstance(payload, dict):
                rows.append(Case(category_dir.name, fixture_file, payload))
            else:
                raise TypeError(f"{fixture_file} must contain an object or list of objects")
    return rows


def apply_changes(payload: dict[str, Any], *, set_values: dict[str, Any] | None = None, remove_fields: list[str] | None = None) -> dict[str, Any]:
    out = copy.deepcopy(payload)
    for field in remove_fields or []:
        out.pop(field, None)
    for key, value in (set_values or {}).items():
        out[key] = value
    return out


def build_baseline_state() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    candidate = build_candidate_memory_record(
        source_record={
            "source": "mirror_door_contracts",
            "expert_name": "mirror-door",
            "task": "mirror door contract baseline",
        },
        source_record_ref="tests/mirror_door_contracts/valid/cases.json",
        submitted_by="mirror-door",
        source_workspace="spinetop",
        summary="mirror door contract baseline",
        key_findings=["fully governed lineage"],
        recommended_action="admit_to_collective",
        confidence=0.98,
        record_id=BASE_RECORD_ID,
        created_at=BASE_TS,
        related_petition_id=BASE_PETITION_ID,
    )

    petition = build_dispatch_petition_record(
        petition_id=BASE_PETITION_ID,
        created_by="mirror-door",
        workspace="spinetop",
        status="approved",
        petition_kind="memory_admission",
        summary="mirror door contract baseline",
        reason="mirror door contract baseline",
        evidence_refs=["evidence:mirror-door"],
        requested_action="admit_to_collective",
        risk_level="medium",
        requires_operator_approval=False,
        entry_class="normal",
        source_host="test-harness",
        base_record={
            "agent_id": "hermes-desktop",
            "task": "mirror door contract baseline",
            "summary": "mirror door contract baseline",
            "confidence": 0.5,
            "promotion_candidate": False,
            "payload_type": "pattern",
            "urgency": "normal",
            "requires_emissary": True,
            "ask_count": 1,
            "spawn_authority": "operator",
            "dispatch_mode": "normal",
            "nanny_temperature": "cool",
            "nanny_cooldown_seconds": 0,
            "governance_status": "allowed",
            "governance_reason": "dispatch permitted",
        },
    )

    decision = build_governance_decision_record(
        petition_id=BASE_PETITION_ID,
        petition_kind="memory_admission",
        decision_outcome="approve_collective",
        created_by="mirror-door",
        summary="mirror door contract baseline",
        reason="mirror door contract baseline",
        evidence_refs=["evidence:mirror-door"],
        risk_level="medium",
        requires_operator_review=False,
        decision_id=BASE_DECISION_ID,
        created_at=BASE_TS,
        review_state="final",
        related_collective_id=BASE_RECORD_ID,
        source_host="test-harness",
        legacy_compatibility=False,
    )

    collective = build_collective_record_from_candidate(
        candidate,
        governance_decision_id=BASE_DECISION_ID,
        related_petition_id=BASE_PETITION_ID,
        admitted_at=BASE_TS,
        durability_class="stable_truth",
    )
    collective.update(
        {
            "session_id": BASE_SESSION_ID,
            "agent_id": "hermes-desktop",
            "workspace": "spinetop",
            "admission_actor": "governed_admission_script",
            "governance_review_state": "approved",
            "governance_review_reason": "mirror door contract baseline",
        }
    )

    return collective, petition, decision


def build_context(case: Case) -> dict[str, Any]:
    base_record, base_petition, base_decision = build_baseline_state()

    record = apply_changes(
        base_record,
        set_values=case.payload.get("record_set"),
        remove_fields=case.payload.get("record_remove"),
    )
    petition_present = case.payload.get("petition_present", True)
    decision_present = case.payload.get("decision_present", True)
    petition = None
    decision = None
    if petition_present:
        petition = apply_changes(
            base_petition,
            set_values=case.payload.get("petition_set"),
            remove_fields=case.payload.get("petition_remove"),
        )
    if decision_present:
        decision = apply_changes(
            base_decision,
            set_values=case.payload.get("decision_set"),
            remove_fields=case.payload.get("decision_remove"),
        )

    return {
        "case_id": case.case_id,
        "record": record,
        "petition": petition,
        "decision": decision,
        "return_all": case.payload.get("return_all"),
        "nanny": case.payload.get("nanny"),
        "path": case.payload.get("path", f"memory/collective/{case.case_id}.json"),
        "expected": str(case.payload.get("expected", "correctly_blocked")),
        "attack_surface": str(case.payload.get("attack_surface", "bridge")),
    }


def stage_world(temp_root: Path, context: dict[str, Any]) -> tuple[Path, Path]:
    collective_dir = temp_root / "memory" / "collective"
    dispatch_dir = temp_root / "memory" / "dispatch"
    governance_dir = temp_root / "logs" / "governance"
    nanny_dir = temp_root / "logs" / "nanny"
    bridge_state_dir = temp_root / "logs" / "honcho_bridge"
    topology_dir = temp_root / "logs" / "topology"

    for directory in (collective_dir, dispatch_dir / "approved", dispatch_dir / "deferred", dispatch_dir / "rejected", governance_dir, nanny_dir, bridge_state_dir, topology_dir):
        directory.mkdir(parents=True, exist_ok=True)

    return_all = context.get("return_all")
    if return_all is None:
        return_all = {
            "enabled": False,
            "issued_by": "mirror-door",
            "issued_at": BASE_TS,
            "reason": "mirror door contract baseline",
            "allow_custodial_bypass": False,
        }
    nanny = context.get("nanny")
    if nanny is None:
        nanny = {
            "temperature": "cool",
            "global_cooldown_seconds": 0,
            "recommended_actions": [],
        }

    dump_json(governance_dir / "return_all.json", return_all)
    dump_json(nanny_dir / "item_world_status.json", nanny)
    dump_json(bridge_state_dir / "sent_files.json", {})
    (topology_dir / "events.jsonl").write_text("", encoding="utf-8")

    record_path = temp_root / Path(str(context["path"]))
    dump_json(record_path, context["record"])

    petition = context.get("petition")
    if petition is not None:
        petition_id = str(petition.get("petition_id") or f"{context['case_id']}_missing_petition_id")
        dump_json(dispatch_dir / "approved" / f"dispatch_{petition_id}_approved.json", petition)

    decision = context.get("decision")
    if decision is not None:
        decision_id = str(decision.get("decision_id") or f"{context['case_id']}_missing_decision_id")
        decision_status = str(decision.get("review_state") or "final")
        if str(decision.get("decision_outcome") or "") == "approve_collective":
            folder = "approved"
        elif str(decision.get("decision_outcome") or "") == "defer":
            folder = "deferred"
        elif str(decision.get("decision_outcome") or "") == "reject":
            folder = "rejected"
        else:
            folder = "approved" if decision_status == "final" else "deferred"
        dump_json(dispatch_dir / folder / f"decision_{decision_id}.json", decision)

    return temp_root, record_path


@contextmanager
def patched_bridge(temp_root: Path):
    with ExitStack() as stack:
        stack.enter_context(_patch_attr(governance_utils, "ROOT", temp_root))
        stack.enter_context(_patch_attr(governance_utils, "GOVERNANCE_DIR", temp_root / "logs" / "governance"))
        stack.enter_context(_patch_attr(governance_utils, "NANNY_STATUS_PATH", temp_root / "logs" / "nanny" / "item_world_status.json"))
        stack.enter_context(_patch_attr(governance_utils, "DISPATCH_DIR", temp_root / "memory" / "dispatch"))
        stack.enter_context(_patch_attr(honcho_bridge, "ROOT", temp_root))
        stack.enter_context(_patch_attr(honcho_bridge, "COLLECTIVE", temp_root / "memory" / "collective"))
        stack.enter_context(_patch_attr(honcho_bridge, "QUARANTINE_DIR", temp_root / "memory" / "collective" / "_quarantine"))
        stack.enter_context(_patch_attr(honcho_bridge, "STATE_DIR", temp_root / "logs" / "honcho_bridge"))
        stack.enter_context(_patch_attr(honcho_bridge, "SENT_FILE", temp_root / "logs" / "honcho_bridge" / "sent_files.json"))
        stack.enter_context(_patch_attr(honcho_bridge, "EVENT_LOG", temp_root / "logs" / "topology" / "events.jsonl"))
        stack.enter_context(_patch_attr(honcho_bridge, "api_request", _fake_api_request))
        yield


@contextmanager
def _patch_attr(module: Any, name: str, value: Any):
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


def _fake_api_request(method: str, path: str, payload: dict | None = None) -> tuple[int, str]:
    if method.upper() == "POST":
        return 201, "{\"ok\": true}"
    return 200, "{\"ok\": true}"


def _classify(expected: str, actual_allowed: bool, exception: Exception | None) -> tuple[str, str]:
    if exception is None and actual_allowed:
        actual = "validly_accepted"
        reason = "mirror opened and transport succeeded"
    elif exception is None:
        actual = "correctly_blocked"
        reason = "mirror closed"
    else:
        actual = "correctly_blocked" if expected == "correctly_blocked" else "unexpected_error"
        reason = str(exception)
    return actual, reason


def run_case(case: Case) -> CaseResult:
    context = build_context(case)
    with tempfile.TemporaryDirectory(prefix="mirror_door_contracts_") as tempdir:
        temp_root = Path(tempdir)
        _, record_path = stage_world(temp_root, context)

        exception: Exception | None = None
        actual_allowed = False
        reason = ""
        try:
            with patched_bridge(temp_root):
                gate = governance_utils.can_bridge_to_honcho(
                    context["record"],
                    return_all=governance_utils.read_return_all_state(),
                    nanny=governance_utils.read_nanny_state(),
                )
                if gate.allowed:
                    actual_allowed = True
                    honcho_bridge.send_record(record_path)
                    reason = gate.reason
                else:
                    actual_allowed = False
                    reason = gate.reason
        except Exception as exc:  # noqa: BLE001
            exception = exc
            actual_allowed = False
            reason = str(exc)

        actual, final_reason = _classify(context["expected"], actual_allowed, exception)
        if actual_allowed and exception is None:
            final_reason = reason
        elif exception is None:
            final_reason = reason
        else:
            final_reason = reason

        return CaseResult(
            category=case.category,
            case_id=case.case_id,
            expected=context["expected"],
            actual=actual,
            reason=final_reason,
            attack_surface=context["attack_surface"],
            source_file=case.source_file,
        )


def print_result(result: CaseResult, index: int) -> None:
    print(
        f"{index:02d} [{result.category}] {result.case_id} :: {result.bucket} "
        f"(expected={result.expected}, actual={result.actual}, surface={result.attack_surface})"
    )
    print(f"    reason: {result.reason}")


def print_summary(results: list[CaseResult]) -> Counter[str]:
    counts = Counter(result.bucket for result in results)
    total = len(results)
    print("== totals ==")
    print(f"total={total} correctly_blocked={counts['correctly_blocked']} validly_accepted={counts['validly_accepted']} unexpected_accept={counts['unexpected_accept']} unexpected_error={counts['unexpected_error']}")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Red-team mirror door contracts.")
    parser.add_argument("--category", action="append", dest="categories", help="Limit execution to one or more categories.")
    args = parser.parse_args()

    cases = list(iter_case_files())
    if args.categories:
        wanted = {item.strip() for item in args.categories if item.strip()}
        cases = [case for case in cases if case.category in wanted]

    if not cases:
        print("No mirror door contract fixtures found.")
        return 1

    results = [run_case(case) for case in cases]
    results.sort(key=lambda item: (CATEGORY_ORDER.index(item.category) if item.category in CATEGORY_ORDER else len(CATEGORY_ORDER), item.case_id))
    for index, result in enumerate(results, start=1):
        print_result(result, index)
    counts = print_summary(results)

    unexpected = counts["unexpected_accept"] + counts["unexpected_error"]
    if unexpected:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
