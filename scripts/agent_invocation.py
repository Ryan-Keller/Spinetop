from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bootstrap_hermes_profiles import current_active, iter_profiles
from helper_model_runtime import load_helper_runtime_profile
from repo_paths import repo_root
from run_hermes_v1 import extract_json_candidate, invoke_model, load_hermes_runtime_config
from state_machine import normalize_mission_id, read_artifact_index, read_mission_brief, read_state, upsert_artifact_index_entry


ROOT = repo_root()
EXPEDITIONS_ACTIVE_DIR = ROOT / "expeditions" / "active"
WORKBENCH_MISSIONS_DIR = ROOT / "workbench" / "missions"
AGENT_RUNS_DIRNAME = "agent_runs"

CANONICAL_ROLE_IDS = {
    "spinetop-sentinel": "spinetop-sentinel",
    "spinetop-expeditioner": "spinetop-expeditioner",
    "spinetop_expeditioner": "spinetop-expeditioner",
    "spinetop-helper-2b": "spinetop-helper-2b",
    "spinetop-helper_2b": "spinetop-helper-2b",
    "spinetop-mirror": "spinetop-mirror",
}
HELPER_RUNTIME_ROLE_IDS = {
    "spinetop-expeditioner": "spinetop-expeditioner",
    "spinetop-helper-2b": "spinetop-helper-2b",
    "spinetop-mirror": "spinetop-mirror",
}
ROLE_LABELS = {
    "spinetop-sentinel": "Sentinel",
    "spinetop-expeditioner": "Expeditioner",
    "spinetop-helper-2b": "helper_2b",
    "spinetop-mirror": "Mirror",
}

APPROVED_INPUT_ROOTS = [
    ROOT / "workbench" / "missions",
    ROOT / "expeditions" / "active",
    ROOT / "logs" / "support",
]


class AgentInvocationError(ValueError):
    pass


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _short_digest(seed: str) -> str:
    import hashlib

    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _workbench_notes_root(mission_id: str) -> Path:
    return WORKBENCH_MISSIONS_DIR / normalize_mission_id(mission_id) / "notes"


def agent_runs_dir(mission_id: str, *, ensure: bool = False) -> Path:
    path = _workbench_notes_root(mission_id) / AGENT_RUNS_DIRNAME
    if ensure:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _mission_exists(mission_id: str) -> bool:
    mission = normalize_mission_id(mission_id)
    return (EXPEDITIONS_ACTIVE_DIR / mission).exists() or (WORKBENCH_MISSIONS_DIR / mission).exists()


def _is_under(path: Path, root: Path) -> bool:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def _resolve_repo_path(raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    return (ROOT / candidate).resolve()


def _safe_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except Exception:
        return path.resolve().as_posix()


def normalize_role_id(role_id: str) -> str:
    normalized = CANONICAL_ROLE_IDS.get(str(role_id or "").strip())
    if not normalized:
        raise AgentInvocationError(f"unsupported role_id: {role_id}")
    return normalized


def _profile_map() -> dict[str, dict[str, Any]]:
    return {str(profile["profile_name"]): profile for profile in iter_profiles()}


def _profile_for_role(role_id: str) -> dict[str, Any]:
    profile = _profile_map().get(normalize_role_id(role_id))
    if profile is None:
        raise AgentInvocationError(f"no Hermes profile registered for role_id: {role_id}")
    return profile


def _load_soul_text(profile: dict[str, Any]) -> str:
    soul_path = ROOT.joinpath(*str(profile["soul_path"]).split("/"))
    return soul_path.read_text(encoding="utf-8").strip()


def _resolve_model_key(role_id: str, runtime_config: dict[str, Any]) -> str:
    canonical = normalize_role_id(role_id)
    if canonical == "spinetop-sentinel":
        key = str(runtime_config.get("default_model_key") or runtime_config.get("production_model_key") or "").strip()
        if not key:
            raise AgentInvocationError("Sentinel runtime has no default model key configured")
        return key
    helper_profile = load_helper_runtime_profile(HELPER_RUNTIME_ROLE_IDS[canonical])
    key = str(helper_profile.default_model_key or "").strip()
    if not key:
        raise AgentInvocationError(f"{canonical} has no default model key configured")
    return key


def _runtime_active(role_id: str) -> bool:
    return current_active(_profile_for_role(role_id))


def _coerce_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_coerce_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _coerce_jsonable(item) for key, item in value.items()}
    return str(value)


