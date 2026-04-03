import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
EXPERTS_DIR = ROOT / "experts"
SPINELAB_EXPERTS_DIR = ROOT.parent / "Spinelab" / "experts"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_expert_file(expert_id: str) -> Path:
    filename = expert_id.replace("-", "_") + ".json"
    candidate = EXPERTS_DIR / filename
    if candidate.exists():
        return candidate
    candidate = SPINELAB_EXPERTS_DIR / filename
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Expert file not found for {expert_id}")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 load_expert_policy.py <expert-id>")
        return 1

    expert_id = sys.argv[1].strip()
    registry = load_json(CONFIG_DIR / "model_registry.json")
    policy = load_json(CONFIG_DIR / "expert_model_policy.json")
    expert_file = resolve_expert_file(expert_id)
    expert = load_json(expert_file)

    models = set(registry.get("models", {}).keys())
    expert_policy = policy.get("experts", {}).get(expert_id)
    if not expert_policy:
        raise KeyError(f"No policy entry for {expert_id}")

    allowed = expert_policy.get("allowed_models", [])
    default_model = expert_policy.get("default_model")
    escalation_model = expert_policy.get("escalation_model")

    missing_models = [m for m in allowed + [default_model, escalation_model] if m not in models]
    if missing_models:
        raise ValueError(f"Unknown model keys: {missing_models}")

    summary = {
        "expert_id": expert.get("expert_id", expert_id),
        "lane": expert_policy.get("lane"),
        "allowed_models": allowed,
        "default_model": default_model,
        "escalation_model": escalation_model,
        "api_allowed": expert_policy.get("api_allowed", False),
        "forbidden_actions": expert.get("forbidden_actions", []),
    }

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
