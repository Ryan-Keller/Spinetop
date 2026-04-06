from __future__ import annotations

import json
import tempfile
from pathlib import Path

import bootstrap_hermes_profiles


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    issues = bootstrap_hermes_profiles.validate_registry()
    _assert(not issues, f"registry should validate cleanly: {issues}")

    temp_root = Path(tempfile.mkdtemp(prefix="hermes_profiles_"))
    homes = bootstrap_hermes_profiles.bootstrap_profiles(runtime_root=temp_root)
    expected = {
        "spinetop-sentinel",
        "spinetop-expeditioner",
        "spinetop-helper-2b",
        "spinetop-mirror",
    }
    _assert(len(homes) == len(expected), f"expected {len(expected)} bootstrapped homes, got {len(homes)}")

    seen_names: set[str] = set()
    seen_memory_roots: set[str] = set()
    for home in homes:
        profile_path = home / "profile.json"
        _assert(profile_path.exists(), f"missing runtime profile: {profile_path}")
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
        profile_name = str(payload.get("profile_name") or "")
        _assert(profile_name in expected, f"unexpected profile name: {profile_name}")
        _assert(profile_name not in seen_names, f"profile duplicated: {profile_name}")
        seen_names.add(profile_name)

        _assert((home / "SOUL.md").exists(), f"missing SOUL.md for {profile_name}")
        _assert((home / "config.yaml").exists(), f"missing config.yaml for {profile_name}")
        _assert((home / "memories" / "MEMORY.md").exists(), f"missing MEMORY.md for {profile_name}")
        _assert((home / "memories" / "USER.md").exists(), f"missing USER.md for {profile_name}")

        separation = payload.get("separation") or {}
        _assert(separation.get("shared_identity_allowed") is False, f"{profile_name} must not share identity")
        _assert(separation.get("shared_memory_allowed") is False, f"{profile_name} must not share memory")
        _assert(separation.get("shared_runtime_home_allowed") is False, f"{profile_name} must not share runtime home")

        memory_root = (home / "memories").resolve()
        _assert(str(memory_root) not in seen_memory_roots, f"memory root reused: {memory_root}")
        seen_memory_roots.add(str(memory_root))

    sentinel = bootstrap_hermes_profiles._profile_name_map()["spinetop-sentinel"]
    helper = bootstrap_hermes_profiles._profile_name_map()["spinetop-helper-2b"]
    mirror = bootstrap_hermes_profiles._profile_name_map()["spinetop-mirror"]
    _assert(bootstrap_hermes_profiles.current_active(sentinel) is True, "Sentinel should remain active by current runtime")
    _assert(bootstrap_hermes_profiles.current_active(helper) is False, "helper_2b should remain disabled-safe by default")
    _assert(bootstrap_hermes_profiles.current_active(mirror) is False, "Mirror should remain disabled-safe by default")

    print("hermes_profile_bootstrap_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