def _load_artifact_refs(mission_id: str, input_payload: dict[str, Any]) -> list[dict[str, Any]]:
    refs = input_payload.get("artifact_refs")
    if not isinstance(refs, list):
        return []
    loaded: list[dict[str, Any]] = []
    for raw_ref in refs:
        text = str(raw_ref or "").strip()
        if not text:
            continue
        path = _resolve_repo_path(text)
        if not path.exists():
            raise AgentInvocationError(f"artifact_ref does not exist: {text}")
        if not any(_is_under(path, root) for root in APPROVED_INPUT_ROOTS):
            raise AgentInvocationError(f"artifact_ref is outside approved invocation roots: {text}")
        mission_from_ref = text.replace("\\", "/")
        if f"/{normalize_mission_id(mission_id)}/" not in f"/{mission_from_ref}/" and not _is_under(path, ROOT / "logs" / "support"):
            raise AgentInvocationError(f"artifact_ref is not mission-local: {text}")
        payload = _load_json(path)
        loaded.append({"path": _safe_ref(path), "payload": _coerce_jsonable(payload)})
    return loaded


def _latest_index_refs(mission_id: str, limit: int = 8) -> list[dict[str, Any]]:
    index = read_artifact_index(mission_id)
    items = list(index.get("items") or [])
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return [
        {
            "kind": str(item.get("kind") or "").strip(),
            "path": str(item.get("path") or "").strip(),
            "created_at": str(item.get("created_at") or "").strip(),
        }
        for item in items[:limit]
        if isinstance(item, dict)
    ]


def _invocation_prompt(role_id: str, mission_id: str, input_payload: dict[str, Any]) -> str:
    brief = read_mission_brief(mission_id) or {}
    state = read_state(mission_id)
    prompt = {
        "task": "Produce one explicit derived-only role result for the mission. This is an invocation, not a loop.",
        "required_output_schema": {
            "role": normalize_role_id(role_id),
            "mission_id": normalize_mission_id(mission_id),
            "result": "string",
            "confidence": "number from 0.0 to 1.0",
            "next_step": "string",
            "derived_only": True,
        },
        "rules": [
            "Return only a JSON object matching the required schema.",
            "Do not start follow-on work, loops, schedules, or hidden agent communication.",
            "Do not claim truth authority, approval authority, or governance authority.",
            "Other roles may read artifacts later, but you must not send direct messages to them.",
        ],
        "mission": {
            "mission_id": normalize_mission_id(mission_id),
            "objective": str(brief.get("objective") or brief.get("task_text") or "").strip(),
            "state": str(state.get("current_state") or "").strip(),
            "latest_artifacts": _latest_index_refs(mission_id),
        },
        "input_payload": _coerce_jsonable(input_payload),
        "loaded_artifacts": _load_artifact_refs(mission_id, input_payload),
    }
    return json.dumps(prompt, indent=2, ensure_ascii=False)


