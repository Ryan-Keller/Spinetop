from __future__ import annotations

import helper_model_runtime


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    profile = helper_model_runtime.load_helper_runtime_profile("helper_2b")
    _assert(profile.role_id == "helper_2b", "role id mismatch")
    _assert(profile.execution_backend == "scripted", "helper_2b should stay scripted by default")
    _assert(
        profile.mapped_helpers == ["retrieval_helper_2b", "runner_helper_2b"],
        "mapped helper list mismatch",
    )
    _assert(
        "local_onboarding_gemma4_e4b_4k" in profile.allowed_model_keys,
        "expected onboarding local model in helper allowed_model_keys",
    )
    _assert(
        "local_production_qwen2_5_coder_14b" in profile.allowed_model_keys,
        "expected production local model in helper allowed_model_keys",
    )
    _assert(profile.default_model_key == "", "scripted helper role should not resolve a default model yet")
    print("helper_model_runtime_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
