from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from repo_paths import repo_root


ROOT = repo_root()
REGISTRY_PATH = ROOT / "config" / "hermes_profile_registry.json"

RUNTIME_SUBDIRS = [
    "memories",
    "logs",
    "sessions",
    "skills",
    "cron",
    "pairing",
    "hooks",
    "image_cache",
    "audio_cache",
    "whatsapp/session",
]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_text_if_missing(path: Path, text: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _resolve_repo_path(relative_path: str) -> Path:
    return ROOT.joinpath(*[part for part in relative_path.split("/") if part])


def _json_pointer_get(payload: Any, pointer: str) -> Any:
    current = payload
    if not pointer:
        return current
    for part in pointer.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(pointer)
        current = current[part]
    return current


def _split_ref(ref: str) -> tuple[Path, str]:
    if "#" not in ref:
        return _resolve_repo_path(ref), ""
    path_text, pointer = ref.split("#", 1)
    return _resolve_repo_path(path_text), pointer


def _read_ref(ref: str) -> Any:
    path, pointer = _split_ref(ref)
    payload = _load_json(path)
    return _json_pointer_get(payload, pointer)


def _set_ref(ref: str, value: Any) -> None:
    path, pointer = _split_ref(ref)
    if not pointer:
        raise ValueError(f"cannot set root reference without pointer: {ref}")
    payload = _load_json(path)
    current = payload
    parts = pointer.split(".")
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            raise KeyError(ref)
        current = current[part]
    if not isinstance(current, dict):
        raise ValueError(f"reference parent must be an object: {ref}")
    current[parts[-1]] = value
    _write_json(path, payload)


def load_registry() -> dict[str, Any]:
    payload = _load_json(REGISTRY_PATH)
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError("hermes_profile_registry.json profiles must be an array")
    return payload


def iter_profiles() -> list[dict[str, Any]]:
    registry = load_registry()
    profiles = registry["profiles"]
    normalized: list[dict[str, Any]] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError("hermes_profile_registry.json profiles entries must be objects")
        normalized.append(profile)
    return normalized


def _profile_name_map() -> dict[str, dict[str, Any]]:
    return {str(profile["profile_name"]): profile for profile in iter_profiles()}


def _runtime_home(profile: dict[str, Any], runtime_root: Path | None = None) -> Path:
    if runtime_root is not None:
        return runtime_root / str(profile["profile_name"]) / "home"
    return _resolve_repo_path(str(profile["runtime_home"]))


def _activation_ref(profile: dict[str, Any]) -> str:
    activation = profile.get("activation")
    if not isinstance(activation, dict):
        raise ValueError(f"profile {profile.get('profile_name')} activation must be an object")
    return str(activation.get("control_ref") or "").strip()


def current_active(profile: dict[str, Any]) -> bool:
    value = _read_ref(_activation_ref(profile))
    if not isinstance(value, bool):
        raise ValueError(f"activation control for {profile['profile_name']} must resolve to a boolean")
    return value


def validate_registry() -> list[str]:
    issues: list[str] = []
    seen_names: set[str] = set()
    seen_runtime_homes: set[str] = set()
    seen_memory_roots: set[str] = set()

    for profile in iter_profiles():
        name = str(profile.get("profile_name") or "").strip()
        if not name:
            issues.append("profile_name must be a non-empty string")
            continue
        if name in seen_names:
            issues.append(f"duplicate profile_name: {name}")
        seen_names.add(name)

        for field in (
            "display_name",
            "role_purpose",
            "role_config_ref",
            "template_root",
            "runtime_home",
            "config_root",
            "memory_root",
            "memory_ref",
            "soul_path"
        ):
            value = str(profile.get(field) or "").strip()
            if not value:
                issues.append(f"profile {name} missing {field}")

        template_root = _resolve_repo_path(str(profile.get("template_root") or ""))
        if not template_root.exists():
            issues.append(f"profile {name} missing template_root: {template_root}")
        soul_path = _resolve_repo_path(str(profile.get("soul_path") or ""))
        if not soul_path.exists():
            issues.append(f"profile {name} missing SOUL.md template: {soul_path}")
        profile_card = template_root / "profile.json"
        if not profile_card.exists():
            issues.append(f"profile {name} missing template profile.json: {profile_card}")

        runtime_home = str(profile.get("runtime_home") or "")
        memory_root = str(profile.get("memory_root") or "")
        if runtime_home in seen_runtime_homes:
            issues.append(f"profile {name} reuses runtime_home: {runtime_home}")
        seen_runtime_homes.add(runtime_home)
        if memory_root in seen_memory_roots:
            issues.append(f"profile {name} reuses memory_root: {memory_root}")
        seen_memory_roots.add(memory_root)

        activation = profile.get("activation")
        if not isinstance(activation, dict):
            issues.append(f"profile {name} activation must be an object")
        else:
            default_state = str(activation.get("default_state") or "").strip()
            if default_state not in {"active", "inactive"}:
                issues.append(f"profile {name} activation.default_state must be active or inactive")
            for field in ("control_ref", "inactive_mode_ref", "disabled_safe_contract_ref"):
                ref = str(activation.get(field) or "").strip()
                if not ref:
                    issues.append(f"profile {name} activation missing {field}")
                    continue
                try:
                    _read_ref(ref)
                except Exception as exc:
                    issues.append(f"profile {name} invalid activation ref {field}: {exc}")

        model_provider_slot = profile.get("model_provider_slot")
        if not isinstance(model_provider_slot, dict):
            issues.append(f"profile {name} model_provider_slot must be an object")
        else:
            for field in ("provider_ref", "model_key_ref", "provider_requirement"):
                value = str(model_provider_slot.get(field) or "").strip()
                if not value:
                    issues.append(f"profile {name} model_provider_slot missing {field}")
            for field in ("provider_ref", "model_key_ref"):
                ref = str(model_provider_slot.get(field) or "").strip()
                if ref:
                    try:
                        _read_ref(ref)
                    except Exception as exc:
                        issues.append(f"profile {name} invalid model/provider ref {field}: {exc}")

        separation = profile.get("separation")
        if not isinstance(separation, dict):
            issues.append(f"profile {name} separation must be an object")
        else:
            for field in (
                "shared_identity_allowed",
                "shared_memory_allowed",
                "shared_runtime_home_allowed"
            ):
                value = separation.get(field)
                if value is not False:
                    issues.append(f"profile {name} separation.{field} must be false")

    required_profiles = {
        "spinetop-sentinel",
        "spinetop-expeditioner",
        "spinetop-helper-2b",
        "spinetop-mirror",
    }
    missing = sorted(required_profiles - seen_names)
    if missing:
        issues.append(f"missing required profiles: {missing}")
    return issues


def bootstrap_profiles(runtime_root: Path | None = None) -> list[Path]:
    written: list[Path] = []
    for profile in iter_profiles():
        home = _runtime_home(profile, runtime_root=runtime_root)
        for relative in RUNTIME_SUBDIRS:
            (home / relative).mkdir(parents=True, exist_ok=True)

        soul_template = _resolve_repo_path(str(profile["soul_path"]))
        soul_text = soul_template.read_text(encoding="utf-8")
        _write_text_if_missing(home / "SOUL.md", soul_text)
        _write_text_if_missing(
            home / "config.yaml",
            (
                "# Repo-local Hermes profile bootstrap for Spinetop.\n"
                "# Add provider credentials with `hermes config set ...` after install.\n"
                "terminal:\n"
                "  backend: local\n"
            ),
        )
        _write_text_if_missing(home / ".env", "# Add Hermes provider credentials here if needed.\n")
        _write_text_if_missing(
            home / "memories" / "MEMORY.md",
            (
                f"# {profile['display_name']} Memory\n\n"
                "Repo-local Hermes memory placeholder.\n"
                "Keep role-local notes here only; do not merge identities across profiles.\n"
            ),
        )
        _write_text_if_missing(
            home / "memories" / "USER.md",
            "# User Notes\n\nLeave empty until the operator decides this profile needs role-local user notes.\n",
        )
        _write_text_if_missing(
            home / "README.md",
            (
                f"# {profile['display_name']} Home\n\n"
                f"- role purpose: {profile['role_purpose']}\n"
                f"- template root: {profile['template_root']}\n"
                f"- activation control: {_activation_ref(profile)}\n"
                "- this home is repo-local and safe to remove if you want to revert the bootstrap\n"
            ),
        )
        runtime_profile = {
            "profile_name": profile["profile_name"],
            "display_name": profile["display_name"],
            "role_purpose": profile["role_purpose"],
            "role_config_ref": profile["role_config_ref"],
            "memory_ref": profile["memory_ref"],
            "soul_template_ref": profile["soul_path"],
            "activation_control_ref": _activation_ref(profile),
            "model_provider_slot": profile["model_provider_slot"],
            "separation": profile["separation"],
        }
        _write_text_if_missing(home / "profile.json", json.dumps(runtime_profile, indent=2) + "\n")
        written.append(home)
    return written


def print_status() -> int:
    for profile in iter_profiles():
        home = _runtime_home(profile)
        bootstrapped = home.exists()
        active = current_active(profile)
        default_state = str(profile["activation"]["default_state"])
        print(
            f"{profile['profile_name']}: "
            f"bootstrapped={'yes' if bootstrapped else 'no'} "
            f"active={'true' if active else 'false'} "
            f"default={default_state} "
            f"home={home.relative_to(ROOT).as_posix()}"
        )
    return 0


def set_active(profile_name: str, active: bool) -> int:
    profile = _profile_name_map().get(profile_name)
    if profile is None:
        raise KeyError(f"unknown profile: {profile_name}")
    _set_ref(_activation_ref(profile), active)
    print(f"{profile_name}: active set to {str(active).lower()} via {_activation_ref(profile)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap and manage repo-local Hermes profile homes for Spinetop.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate", help="Validate the Hermes profile registry and template separation.")
    bootstrap_parser = subparsers.add_parser("bootstrap", help="Create repo-local Hermes home directories for all defined profiles.")
    bootstrap_parser.add_argument(
        "--runtime-root",
        default="",
        help="Optional override root for bootstrapped homes, relative to the repo or absolute.",
    )
    subparsers.add_parser("status", help="Show whether each profile is bootstrapped and whether its mapped role is active.")
    active_parser = subparsers.add_parser("set-active", help="Toggle the existing mapped runtime flag for one profile.")
    active_parser.add_argument("profile_name")
    active_parser.add_argument("state", choices=["active", "inactive"])

    args = parser.parse_args()

    if args.command == "validate":
        issues = validate_registry()
        if issues:
            print("hermes_profile_registry: FAIL")
            for issue in issues:
                print(f"  - {issue}")
            return 2
        print("hermes_profile_registry: OK")
        return 0

    if args.command == "bootstrap":
        runtime_root: Path | None = None
        if args.runtime_root:
            candidate = Path(args.runtime_root)
            runtime_root = candidate if candidate.is_absolute() else ROOT / candidate
        homes = bootstrap_profiles(runtime_root=runtime_root)
        print("bootstrapped profiles:")
        for home in homes:
            try:
                shown = home.relative_to(ROOT).as_posix()
            except ValueError:
                shown = str(home)
            print(f"  - {shown}")
        return 0

    if args.command == "status":
        return print_status()

    if args.command == "set-active":
        return set_active(args.profile_name, args.state == "active")

    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