def _normalize_role_output(role_id: str, mission_id: str, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AgentInvocationError("model response is not a JSON object")
    result = str(payload.get("result") or "").strip()
    next_step = str(payload.get("next_step") or "").strip()
    if not result:
        raise AgentInvocationError("model response missing non-empty result")
    if not next_step:
        raise AgentInvocationError("model response missing non-empty next_step")
    confidence_raw = payload.get("confidence")
    if not isinstance(confidence_raw, (int, float)):
        raise AgentInvocationError("model response confidence must be numeric")
    confidence = float(confidence_raw)
    if confidence < 0.0 or confidence > 1.0:
        raise AgentInvocationError("model response confidence must be between 0.0 and 1.0")
    derived_only = payload.get("derived_only")
    if derived_only is not True:
        raise AgentInvocationError("model response derived_only must be true")
    returned_role = str(payload.get("role") or "").strip() or normalize_role_id(role_id)
    if normalize_role_id(returned_role) != normalize_role_id(role_id):
        raise AgentInvocationError("model response role does not match invoked role")
    returned_mission_id = normalize_mission_id(str(payload.get("mission_id") or mission_id).strip())
    if returned_mission_id != normalize_mission_id(mission_id):
        raise AgentInvocationError("model response mission_id does not match invoked mission")
    return {
        "role": normalize_role_id(role_id),
        "mission_id": normalize_mission_id(mission_id),
        "result": result,
        "confidence": confidence,
        "next_step": next_step,
        "derived_only": True,
    }


def _disabled_safe_output(role_id: str, mission_id: str) -> dict[str, Any]:
    return {
        "role": normalize_role_id(role_id),
        "mission_id": normalize_mission_id(mission_id),
        "result": "Role invocation blocked because the mapped runtime is inactive; no model run was attempted.",
        "confidence": 0.0,
        "next_step": "Operator may inspect existing artifacts or explicitly activate the role before retrying.",
        "derived_only": True,
    }


def _run_record_path(mission_id: str, role_id: str, created_at: str, input_payload: dict[str, Any]) -> Path:
    canonical_role = normalize_role_id(role_id)
    run_id = f"agent_run_{utc_stamp()}_{canonical_role}_{_short_digest(json.dumps(_coerce_jsonable(input_payload), sort_keys=True))}"
    return agent_runs_dir(mission_id, ensure=True) / f"{run_id}.json"


def invoke_role(role_id: str, mission_id: str, input_payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(input_payload, dict):
        raise AgentInvocationError("input_payload must be a JSON object")
    mission = normalize_mission_id(mission_id)
    canonical_role = normalize_role_id(role_id)
    if not _mission_exists(mission):
        raise AgentInvocationError(f"mission not found: {mission}")

    created_at = iso_now()
    trigger_reason = str(input_payload.get("trigger_reason") or input_payload.get("reason") or "explicit_role_invocation").strip()
    profile = _profile_for_role(canonical_role)
    soul_text = _load_soul_text(profile)
    artifact_path = _run_record_path(mission, canonical_role, created_at, input_payload)

    runtime_active = _runtime_active(canonical_role)
    runtime_config = load_hermes_runtime_config()
    output: dict[str, Any]
    raw_response = ""
    status = "inactive"
    error = ""
    model_key = ""

    if runtime_active:
        model_key = _resolve_model_key(canonical_role, runtime_config)
        prompt = _invocation_prompt(canonical_role, mission, input_payload)
        system_prompt = (
            f"{soul_text}\n\n"
            "Invocation rules:\n"
            "- This is an explicit one-shot role invocation.\n"
            "- Return only a JSON object with role, mission_id, result, confidence, next_step, derived_only.\n"
            "- derived_only must be true.\n"
            "- No loops, no direct agent messaging, no hidden follow-up work.\n"
        )
        try:
            raw_response = invoke_model(
                model_key,
                prompt,
                runtime_config,
                system_prompt=system_prompt,
                response_format="json_object",
            )
            candidate = extract_json_candidate(raw_response)
            parsed = json.loads(candidate) if candidate else None
            output = _normalize_role_output(canonical_role, mission, parsed)
            status = "success"
        except Exception as exc:
            error = str(exc)
            output = {
                "role": canonical_role,
                "mission_id": mission,
                "result": f"Role invocation failed before a valid structured result was produced: {error}",
                "confidence": 0.0,
                "next_step": "Inspect the logged invocation artifact and retry only after the failure is understood.",
                "derived_only": True,
            }
            status = "error"
    else:
        output = _disabled_safe_output(canonical_role, mission)

    record = {
        "run_id": artifact_path.stem,
        "artifact_kind": "agent_role_invocation",
        "role": canonical_role,
        "role_label": ROLE_LABELS.get(canonical_role, canonical_role),
        "mission_id": mission,
        "created_at": created_at,
        "trigger_reason": trigger_reason,
        "input_payload": _coerce_jsonable(input_payload),
        "profile_name": str(profile.get("profile_name") or "").strip(),
        "profile_ref": str(profile.get("template_root") or "").strip(),
        "soul_ref": str(profile.get("soul_path") or "").strip(),
        "runtime_active": runtime_active,
        "model_key": model_key,
        "status": status,
        "output": output,
        "summary": str(output.get("result") or "").strip(),
        "next_step": str(output.get("next_step") or "").strip(),
        "confidence": float(output.get("confidence") or 0.0),
        "derived_only": True,
    }
    if raw_response:
        record["raw_response"] = raw_response
    if error:
        record["error"] = error

    _write_json(artifact_path, record)
    upsert_artifact_index_entry(mission, "agent_run", artifact_path, created_at=created_at)
    return {
        "ok": status == "success",
        "status": status,
        "role": canonical_role,
        "mission_id": mission,
        "artifact_path": _safe_ref(artifact_path),
        "output": output,
        "record": record,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Explicitly invoke one Hermes-backed Spinetop role for one mission.")
    parser.add_argument("role_id")
    parser.add_argument("mission_id")
    parser.add_argument("--input-json", default="{}", help="JSON object to pass as input_payload.")
    args = parser.parse_args()

    try:
        input_payload = json.loads(args.input_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"input-json must be valid JSON: {exc}")
    if not isinstance(input_payload, dict):
        raise SystemExit("input-json must decode to a JSON object")

    result = invoke_role(args.role_id, args.mission_id, input_payload)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
