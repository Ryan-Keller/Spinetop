from __future__ import annotations

import json
import sys

from helper_model_runtime import load_helper_runtime_profile


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 load_helper_model_policy.py <role-id>")
        return 1

    role_id = sys.argv[1].strip()
    profile = load_helper_runtime_profile(role_id)

    print(
        json.dumps(
            {
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
