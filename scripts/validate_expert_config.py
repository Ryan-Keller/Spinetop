from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from record_schemas import normalize_dispatch_petition_record
from repo_paths import repo_root


ROOT = repo_root()
REGISTRY = ROOT / "config" / "model_registry.json"
POLICY = ROOT / "config" / "expert_model_policy.json"
EXPERTS_DIR = ROOT / "experts"
SPINELAB_EXPERTS_DIR = ROOT.parent / "Spinelab" / "experts"
RETURN_ALL_PATH = ROOT / "logs" / "governance" / "return_all.json"
DISPATCH_DIR = ROOT / "memory" / "dispatch"
RESUME_QUEUE_PATH = ROOT / "logs" / "custodial" / "resume_queue.json"
LAST_KNOWN_ROLE_PATH = ROOT / "logs" / "custodial" / "last_known_role.json"

REQUIRED_EXPERT_FIELDS = [
    "expert_id",
    "display_name",
    "role",
    "workspace",
    "lane",
    "allowed_actions",
    "forbidden_actions",
    "default_model_key",
    "escalation_model_key",
]

def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def try_load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = load_json(path)
        if not isinstance(payload, dict):
            return None, "root value is not an object"
        return payload, None
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"invalid json: {exc}"
    except OSError as exc:
        return None, f"io error: {exc}"


def gather_experts() -> list[Path]:
    files: list[Path] = []
    if EXPERTS_DIR.exists():
        files.extend(sorted(EXPERTS_DIR.glob("*.json")))
    if SPINELAB_EXPERTS_DIR.exists():
        files.extend(sorted(SPINELAB_EXPERTS_DIR.glob("*.json")))
    return files


def validate_expert(expert: dict[str, Any], models: set[str], policy: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for field in REQUIRED_EXPERT_FIELDS:
        if field not in expert:
            issues.append(f"missing field: {field}")

    expert_id = str(expert.get("expert_id") or "")
    default_key = str(expert.get("default_model_key") or "")
    escalation_key = str(expert.get("escalation_model_key") or "")
    if default_key and default_key not in models:
        issues.append(f"default_model_key not in registry: {default_key}")
    if escalation_key and escalation_key not in models:
        issues.append(f"escalation_model_key not in registry: {escalation_key}")

    policy_entry = policy.get("experts", {}).get(expert_id)
    if not policy_entry:
        issues.append("no policy entry for expert_id")
        return issues

    allowed_models = policy_entry.get("allowed_models", [])
    if not isinstance(allowed_models, list):
        issues.append("policy allowed_models is not a list")
    else:
        missing = [model for model in allowed_models if model not in models]
        if missing:
            issues.append(f"allowed_models missing in registry: {missing}")

    lane = policy_entry.get("lane")
    if lane and expert.get("lane") != lane:
        issues.append(f"lane mismatch policy={lane} expert={expert.get('lane')}")
    return issues


def validate_governance() -> list[str]:
    payload, error = try_load_json(RETURN_ALL_PATH)
    if error == "missing":
        return []
    if error:
        return [f"return_all.json {error}"]

    issues: list[str] = []
    required = {"ok", "enabled", "issued_by", "issued_at", "reason", "allow_custodial_bypass"}
    missing = sorted(required - set(payload or {}))
    if missing:
        issues.append(f"return_all.json missing fields: {missing}")
    if payload and not isinstance(payload.get("enabled"), bool):
        issues.append("return_all.json enabled must be boolean")
    if payload and not isinstance(payload.get("allow_custodial_bypass"), bool):
        issues.append("return_all.json allow_custodial_bypass must be boolean")
    return issues


def validate_dispatch() -> list[str]:
    issues: list[str] = []
    seen: dict[str, list[str]] = defaultdict(list)

    if not DISPATCH_DIR.exists():
        return []

    for folder in sorted(DISPATCH_DIR.iterdir()):
        if not folder.exists():
            continue
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            payload, error = try_load_json(path)
            if error:
                issues.append(f"{folder.name}/{path.name}: {error}")
                continue
            assert payload is not None
            try:
                normalized = normalize_dispatch_petition_record(payload, path=path, legacy_ok=True)
            except Exception as exc:
                issues.append(f"{folder.name}/{path.name}: {exc}")
                continue
            petition_id = str(normalized.get("petition_id") or f"legacy:{path.name}")
            seen[petition_id].append(f"{folder.name}/{path.name}")

    for petition_id, locations in sorted(seen.items()):
        if len(locations) > 1:
            issues.append(f"duplicate canonical petition_id {petition_id}: {locations}")

    return issues


def validate_custodial_files() -> list[str]:
    issues: list[str] = []

    queue_payload, queue_error = try_load_json(RESUME_QUEUE_PATH)
    if queue_error not in {None, "missing"}:
        issues.append(f"resume_queue.json {queue_error}")
    elif queue_payload:
        actions = queue_payload.get("actions")
        if actions is None:
            action = queue_payload.get("action")
            if action is not None and not isinstance(action, dict):
                issues.append("resume_queue.json action must be an object")
        elif not isinstance(actions, list):
            issues.append("resume_queue.json actions must be a list")
        else:
            for index, action in enumerate(actions):
                if not isinstance(action, dict):
                    issues.append(f"resume_queue.json actions[{index}] must be an object")

    role_payload, role_error = try_load_json(LAST_KNOWN_ROLE_PATH)
    if role_error not in {None, "missing"}:
        issues.append(f"last_known_role.json {role_error}")
    elif role_payload:
        if "role" in role_payload and not isinstance(role_payload.get("role"), str):
            issues.append("last_known_role.json role must be a string")
        if "lane" in role_payload and not isinstance(role_payload.get("lane"), str):
            issues.append("last_known_role.json lane must be a string")

    return issues


def main() -> int:
    failures = 0
    sections: list[tuple[str, list[str]]] = []

    registry = load_json(REGISTRY)
    policy = load_json(POLICY)
    models = set(registry.get("models", {}).keys())

    expert_issues: list[str] = []
    experts = gather_experts()
    for path in experts:
        payload, error = try_load_json(path)
        if error:
            expert_issues.append(f"{path.name}: {error}")
            continue
        assert payload is not None
        issues = validate_expert(payload, models, policy)
        if issues:
            expert_issues.append(f"{payload.get('expert_id', path.stem)}: " + "; ".join(issues))
    sections.append(("Expert / model", expert_issues))
    sections.append(("Governance", validate_governance()))
    sections.append(("Dispatch", validate_dispatch()))
    sections.append(("Custodial", validate_custodial_files()))

    print("Spine configuration validation\n")
    for title, issues in sections:
        if issues:
            failures += len(issues)
            print(f"[FAIL] {title}")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print(f"[OK] {title}")
        print("")

    print(f"Summary: {failures} issue(s)")
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
