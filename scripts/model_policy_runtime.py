from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repo_paths import repo_root


ROOT = repo_root()
CONFIG_DIR = ROOT / "config"
EXPERTS_DIR = ROOT / "experts"
SPINELAB_EXPERTS_DIR = ROOT.parent / "Spinelab" / "experts"


@dataclass(frozen=True)
class RuntimeModelPolicy:
    expert_id: str
    allowed_model_keys: list[str]
    default_model_key: str
    escalation_model_key: str
    registry_keys: list[str]
    expert_file: str


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _resolve_expert_file(expert_id: str) -> Path:
    filename = expert_id.replace("-", "_") + ".json"
    for directory in (EXPERTS_DIR, SPINELAB_EXPERTS_DIR):
        candidate = directory / filename
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Expert file not found for {expert_id}")


def load_runtime_policy(expert_id: str) -> RuntimeModelPolicy:
    registry = _load_json(CONFIG_DIR / "model_registry.json")
    policy = _load_json(CONFIG_DIR / "expert_model_policy.json")
    expert_file = _resolve_expert_file(expert_id)
    expert = _load_json(expert_file)

    registry_models = registry.get("models", {})
    if not isinstance(registry_models, dict):
        raise ValueError("model_registry.json models must be an object")
    registry_keys = sorted(registry_models.keys())

    expert_policy = policy.get("experts", {}).get(expert_id)
    if not isinstance(expert_policy, dict):
        raise KeyError(f"No policy entry for {expert_id}")

    allowed_models = expert_policy.get("allowed_models", [])
    if not isinstance(allowed_models, list) or not all(isinstance(item, str) for item in allowed_models):
        raise ValueError(f"Policy allowed_models must be a list for {expert_id}")

    default_model_key = str(expert_policy.get("default_model") or "").strip()
    escalation_model_key = str(expert_policy.get("escalation_model") or "").strip()
    if not default_model_key:
        raise ValueError(f"Policy default_model missing for {expert_id}")
    if not escalation_model_key:
        raise ValueError(f"Policy escalation_model missing for {expert_id}")

    missing = [key for key in allowed_models + [default_model_key, escalation_model_key] if key not in registry_models]
    if missing:
        raise ValueError(f"Unknown model key(s) for {expert_id}: {sorted(set(missing))}")

    if default_model_key not in allowed_models:
        raise ValueError(f"default_model {default_model_key} is not allowed for {expert_id}")
    if escalation_model_key not in allowed_models:
        raise ValueError(f"escalation_model {escalation_model_key} is not allowed for {expert_id}")

    expert_default = str(expert.get("default_model_key") or "").strip()
    expert_escalation = str(expert.get("escalation_model_key") or "").strip()
    if expert_default and expert_default not in allowed_models:
        raise ValueError(f"Expert default_model_key {expert_default} is not allowed for {expert_id}")
    if expert_escalation and expert_escalation not in allowed_models:
        raise ValueError(f"Expert escalation_model_key {expert_escalation} is not allowed for {expert_id}")

    if expert_default and expert_default != default_model_key:
        raise ValueError(
            f"Expert default_model_key {expert_default} does not match policy default_model {default_model_key} for {expert_id}"
        )
    if expert_escalation and expert_escalation != escalation_model_key:
        raise ValueError(
            f"Expert escalation_model_key {expert_escalation} does not match policy escalation_model {escalation_model_key} for {expert_id}"
        )

    return RuntimeModelPolicy(
        expert_id=str(expert.get("expert_id") or expert_id),
        allowed_model_keys=list(allowed_models),
        default_model_key=default_model_key,
        escalation_model_key=escalation_model_key,
        registry_keys=registry_keys,
        expert_file=str(expert_file),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve an expert's runtime model policy.")
    parser.add_argument("expert_id")
    args = parser.parse_args()

    policy = load_runtime_policy(args.expert_id.strip())
    print(
        json.dumps(
            {
                "ok": True,
                "expert_id": policy.expert_id,
                "expert_file": policy.expert_file,
                "allowed_model_keys": policy.allowed_model_keys,
                "default_model_key": policy.default_model_key,
                "escalation_model_key": policy.escalation_model_key,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
