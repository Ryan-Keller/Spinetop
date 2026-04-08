from __future__ import annotations

import json
import tempfile
from pathlib import Path

import helper_model_runtime
import support_validation


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    profile = helper_model_runtime.load_helper_runtime_profile("spinetop_expeditioner")
    _assert(profile.role_id == "spinetop-expeditioner", "role id mismatch")
    _assert(profile.active is True, "spinetop-expeditioner should stay active unless workers are shut down")
    _assert(profile.execution_backend == "model_backed", "spinetop-expeditioner should be model_backed")
    _assert(profile.inactive_behavior == "disabled_safe", "Expeditioner runtime should stay disabled-safe when inactive")
    _assert(
        profile.mapped_helpers == ["retrieval_helper_2b", "runner_helper_2b"],
        "mapped helper list mismatch",
    )
    _assert(
        profile.role_description.startswith("Spinetop-Expeditioner"),
        "role description should identify the Expeditioner lane",
    )
    _assert(
        "local_gemma4_e4b_4k" in profile.allowed_model_keys,
        "expected configured local model in Expeditioner allowed_model_keys",
    )
    _assert(
        profile.default_model_key == "local_gemma4_e4b_4k",
        "Expeditioner should resolve the configured local model by default",
    )
    _assert(
        profile.fallback_model_key == "local_gemma4_e4b_4k",
        "Expeditioner should expose the configured local fallback model key",
    )
    _assert(profile.authority_boundary.get("derived_outputs_only") is True, "Expeditioner role should stay derived-only")
    _assert(
        "write to memory/collective" in profile.authority_boundary.get("may_not", []),
        "Expeditioner boundary should forbid collective writes",
    )
    _assert(
        "mission briefs and mission inputs under expeditions/active/" in profile.authority_boundary.get("may_read", []),
        "Expeditioner boundary should allow expedition-local reads",
    )
    _assert(
        "workbench/missions/ notes and mission-local artifacts" in profile.context_refs,
        "Expeditioner should carry mission-local context references",
    )
    _assert(
        profile.behavior_contract.get("thinking_style") == [
            "first-pass mission execution",
            "bounded assumptions",
            "useful-now delivery",
        ],
        "Expeditioner should expose the bounded first-pass thinking style",
    )
    _assert(
        profile.behavior_contract.get("output_structure") == [
            "first-pass answer",
            "assumptions used",
            "next steps",
        ],
        "Expeditioner should expose the structured first-pass output layout",
    )
    _assert(
        "omit the assumptions section when no assumptions were used" in profile.behavior_contract.get("must_do", []),
        "Expeditioner should keep assumptions optional",
    )
    _assert(
        "default to broad defer language when a bounded first pass is possible" in profile.behavior_contract.get("must_not", []),
        "Expeditioner should avoid generic blocking language",
    )

    helper_profile = helper_model_runtime.load_helper_runtime_profile("spinetop-helper_2b")
    _assert(helper_profile.role_id == "spinetop-helper-2b", "helper role id mismatch")
    _assert(helper_profile.active is True, "spinetop-helper-2b should stay active unless workers are shut down")
    _assert(helper_profile.execution_backend == "model_backed", "spinetop-helper-2b should use the model seam")
    _assert(
        helper_profile.inactive_behavior == "disabled_safe",
        "Spinetop-helper-2b runtime should stay disabled-safe when inactive",
    )
    _assert(
        helper_profile.role_description.startswith("Spinetop-helper_2b is the field-side mini brain"),
        "role description should identify the field helper lane",
    )
    _assert(
        "mission-local context under workbench/missions/" in helper_profile.authority_boundary.get("may_read", []),
        "Spinetop-helper-2b should allow mission-local workbench reads",
    )
    _assert(
        "write to memory/collective" in helper_profile.authority_boundary.get("may_not", []),
        "Spinetop-helper-2b should forbid collective writes",
    )
    _assert(
        helper_profile.behavior_contract.get("thinking_style") == ["short horizon", "local context", "tactical suggestions"],
        "Spinetop-helper-2b should expose the tactical helper thinking style",
    )
    _assert(
        helper_profile.default_model_key == "local_granite3_3_2b_q2k",
        "Spinetop-helper-2b should bind to the configured local model by default",
    )
    _assert(
        helper_profile.fallback_model_key == "local_granite3_3_2b_q2k",
        "Spinetop-helper-2b should expose the configured local fallback key",
    )
    _assert(
        helper_profile.behavior_contract.get("output_structure") == [
            "current context",
            "key observations",
            "possible next steps",
            "open questions",
        ],
        "Spinetop-helper-2b should expose the small structured output layout",
    )
    _assert(
        helper_profile.behavior_contract.get("separation_rule") == "helper_2b internal reasoning stays separate from runner-return external receipts",
        "Spinetop-helper-2b should keep internal reasoning distinct from runner returns",
    )

    mirror_profile = helper_model_runtime.load_helper_runtime_profile("spinetop-mirror")
    _assert(mirror_profile.role_id == "spinetop-mirror", "mirror role id mismatch")
    _assert(mirror_profile.active is False, "spinetop-mirror should require explicit activation")
    _assert(mirror_profile.execution_backend == "model_backed", "spinetop-mirror should use the model seam")
    _assert(mirror_profile.inactive_behavior == "disabled_safe", "Mirror runtime should stay disabled-safe when inactive")
    _assert(
        mirror_profile.role_description.startswith("Spinetop-Mirror is the read-only memory interpretation role"),
        "role description should identify the mirror lane",
    )
    _assert(
        "Honcho query interfaces and Honcho-backed read results only" in mirror_profile.authority_boundary.get("may_read", []),
        "Mirror should allow only Honcho read-side access",
    )
    _assert(
        "write to Honcho" in mirror_profile.authority_boundary.get("may_not", []),
        "Mirror should forbid Honcho writes",
    )
    _assert(
        "workbench/missions/*/notes/mirror/" in mirror_profile.support_write_scope,
        "Mirror should write only to the mission-local mirror lane",
    )
    _assert(
        mirror_profile.default_model_key == "local_granite3_3_2b_q2k",
        "Mirror should bind to the configured local model by default",
    )
    _assert(
        mirror_profile.fallback_model_key == "local_granite3_3_2b_q2k",
        "Mirror should expose the configured local fallback key",
    )

    temp_root = Path(tempfile.mkdtemp(prefix="helper_model_runtime_"))
    temp_model_registry = temp_root / "model_registry.json"
    temp_helper_registry = temp_root / "helper_model_registry.json"
    _write_json(
        temp_model_registry,
        {
            "models": {
                "local_gemma4_e4b_4k": {"provider": "ollama", "model": "gemma4:e4b-4k"},
                "local_granite3_3_2b_q2k": {
                    "provider": "ollama",
                    "model": "granite3.3:2b",
                    "ollama_options": {"num_ctx": 8192},
                },
            }
        },
    )
    _write_json(
        temp_helper_registry,
        {
            "roles": {
                "spinetop-expeditioner": {
                    "role_description": "Spinetop-Expeditioner is the mission-doing worker for first-pass derived outputs inside mission-local and workbench lanes.",
                    "active": True,
                    "execution_backend": "model_backed",
                    "allowed_model_keys": [
                        "local_gemma4_e4b_4k",
                    ],
                    "default_model_key": "local_gemma4_e4b_4k",
                    "fallback_model_key": "local_gemma4_e4b_4k",
                    "provider_requirement": "local_only",
                    "mapped_helpers": ["retrieval_helper_2b", "runner_helper_2b"],
                    "context_refs": ["workbench/missions/ notes and mission-local artifacts", "expeditions/active/ mission briefs and mission inputs"],
                    "config_refs": ["config/helper_model_registry.json"],
                    "support_write_scope": ["workbench/missions/", "logs/support/"],
                    "inactive_behavior": "disabled_safe",
                    "behavior_contract": {
                        "thinking_style": ["first-pass mission execution", "bounded assumptions", "useful-now delivery"],
                        "output_structure": ["first-pass answer", "assumptions used", "next steps"],
                        "must_do": [
                            "produce something useful now with the context in hand",
                            "omit the assumptions section when no assumptions were used",
                        ],
                        "must_not": ["write truth", "default to broad defer language when a bounded first pass is possible"],
                        "separation_rule": "Expeditioner mission-doing output stays structured, human-readable, and distinct from governance, review, and scripted external receipts",
                    },
                    "authority_boundary": {
                        "may_read": ["mission briefs and mission inputs under expeditions/active/"],
                        "may_write_only": ["mission-local outputs and workbench artifacts under workbench/missions/"],
                        "derived_outputs_only": True,
                        "returns_must_remain_structured": True,
                        "may_not": ["write truth", "submit", "write to memory/collective"],
                    },
                },
                "spinetop-helper-2b": {
                    "role_description": "Spinetop-helper_2b is the field-side mini brain for short-horizon expedition support and bounded runner-return preparation.",
                    "active": True,
                    "execution_backend": "model_backed",
                    "allowed_model_keys": [
                        "local_granite3_3_2b_q2k",
                    ],
                    "default_model_key": "local_granite3_3_2b_q2k",
                    "fallback_model_key": "local_granite3_3_2b_q2k",
                    "provider_requirement": "local_only",
                    "mapped_helpers": ["retrieval_helper_2b", "runner_helper_2b"],
                    "context_refs": ["workbench/missions/ notes and mission-local helper context", "expeditions/active/ mission-local artifacts"],
                    "config_refs": ["config/helper_model_registry.json", "config/helper_role.json"],
                    "support_write_scope": ["logs/support/", "memory/drafts/ only when explicitly allowed"],
                    "inactive_behavior": "disabled_safe",
                    "behavior_contract": {
                        "thinking_style": ["short horizon", "local context", "tactical suggestions"],
                        "output_structure": ["current context", "key observations", "possible next steps", "open questions"],
                        "must_do": ["summarize local findings", "highlight contradictions without inventing a resolution"],
                        "must_not": ["act like Sentinel", "write truth"],
                        "separation_rule": "helper_2b internal reasoning stays separate from runner-return external receipts",
                    },
                    "authority_boundary": {
                        "may_read": ["mission-local context under workbench/missions/"],
                        "may_write_only": ["helper-local support artifacts under logs/support/"],
                        "derived_outputs_only": True,
                        "returns_must_remain_structured": True,
                        "may_not": ["write truth", "submit", "write to memory/collective"],
                    },
                },
                "spinetop-mirror": {
                    "role_description": "Spinetop-Mirror is the read-only memory interpretation role for Honcho-backed inspection and mission-local reflection.",
                    "active": False,
                    "execution_backend": "model_backed",
                    "allowed_model_keys": [
                        "local_granite3_3_2b_q2k",
                    ],
                    "default_model_key": "local_granite3_3_2b_q2k",
                    "fallback_model_key": "local_granite3_3_2b_q2k",
                    "provider_requirement": "local_only",
                    "mapped_helpers": [],
                    "context_refs": ["Honcho query interfaces and Honcho-backed read results", "workbench/missions/*/notes/mirror/"],
                    "config_refs": ["config/helper_model_registry.json", "config/mirror_role.json"],
                    "support_write_scope": ["workbench/missions/*/notes/mirror/"],
                    "inactive_behavior": "disabled_safe",
                    "behavior_contract": {
                        "thinking_style": [],
                        "output_structure": [],
                        "must_do": [],
                        "must_not": [],
                        "separation_rule": "",
                    },
                    "authority_boundary": {
                        "may_read": ["Honcho query interfaces and Honcho-backed read results only"],
                        "may_write_only": ["mission-local mirror artifacts under workbench/missions/*/notes/mirror/"],
                        "derived_outputs_only": True,
                        "returns_must_remain_structured": True,
                        "may_not": ["write truth", "submit", "write to Honcho", "write to memory/collective"],
                    },
                }
            }
        },
    )

    original_model_registry = helper_model_runtime.MODEL_REGISTRY_PATH
    original_helper_registry = helper_model_runtime.HELPER_MODEL_REGISTRY_PATH
    try:
        helper_model_runtime.MODEL_REGISTRY_PATH = temp_model_registry
        helper_model_runtime.HELPER_MODEL_REGISTRY_PATH = temp_helper_registry
        configured = helper_model_runtime.load_helper_runtime_profile("spinetop_expeditioner")
        helper_configured = helper_model_runtime.load_helper_runtime_profile("spinetop-helper_2b")
        mirror_configured = helper_model_runtime.load_helper_runtime_profile("spinetop-mirror")
    finally:
        helper_model_runtime.MODEL_REGISTRY_PATH = original_model_registry
        helper_model_runtime.HELPER_MODEL_REGISTRY_PATH = original_helper_registry

    _assert(configured.execution_backend == "model_backed", "configured Expeditioner role should load model_backed")
    _assert(configured.active is True, "configured Expeditioner role should preserve explicit activation")
    _assert(
        configured.default_model_key == "local_gemma4_e4b_4k",
        "configured Expeditioner default model key mismatch",
    )
    _assert(
        configured.fallback_model_key == "local_gemma4_e4b_4k",
        "configured Expeditioner fallback model key mismatch",
    )
    _assert(helper_configured.role_id == "spinetop-helper-2b", "configured helper role should load")
    _assert(helper_configured.active is True, "configured helper role should preserve default-active behavior")
    _assert(helper_configured.execution_backend == "model_backed", "configured helper role should stay model_backed")
    _assert(
        helper_configured.behavior_contract.get("thinking_style") == ["short horizon", "local context", "tactical suggestions"],
        "configured helper behavior contract mismatch",
    )
    _assert(mirror_configured.role_id == "spinetop-mirror", "configured mirror role should load")
    _assert(
        mirror_configured.default_model_key == "local_granite3_3_2b_q2k",
        "configured Mirror default model key mismatch",
    )
    _assert(mirror_configured.active is False, "configured Mirror role should preserve inactive flag")

    try:
        support_validation.normalize_write_scope(
            ["logs/support/retrieval/", "memory/dispatch/approved/"],
            allowed_write_scope=["logs/support/retrieval/"],
        )
    except support_validation.SupportValidationError:
        pass
    else:
        raise AssertionError("governed write lanes must stay forbidden for helper write_scope")

    print("helper_model_runtime_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
