from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repo_paths import repo_root


ROOT = repo_root()
CONFIG_DIR = ROOT / "config"
MODEL_REGISTRY_PATH = CONFIG_DIR / "model_registry.json"
HELPER_MODEL_REGISTRY_PATH = CONFIG_DIR / "helper_model_registry.json"
LOCAL_PROVIDERS = {"ollama"}


@dataclass(frozen=True)
class HelperRuntimeProfile:
    role_id: str
    execution_backend: str
    allowed_model_keys: list[str]
    default_model_key: str
    fallback_model_key: str
    provider_requirement: str
    mapped_helpers: list[str]
    registry_path: str


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _load_model_registry() -> dict[str, dict[str, Any]]:
    registry = _load_json(MODEL_REGISTRY_PATH)
    models = registry.get("models", {})
    if not isinstance(models, dict):
        raise ValueError("model_registry.json models must be an object")
    out: dict[str, dict[str, Any]] = {}
    for key, value in models.items():
        if isinstance(key, str) and isinstance(value, dict):
            out[key] = value
    return out


def _validate_role(role_id: str, role: dict[str, Any], models: dict[str, dict[str, Any]]) -> HelperRuntimeProfile:
    execution_backend = str(role.get("execution_backend") or "").strip()
    if execution_backend not in {"scripted", "model_backed"}:
        raise ValueError(f"helper role {role_id} execution_backend must be scripted or model_backed")

    allowed_model_keys = role.get("allowed_model_keys", [])
    if not isinstance(allowed_model_keys, list) or not all(isinstance(item, str) for item in allowed_model_keys):
        raise ValueError(f"helper role {role_id} allowed_model_keys must be a list of strings")
    normalized_allowed = [item.strip() for item in allowed_model_keys if item.strip()]
    unknown_allowed = [key for key in normalized_allowed if key not in models]
    if unknown_allowed:
        raise ValueError(f"helper role {role_id} references unknown allowed_model_keys: {sorted(set(unknown_allowed))}")

    provider_requirement = str(role.get("provider_requirement") or "any").strip() or "any"
    if provider_requirement not in {"any", "local_only"}:
        raise ValueError(f"helper role {role_id} provider_requirement must be any or local_only")

    default_model_key = str(role.get("default_model_key") or "").strip()
    fallback_model_key = str(role.get("fallback_model_key") or "").strip()
    for field_name, model_key in [("default_model_key", default_model_key), ("fallback_model_key", fallback_model_key)]:
        if model_key and model_key not in models:
            raise ValueError(f"helper role {role_id} {field_name} is not in model_registry.json: {model_key}")
        if model_key and model_key not in normalized_allowed:
            raise ValueError(f"helper role {role_id} {field_name} must also appear in allowed_model_keys: {model_key}")
        if provider_requirement == "local_only" and model_key:
            provider = str(models.get(model_key, {}).get("provider") or "").strip().lower()
            if provider not in LOCAL_PROVIDERS:
                raise ValueError(f"helper role {role_id} {field_name} must use a local provider: {model_key}")

    if execution_backend == "model_backed" and not default_model_key:
        raise ValueError(f"helper role {role_id} requires default_model_key when execution_backend is model_backed")

    mapped_helpers = role.get("mapped_helpers", [])
    if not isinstance(mapped_helpers, list) or not all(isinstance(item, str) and item.strip() for item in mapped_helpers):
        raise ValueError(f"helper role {role_id} mapped_helpers must be a list of non-empty strings")

    return HelperRuntimeProfile(
        role_id=role_id,
        execution_backend=execution_backend,
        allowed_model_keys=normalized_allowed,
        default_model_key=default_model_key,
        fallback_model_key=fallback_model_key,
        provider_requirement=provider_requirement,
        mapped_helpers=[item.strip() for item in mapped_helpers],
        registry_path=str(HELPER_MODEL_REGISTRY_PATH),
    )


def load_helper_runtime_profile(role_id: str) -> HelperRuntimeProfile:
    models = _load_model_registry()
    registry = _load_json(HELPER_MODEL_REGISTRY_PATH)
    roles = registry.get("roles", {})
    if not isinstance(roles, dict):
        raise ValueError("helper_model_registry.json roles must be an object")
    role = roles.get(role_id)
    if not isinstance(role, dict):
        raise KeyError(f"No helper runtime profile for role {role_id}")
    return _validate_role(role_id, role, models)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve a helper runtime profile.")
    parser.add_argument("role_id")
    args = parser.parse_args()

    profile = load_helper_runtime_profile(args.role_id.strip())
    print(
        json.dumps(
            {
                "ok": True,
                "role_id": profile.role_id,
                "execution_backend": profile.execution_backend,
                "allowed_model_keys": profile.allowed_model_keys,
                "default_model_key": profile.default_model_key,
                "fallback_model_key": profile.fallback_model_key,
                "provider_requirement": profile.provider_requirement,
                "mapped_helpers": profile.mapped_helpers,
                "registry_path": profile.registry_path,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
