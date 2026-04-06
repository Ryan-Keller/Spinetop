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
HELPER_REGISTRY = ROOT / "config" / "helper_model_registry.json"
HERMES_PROFILE_REGISTRY = ROOT / "config" / "hermes_profile_registry.json"
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


def validate_helper_models(models: set[str]) -> list[str]:
    payload, error = try_load_json(HELPER_REGISTRY)
    if error:
        return [f"helper_model_registry.json {error}"]

    assert payload is not None
    roles = payload.get("roles")
    if not isinstance(roles, dict):
        return ["helper_model_registry.json roles must be an object"]

    issues: list[str] = []
    for role_id, role in sorted(roles.items()):
        if not isinstance(role_id, str) or not role_id.strip():
            issues.append("helper_model_registry.json contains a blank role id")
            continue
        if not isinstance(role, dict):
            issues.append(f"helper role {role_id} must be an object")
            continue

        execution_backend = str(role.get("execution_backend") or "").strip()
        if execution_backend not in {"scripted", "model_backed"}:
            issues.append(f"helper role {role_id} execution_backend must be scripted or model_backed")

        role_description = str(role.get("role_description") or "").strip()
        if not role_description:
            issues.append(f"helper role {role_id} role_description must be a non-empty string")

        if "active" not in role or not isinstance(role.get("active"), bool):
            issues.append(f"helper role {role_id} active must be a boolean")

        allowed_model_keys = role.get("allowed_model_keys", [])
        if not isinstance(allowed_model_keys, list) or not all(isinstance(item, str) for item in allowed_model_keys):
            issues.append(f"helper role {role_id} allowed_model_keys must be a list of strings")
            allowed_model_keys = []
        normalized_allowed = [item.strip() for item in allowed_model_keys if isinstance(item, str) and item.strip()]
        missing_allowed = [key for key in normalized_allowed if key not in models]
        if missing_allowed:
            issues.append(f"helper role {role_id} allowed_model_keys missing in registry: {sorted(set(missing_allowed))}")

        provider_requirement = str(role.get("provider_requirement") or "any").strip() or "any"
        if provider_requirement not in {"any", "local_only"}:
            issues.append(f"helper role {role_id} provider_requirement must be any or local_only")

        for field_name in ("default_model_key", "fallback_model_key"):
            model_key = str(role.get(field_name) or "").strip()
            if model_key and model_key not in models:
                issues.append(f"helper role {role_id} {field_name} not in registry: {model_key}")
            if model_key and model_key not in normalized_allowed:
                issues.append(f"helper role {role_id} {field_name} must also appear in allowed_model_keys: {model_key}")
        if execution_backend == "model_backed" and not str(role.get("default_model_key") or "").strip():
            issues.append(f"helper role {role_id} requires default_model_key when execution_backend is model_backed")

        mapped_helpers = role.get("mapped_helpers", [])
        if not isinstance(mapped_helpers, list) or not all(isinstance(item, str) and item.strip() for item in mapped_helpers):
            issues.append(f"helper role {role_id} mapped_helpers must be a list of non-empty strings")

        for field_name in ("context_refs", "config_refs", "support_write_scope"):
            value = role.get(field_name, [])
            if value is None:
                value = []
            if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
                issues.append(f"helper role {role_id} {field_name} must be a list of non-empty strings")

        inactive_behavior = str(role.get("inactive_behavior") or "disabled_safe").strip() or "disabled_safe"
        if inactive_behavior != "disabled_safe":
            issues.append(f"helper role {role_id} inactive_behavior must be disabled_safe")

        authority_boundary = role.get("authority_boundary")
        if authority_boundary is not None:
            if not isinstance(authority_boundary, dict):
                issues.append(f"helper role {role_id} authority_boundary must be an object")
            else:
                for field_name in ("may_read", "may_write_only", "may_not"):
                    value = authority_boundary.get(field_name, [])
                    if value is None:
                        value = []
                    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
                        issues.append(
                            f"helper role {role_id} authority_boundary.{field_name} must be a list of non-empty strings"
                        )
                for field_name in ("derived_outputs_only", "returns_must_remain_structured"):
                    value = authority_boundary.get(field_name)
                    if value is not None and not isinstance(value, bool):
                        issues.append(f"helper role {role_id} authority_boundary.{field_name} must be boolean")

    return issues


def validate_hermes_profiles() -> list[str]:
    payload, error = try_load_json(HERMES_PROFILE_REGISTRY)
    if error:
        return [f"hermes_profile_registry.json {error}"]

    assert payload is not None
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        return ["hermes_profile_registry.json profiles must be an array"]

    issues: list[str] = []
    seen_names: set[str] = set()
    seen_homes: set[str] = set()
    seen_memories: set[str] = set()
    required_profiles = {
        "spinetop-sentinel",
        "spinetop-expeditioner",
        "spinetop-helper-2b",
        "spinetop-mirror",
    }

    for profile in profiles:
        if not isinstance(profile, dict):
            issues.append("hermes_profile_registry.json profile entries must be objects")
            continue
        name = str(profile.get("profile_name") or "").strip()
        if not name:
            issues.append("hermes_profile_registry.json profile_name must be non-empty")
            continue
        if name in seen_names:
            issues.append(f"hermes_profile_registry.json duplicate profile_name: {name}")
        seen_names.add(name)

        for field in ("template_root", "runtime_home", "memory_root", "soul_path"):
            value = str(profile.get(field) or "").strip()
            if not value:
                issues.append(f"hermes profile {name} missing {field}")
                continue
            if field == "template_root" and not (ROOT / value).exists():
                issues.append(f"hermes profile {name} template_root missing: {value}")
            if field == "soul_path" and not (ROOT / value).exists():
                issues.append(f"hermes profile {name} soul_path missing: {value}")
            if field == "runtime_home":
                if value in seen_homes:
                    issues.append(f"hermes profile {name} reuses runtime_home: {value}")
                seen_homes.add(value)
            if field == "memory_root":
                if value in seen_memories:
                    issues.append(f"hermes profile {name} reuses memory_root: {value}")
                seen_memories.add(value)

        activation = profile.get("activation")
        if not isinstance(activation, dict):
            issues.append(f"hermes profile {name} activation must be an object")
        else:
            default_state = str(activation.get("default_state") or "").strip()
            if default_state not in {"active", "inactive"}:
                issues.append(f"hermes profile {name} activation.default_state must be active or inactive")
            control_ref = str(activation.get("control_ref") or "").strip()
            if not control_ref:
                issues.append(f"hermes profile {name} activation.control_ref missing")

        separation = profile.get("separation")
        if not isinstance(separation, dict):
            issues.append(f"hermes profile {name} separation must be an object")
        else:
            for field in ("shared_identity_allowed", "shared_memory_allowed", "shared_runtime_home_allowed"):
                if separation.get(field) is not False:
                    issues.append(f"hermes profile {name} separation.{field} must be false")

    missing = sorted(required_profiles - seen_names)
    if missing:
        issues.append(f"hermes_profile_registry.json missing required profiles: {missing}")

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
    sections.append(("Helper models", validate_helper_models(models)))
    sections.append(("Hermes profiles", validate_hermes_profiles()))
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
