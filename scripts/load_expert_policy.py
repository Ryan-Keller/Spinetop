import json
import sys

from model_policy_runtime import load_runtime_policy


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 load_expert_policy.py <expert-id>")
        return 1

    expert_id = sys.argv[1].strip()
    runtime_policy = load_runtime_policy(expert_id)

    summary = {
        "expert_id": runtime_policy.expert_id,
        "allowed_models": runtime_policy.allowed_model_keys,
        "default_model": runtime_policy.default_model_key,
        "escalation_model": runtime_policy.escalation_model_key,
        "expert_file": runtime_policy.expert_file,
    }

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
