from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

import dashboard_api
import governance_utils
import state_machine


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


@contextmanager
def _patched_roots(temp_root: Path):
    expedition_root = temp_root / "expeditions" / "active"
    workbench_root = temp_root / "workbench" / "missions"
    support_orch_root = temp_root / "logs" / "support" / "orchestration"
    support_retrieval_root = temp_root / "logs" / "support" / "retrieval"
    memory_root = temp_root / "memory"
    governance_root = temp_root / "logs" / "governance"
    nanny_status_path = temp_root / "logs" / "nanny" / "item_world_status.json"
    patches = [
        (state_machine, "ROOT", temp_root),
        (state_machine, "EXPEDITIONS_ACTIVE_DIR", expedition_root),
        (dashboard_api, "ROOT", temp_root),
        (dashboard_api, "EXPEDITIONS_ACTIVE_DIR", expedition_root),
        (dashboard_api, "WORKBENCH_MISSIONS_DIR", workbench_root),
        (dashboard_api, "SUPPORT_ORCHESTRATION_DIR", support_orch_root),
        (dashboard_api, "SUPPORT_RETRIEVAL_DIR", support_retrieval_root),
        (dashboard_api, "SUPPORT_ORCHESTRATION_INSTANCES_DIR", support_orch_root / "instances"),
        (dashboard_api, "SUPPORT_RETRIEVAL_INSTANCES_DIR", support_retrieval_root / "instances"),
        (dashboard_api, "HERMES_RUNS_DIR", temp_root / "logs" / "hermes" / "runs"),
        (dashboard_api, "CLARIFICATION_PACKETS_DIR", temp_root / "logs" / "citadel" / "clarification_packets"),
        (dashboard_api, "MEMORY_DIR", memory_root),
        (dashboard_api, "DISPATCH_DIR", memory_root / "dispatch"),
        (dashboard_api, "GOVERNANCE_DIR", governance_root),
        (dashboard_api, "COMPACTOR_LOG_DIR", temp_root / "logs" / "compactor"),
        (dashboard_api, "ARCHIVE_DIR", memory_root / "archive"),
        (dashboard_api, "COMPACTED_DIR", memory_root / "compacted"),
        (dashboard_api, "PROMOTION_DIR", memory_root / "promotion"),
        (dashboard_api, "INBOX_DIR", memory_root / "inbox"),
        (dashboard_api, "EVENT_LOG", temp_root / "logs" / "topology" / "events.jsonl"),
        (governance_utils, "ROOT", temp_root),
        (governance_utils, "GOVERNANCE_DIR", governance_root),
        (governance_utils, "NANNY_STATUS_PATH", nanny_status_path),
        (governance_utils, "DISPATCH_DIR", memory_root / "dispatch"),
    ]
    originals = [(module, name, getattr(module, name)) for module, name, _ in patches]
    try:
        for module, name, value in patches:
            setattr(module, name, value)
        yield
    finally:
        for module, name, value in originals:
            setattr(module, name, value)


def _post_json(client, path: str, payload: dict[str, object]) -> dict[str, object]:
    response = client.post(path, json=payload)
    body = response.get_json(silent=True) or {}
    if response.status_code >= 400:
        raise RuntimeError(f"POST {path} failed with HTTP {response.status_code}: {body}")
    if not body.get("ok", False):
        raise RuntimeError(f"POST {path} returned a non-ok payload: {body}")
    return body


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="mission_agent_creation_smoke_"))

    with _patched_roots(temp_root):
        dashboard_api.app.config["TESTING"] = True
        client = dashboard_api.app.test_client()

        created = _post_json(client, "/api/expeditions", {"objective": "Trace a bounded release regression"})
        item = created.get("item")
        _assert(isinstance(item, dict), "expedition create response missing item")
        mission_id = str(item.get("mission_id") or "").strip()
        _assert(mission_id, "mission_id missing from expedition create response")

        mission_agent = item.get("mission_agent")
        _assert(isinstance(mission_agent, dict), "mission agent profile missing from expedition detail")
        expected_agent_id = f"mission_agent_{mission_id}_expeditioner"
        _assert(str(mission_agent.get("agent_id") or "") == expected_agent_id, f"unexpected mission agent id: {mission_agent}")
        _assert(str(mission_agent.get("mission_id") or "") == mission_id, f"mission agent should be tied to mission_id: {mission_agent}")
        _assert(str(mission_agent.get("role_id") or "") == "spinetop-expeditioner", f"unexpected role binding: {mission_agent}")
        _assert(bool(mission_agent.get("operator_chat_required")) is False, "operator should stay on the main shell")

        scope = mission_agent.get("scope")
        _assert(isinstance(scope, dict) and bool(scope.get("mission_local_only")), f"mission scope should be local-only: {mission_agent}")

        return_policy = mission_agent.get("return_path_policy")
        _assert(isinstance(return_policy, dict), f"return path policy missing: {mission_agent}")
        _assert(bool(return_policy.get("must_use_existing_governed_paths")), f"governed return path flag missing: {return_policy}")
        _assert(bool(return_policy.get("parallel_truth_path_forbidden")), f"parallel truth path should be forbidden: {return_policy}")

        profile_path = temp_root / str(mission_agent.get("config_root") or "") / "profile.json"
        soul_path = temp_root / str(mission_agent.get("soul_ref") or "")
        _assert(profile_path.exists(), f"profile.json missing: {profile_path}")
        _assert(soul_path.exists(), f"SOUL.md missing: {soul_path}")

        profile = _read_json(profile_path)
        _assert(profile == mission_agent, "detail payload should mirror the stored mission agent profile")

        soul_text = soul_path.read_text(encoding="utf-8")
        for required_snippet in [
            "You operate only for mission",
            "Return work through existing bounded lanes",
            "No truth writes.",
            "No governance bypass.",
            "No writes to Honcho or bridge submission paths.",
            "If blocked, return to base with bounded options",
        ]:
            _assert(required_snippet in soul_text, f"SOUL.md missing required policy text: {required_snippet}")

        artifact_index = _read_json(temp_root / "expeditions" / "active" / mission_id / "artifact_index.json")
        items = artifact_index.get("items")
        _assert(isinstance(items, list), f"artifact index missing items: {artifact_index}")
        kinds = {str(record.get('kind') or '') for record in items if isinstance(record, dict)}
        _assert("mission_agent_profile" in kinds, f"artifact index missing mission agent profile entry: {artifact_index}")
        _assert("mission_agent_soul" in kinds, f"artifact index missing mission agent soul entry: {artifact_index}")

        collective_dir = temp_root / "memory" / "collective"
        approved_dispatch_dir = temp_root / "memory" / "dispatch" / "approved"
        honcho_dir = temp_root / "services" / "honcho"
        _assert(not collective_dir.exists(), f"mission start must not write collective truth: {collective_dir}")
        _assert(not approved_dispatch_dir.exists(), f"mission start must not write approved dispatch: {approved_dispatch_dir}")
        _assert(not honcho_dir.exists(), f"mission start must not write Honcho state: {honcho_dir}")

    print("mission_agent_creation_smoke_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
