import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "model_registry.json"
POLICY = ROOT / "config" / "expert_model_policy.json"
EXPERTS_DIR = ROOT / "experts"
SPINELAB_EXPERTS_DIR = ROOT.parent / "Spinelab" / "experts"

REQUIRED_FIELDS = [
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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def gather_experts() -> list[Path]:
    files = []
    if EXPERTS_DIR.exists():
        files.extend(sorted(EXPERTS_DIR.glob("*.json")))
    if SPINELAB_EXPERTS_DIR.exists():
        files.extend(sorted(SPINELAB_EXPERTS_DIR.glob("*.json")))
    return files


def validate_expert(expert: dict, models: set[str], policy: dict) -> list[str]:
    issues: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in expert:
            issues.append(f"missing field: {field}")

    default_key = expert.get("default_model_key")
    escalation_key = expert.get("escalation_model_key")
    if default_key and default_key not in models:
        issues.append(f"default_model_key not in registry: {default_key}")
    if escalation_key and escalation_key not in models:
        issues.append(f"escalation_model_key not in registry: {escalation_key}")

    expert_id = str(expert.get("expert_id") or "")
    policy_entry = policy.get("experts", {}).get(expert_id)
    if policy_entry:
        allowed = policy_entry.get("allowed_models", [])
        missing = [m for m in allowed if m not in models]
        if missing:
            issues.append(f"allowed_models missing in registry: {missing}")
        lane = policy_entry.get("lane")
        if lane and expert.get("lane") != lane:
            issues.append(f"lane mismatch policy={lane} expert={expert.get('lane')}")
    else:
        issues.append("no policy entry for expert_id")

    return issues


def main() -> int:
    registry = load_json(REGISTRY)
    policy = load_json(POLICY)
    models = set(registry.get("models", {}).keys())

    experts = gather_experts()
    if not experts:
        print("No expert files found.")
        return 1

    total = 0
    errors = 0
    print("Expert config validation\n")

    for path in experts:
        total += 1
        expert = load_json(path)
        issues = validate_expert(expert, models, policy)
        name = expert.get("expert_id", path.stem)
        if issues:
            errors += 1
            print(f"- {name}: FAIL")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print(f"- {name}: OK")

    print(f"\nSummary: {total} checked, {errors} with issues")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
