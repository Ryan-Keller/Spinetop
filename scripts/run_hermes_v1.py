from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from load_expert_policy import load_runtime_policy
from repo_paths import repo_root


ROOT = repo_root()
EXPERT_ID = "hermes-spinetop"
PROMPTS_PATH = ROOT / "docs" / "hermes_v1_prompts.md"
MODEL_REGISTRY_PATH = ROOT / "config" / "model_registry.json"
HERMES_RUNTIME_PATH = ROOT / "config" / "hermes_runtime.json"
SERVICES_PATH = ROOT / "config" / "services.json"
LOGS_DIR = ROOT / "logs"
MEMORY_DIR = ROOT / "memory"

ALLOWED_MODES = {
    "observe",
    "anomaly_review",
    "repair_check",
    "repetition_review",
}

ALLOWED_STATUS = {
    "summary_only",
    "no_action",
    "petition_recommended",
    "blocked",
}

ALLOWED_RECOMMENDED_ACTION = {
    "none",
    "operator_review",
    "create_dispatch_petition",
    "defer",
}

ALLOWED_CLASSIFICATION_KIND = {
    "observation",
    "anomaly",
    "repair_candidate",
}

ALLOWED_SEVERITY = {"low", "medium", "high"}
ALLOWED_BOUNDEDNESS = {"localized", "cross_system", "ambiguous"}
ALLOWED_PETITION_KIND = {
    "anomaly_review",
    "operator_review",
    "repair_request",
    "memory_admission",
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def make_run_id() -> str:
    return f"hermes-{utc_stamp()}-{uuid.uuid4().hex[:4]}"


def load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        return {"_error": f"invalid json: {exc}"}


def normalize_ollama_options(model_cfg: dict[str, Any]) -> dict[str, Any]:
    raw = model_cfg.get("ollama_options", {})
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("model_registry.json ollama_options must be an object when present")

    options: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("model_registry.json ollama_options keys must be non-empty strings")
        option_key = key.strip()
        if option_key == "num_ctx":
            try:
                normalized = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("model_registry.json ollama_options.num_ctx must be an integer") from exc
            if normalized <= 0:
                raise ValueError("model_registry.json ollama_options.num_ctx must be greater than zero")
            options[option_key] = normalized
            continue
        options[option_key] = value
    return options


def load_text_lines(path: Path, tail: int = 20) -> list[str]:
    if not path.exists():
        return []
    buffer: deque[str] = deque(maxlen=tail)
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.rstrip("\n")
                if text:
                    buffer.append(text)
    except OSError as exc:
        return [f"[error reading {path.name}: {exc}]"]
    return list(buffer)


def compact_json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)


def summarize_json_record(path: Path, data: Any, keys: list[str]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"file": str(path), "summary": "[non-object record]"}
    summary = {"file": str(path)}
    for key in keys:
        if key in data:
            summary[key] = data[key]
    return summary


def latest_json_files(directory: Path, pattern: str = "*.json", limit: int = 5) -> list[Path]:
    if not directory.exists():
        return []
    files = [path for path in directory.glob(pattern) if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files[:limit]


def read_topology_recent_events(limit: int = 12) -> list[str]:
    path = LOGS_DIR / "topology" / "events.jsonl"
    return load_text_lines(path, tail=limit)


def read_recent_log_files() -> dict[str, list[str]]:
    logs: dict[str, list[str]] = {}
    topology = read_topology_recent_events()
    if topology:
        logs["topology_events"] = topology

    browser_logs = sorted(LOGS_DIR.glob("browser_tasks_*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    if browser_logs:
        logs["browser_tasks"] = load_text_lines(browser_logs[0], tail=10)
    return logs


def read_state_file(path: Path) -> dict[str, Any]:
    payload = load_json_file(path)
    if isinstance(payload, dict):
        return payload
    if payload is None:
        return {}
    return {"_value": payload}


def summarize_dispatch_state() -> dict[str, Any]:
    dispatch_root = MEMORY_DIR / "dispatch"
    summary: dict[str, Any] = {
        "counts": {},
        "recent_items": [],
    }

    counts: Counter[str] = Counter()
    recent_items: list[dict[str, Any]] = []
    if dispatch_root.exists():
        for folder in sorted([p for p in dispatch_root.iterdir() if p.is_dir()]):
            count = 0
            for path in folder.glob("*.json"):
                if path.name.startswith("decision_"):
                    continue
                count += 1
                recent_items.append((path.stat().st_mtime, path, load_json_file(path)))
            counts[folder.name] = count

    recent_items.sort(key=lambda item: item[0], reverse=True)
    summary["counts"] = dict(counts)
    summary["recent_items"] = [
        summarize_json_record(path, data, ["petition_id", "status", "petition_kind", "summary", "requested_action", "created_at"])
        for _, path, data in recent_items[:5]
    ]
    return summary


def summarize_promotion_backlog() -> dict[str, Any]:
    promotion_root = MEMORY_DIR / "promotion"
    summary: dict[str, Any] = {"count": 0, "recent_items": []}
    if not promotion_root.exists():
        return summary

    files = latest_json_files(promotion_root, "*.json", 5)
    summary["count"] = len(files)
    summary["recent_items"] = [
        summarize_json_record(path, load_json_file(path), ["record_id", "summary", "promotion_candidate", "confidence", "governance_review_state"])
        for path in files
    ]
    return summary


def summarize_collective_state() -> list[dict[str, Any]]:
    collective_root = MEMORY_DIR / "collective"
    if not collective_root.exists():
        return []
    files = latest_json_files(collective_root, "*.json", 5)
    return [
        summarize_json_record(path, load_json_file(path), ["record_id", "summary", "governance_review_state", "confidence", "related_petition_id"])
        for path in files
    ]


def summarize_bridge_status() -> dict[str, Any]:
    seen_path = LOGS_DIR / "honcho_bridge" / "seen_collective_files.json"
    sent_path = LOGS_DIR / "honcho_bridge" / "sent_files.json"
    seen = read_state_file(seen_path)
    sent = read_state_file(sent_path)
    return {
        "seen_collective_files": {
            "count": len(seen),
            "recent_keys": sorted(seen.keys(), reverse=True)[:5] if isinstance(seen, dict) else [],
        },
        "sent_files": {
            "count": len(sent),
            "recent_keys": sorted(sent.keys(), reverse=True)[:5] if isinstance(sent, dict) else [],
        },
    }


def summarize_nanny_state() -> dict[str, Any]:
    return read_state_file(LOGS_DIR / "nanny" / "item_world_status.json")


def summarize_governance_state() -> dict[str, Any]:
    return read_state_file(LOGS_DIR / "governance" / "return_all.json")


def summarize_recent_governance_events(limit: int = 12) -> list[dict[str, Any]]:
    lines = read_topology_recent_events(limit=limit)
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            events.append({"raw": line})
            continue
        if isinstance(payload, dict):
            events.append(
                {
                    "timestamp": payload.get("timestamp"),
                    "event_type": payload.get("event_type"),
                    "record_name": payload.get("record_name"),
                    "status": payload.get("status"),
                    "detail": payload.get("detail"),
                }
            )
        else:
            events.append({"raw": line})
    return events


def summarize_recent_logs() -> dict[str, list[str]]:
    return read_recent_log_files()


def build_snapshot() -> dict[str, Any]:
    nanny_state = summarize_nanny_state()
    governance_state = summarize_governance_state()
    dispatch_state = summarize_dispatch_state()
    promotion_backlog = summarize_promotion_backlog()
    collective_summaries = summarize_collective_state()
    bridge_status = summarize_bridge_status()
    recent_logs = summarize_recent_logs()
    recent_governance_events = summarize_recent_governance_events()

    world_state = {
        "return_all_active": bool(governance_state.get("enabled", False)),
        "nanny_temperature": nanny_state.get("temperature", "unknown"),
        "nanny_cooldown_seconds": nanny_state.get("global_cooldown_seconds", 0),
        "dispatch_counts": dispatch_state.get("counts", {}),
        "promotion_backlog_count": promotion_backlog.get("count", 0),
        "collective_recent_count": len(collective_summaries),
    }

    return {
        "run_id": make_run_id(),
        "world_state": world_state,
        "nanny_state": nanny_state,
        "return_all_state": governance_state,
        "dispatch_status": dispatch_state,
        "promotion_backlog": promotion_backlog,
        "collective_summaries": collective_summaries,
        "bridge_status": bridge_status,
        "recent_governance_events": recent_governance_events,
        "recent_logs": recent_logs,
        "subject": derive_subject(dispatch_state, collective_summaries),
        "evidence_bundle": {
            "world_state": world_state,
            "nanny_state": nanny_state,
            "return_all_state": governance_state,
            "dispatch_status": dispatch_state,
            "promotion_backlog": promotion_backlog,
            "collective_summaries": collective_summaries,
            "bridge_status": bridge_status,
            "recent_governance_events": recent_governance_events,
            "recent_logs": recent_logs,
        },
        "recovery_constraints": {
            "manual_only": True,
            "no_state_writes": True,
            "no_retry_loop": True,
            "governance_brakes": {
                "return_all_active": bool(governance_state.get("enabled", False)),
                "nanny_temperature": nanny_state.get("temperature", "unknown"),
            },
        },
        "repeated_events": summarize_repeated_events(recent_governance_events, dispatch_state, collective_summaries),
    }


def derive_subject(dispatch_state: dict[str, Any], collective_summaries: list[dict[str, Any]]) -> str:
    recent_dispatch = dispatch_state.get("recent_items") or []
    if recent_dispatch:
        first = recent_dispatch[0]
        summary = str(first.get("summary") or "").strip()
        if summary:
            return summary
    if collective_summaries:
        summary = str(collective_summaries[0].get("summary") or "").strip()
        if summary:
            return summary
    return "current bounded issue snapshot"


def summarize_repeated_events(
    recent_governance_events: list[dict[str, Any]],
    dispatch_state: dict[str, Any],
    collective_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    event_types = [str(event.get("event_type") or "").strip() for event in recent_governance_events if event.get("event_type")]
    counts = Counter([event_type for event_type in event_types if event_type])
    repeated = [
        {"event_type": event_type, "count": count}
        for event_type, count in counts.items()
        if count > 1
    ]
    repeated.sort(key=lambda item: (-int(item["count"]), str(item["event_type"])))

    if repeated:
        return repeated

    recent_dispatch = dispatch_state.get("recent_items") or []
    dispatch_summaries = [str(item.get("summary") or "").strip() for item in recent_dispatch if item.get("summary")]
    if len(dispatch_summaries) >= 2 and dispatch_summaries[0] == dispatch_summaries[1]:
        return [{"summary": dispatch_summaries[0], "count": 2}]

    if collective_summaries:
        repeated_summaries = Counter(str(item.get("summary") or "").strip() for item in collective_summaries if item.get("summary"))
        return [
            {"summary": summary, "count": count}
            for summary, count in repeated_summaries.items()
            if count > 1
        ]

    return []


def load_prompt_templates() -> dict[str, str]:
    text = PROMPTS_PATH.read_text(encoding="utf-8")
    templates = {
        "base": extract_template_block(text, "Base System Prompt"),
        "observe": extract_template_block(text, "Observe Prompt"),
        "anomaly_review": extract_template_block(text, "Anomaly Review Prompt"),
        "repair_check": extract_template_block(text, "Repair Check Prompt"),
        "repetition_review": extract_template_block(text, "Repetition Review Prompt"),
    }
    return templates


def extract_template_block(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"Missing prompt section: {heading}")
    fence_start = text.find("```text", start)
    if fence_start < 0:
        raise ValueError(f"Missing prompt fence for: {heading}")
    fence_start = text.find("\n", fence_start) + 1
    fence_end = text.find("\n```", fence_start)
    if fence_end < 0:
        raise ValueError(f"Missing closing fence for: {heading}")
    return text[fence_start:fence_end].strip()


PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


def render_template(template: str, values: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            return ""
        value = values[key]
        if isinstance(value, str):
            return value
        return compact_json(value)

    return PLACEHOLDER_PATTERN.sub(replace, template)


def build_prompt(mode: str, snapshot: dict[str, Any], run_id: str) -> str:
    templates = load_prompt_templates()
    base_prompt = templates["base"]
    mode_prompt = templates[mode]

    prompt_values = {
        "run_id": run_id,
        "world_state": snapshot["world_state"],
        "nanny_state": snapshot["nanny_state"],
        "return_all_state": snapshot["return_all_state"],
        "dispatch_status": snapshot["dispatch_status"],
        "promotion_backlog": snapshot["promotion_backlog"],
        "collective_summaries": snapshot["collective_summaries"],
        "bridge_status": snapshot["bridge_status"],
        "recent_governance_events": snapshot["recent_governance_events"],
        "subject": snapshot["subject"],
        "evidence_bundle": snapshot["evidence_bundle"],
        "recovery_constraints": snapshot["recovery_constraints"],
        "repeated_events": snapshot["repeated_events"],
    }

    rendered = [base_prompt, mode_prompt]
    return "\n\n".join(render_template(part, prompt_values) for part in rendered if part.strip())


def resolve_model_key(runtime_policy: Any, requested_model_key: str | None) -> str:
    if requested_model_key:
        key = requested_model_key.strip()
        if key not in runtime_policy.allowed_model_keys:
            allowed = ", ".join(runtime_policy.allowed_model_keys)
            raise ValueError(f"Model key '{key}' is not allowed for {runtime_policy.expert_id}. Allowed: {allowed}")
        return key
    return runtime_policy.default_model_key


def load_hermes_runtime_config() -> dict[str, Any]:
    payload = load_json_file(HERMES_RUNTIME_PATH)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("hermes_runtime.json must be a JSON object")
    return payload


def load_model_registry() -> dict[str, Any]:
    payload = load_json_file(MODEL_REGISTRY_PATH)
    if not isinstance(payload, dict):
        raise ValueError("model_registry.json must be a JSON object")
    models = payload.get("models", {})
    if not isinstance(models, dict):
        raise ValueError("model_registry.json models must be an object")
    return models


def load_model_lifecycle(runtime_config: dict[str, Any]) -> dict[str, Any]:
    model_profiles = runtime_config.get("model_profiles", {})
    if model_profiles and not isinstance(model_profiles, dict):
        raise ValueError("hermes_runtime.json model_profiles must be an object")

    production_model_key = str(runtime_config.get("production_model_key") or runtime_config.get("default_model_key") or "").strip()
    if not production_model_key:
        raise ValueError("hermes_runtime.json production_model_key is required")

    onboarding_raw = runtime_config.get("onboarding_model_keys", [])
    if onboarding_raw and not isinstance(onboarding_raw, list):
        raise ValueError("hermes_runtime.json onboarding_model_keys must be an array")

    onboarding_model_keys: list[str] = []
    seen: set[str] = set()
    if isinstance(onboarding_raw, list):
        for item in onboarding_raw:
            key = str(item or "").strip()
            if not key:
                raise ValueError("hermes_runtime.json onboarding_model_keys must not contain blank entries")
            if key in seen:
                raise ValueError(f"hermes_runtime.json onboarding_model_keys contains duplicate key: {key}")
            seen.add(key)
            onboarding_model_keys.append(key)

    selected_onboarding_model_key = str(runtime_config.get("selected_onboarding_model_key") or "").strip()
    if selected_onboarding_model_key and selected_onboarding_model_key not in onboarding_model_keys:
        allowed = ", ".join(onboarding_model_keys) or "none"
        raise ValueError(
            f"hermes_runtime.json selected_onboarding_model_key '{selected_onboarding_model_key}' is not in onboarding_model_keys. Allowed: {allowed}"
        )

    if production_model_key in onboarding_model_keys:
        raise ValueError("hermes_runtime.json production_model_key must not also appear in onboarding_model_keys")

    return {
        "production_model_key": production_model_key,
        "onboarding_model_keys": onboarding_model_keys,
        "selected_onboarding_model_key": selected_onboarding_model_key,
        "model_profiles": model_profiles if isinstance(model_profiles, dict) else {},
    }


def load_runtime_activation(runtime_config: dict[str, Any]) -> dict[str, str | bool]:
    runtime_state = runtime_config.get("runtime_state", {})
    if runtime_state is None:
        runtime_state = {}
    if not isinstance(runtime_state, dict):
        raise ValueError("hermes_runtime.json runtime_state must be an object")

    active = runtime_state.get("active", True)
    if not isinstance(active, bool):
        raise ValueError("hermes_runtime.json runtime_state.active must be boolean")

    inactive_mode = str(runtime_state.get("inactive_mode") or "disabled_safe_noop").strip() or "disabled_safe_noop"
    inactive_note = str(runtime_state.get("inactive_note") or "").strip()
    return {
        "active": active,
        "inactive_mode": inactive_mode,
        "inactive_note": inactive_note,
    }


def resolve_runtime_model_key(
    runtime_policy: Any,
    runtime_config: dict[str, Any],
    requested_model_key: str | None,
    requested_onboarding_model_key: str | None,
) -> str:
    lifecycle = load_model_lifecycle(runtime_config)
    if requested_model_key and requested_onboarding_model_key and requested_model_key != requested_onboarding_model_key:
        raise ValueError("Choose either --model-key or --onboarding-model-key, not both")
    if requested_onboarding_model_key:
        key = requested_onboarding_model_key.strip()
        if key not in lifecycle["onboarding_model_keys"]:
            allowed = ", ".join(lifecycle["onboarding_model_keys"]) or "none"
            raise ValueError(f"Onboarding model key '{key}' is not in onboarding_model_keys. Allowed: {allowed}")
        return resolve_model_key(runtime_policy, key)
    if requested_model_key:
        return resolve_model_key(runtime_policy, requested_model_key)

    configured_default = lifecycle["production_model_key"] or str(runtime_config.get("default_model_key") or "").strip()
    if configured_default:
        if configured_default not in runtime_policy.allowed_model_keys:
            allowed = ", ".join(runtime_policy.allowed_model_keys)
            raise ValueError(
                f"Runtime default_model_key '{configured_default}' is not allowed for {runtime_policy.expert_id}. Allowed: {allowed}"
            )
        return configured_default

    return runtime_policy.default_model_key


def validate_model_lifecycle(runtime_policy: Any, models: dict[str, Any], lifecycle: dict[str, Any]) -> None:
    production_model_key = lifecycle["production_model_key"]
    onboarding_model_keys = lifecycle["onboarding_model_keys"]
    selected_onboarding_model_key = lifecycle["selected_onboarding_model_key"]
    model_profiles = lifecycle["model_profiles"]

    missing = [key for key in [production_model_key, *onboarding_model_keys] if key not in models]
    if missing:
        raise ValueError(f"Unknown lifecycle model key(s): {', '.join(sorted(set(missing)))}")

    missing_allowed = [key for key in [production_model_key, *onboarding_model_keys] if key not in runtime_policy.allowed_model_keys]
    if missing_allowed:
        allowed = ", ".join(runtime_policy.allowed_model_keys)
        raise ValueError(f"Lifecycle model key(s) not allowed for {runtime_policy.expert_id}: {', '.join(sorted(set(missing_allowed)))}. Allowed: {allowed}")

    if selected_onboarding_model_key and selected_onboarding_model_key not in onboarding_model_keys:
        allowed = ", ".join(onboarding_model_keys) or "none"
        raise ValueError(
            f"selected_onboarding_model_key '{selected_onboarding_model_key}' must be one of onboarding_model_keys. Allowed: {allowed}"
        )

    for key in [production_model_key, *onboarding_model_keys]:
        profile = model_profiles.get(key)
        if profile is None:
            raise ValueError(f"hermes_runtime.json missing model_profiles entry for {key}")
        if not isinstance(profile, dict):
            raise ValueError(f"hermes_runtime.json model_profiles.{key} must be an object")
        if str(profile.get("model_key") or "").strip() != key:
            raise ValueError(f"hermes_runtime.json model_profiles.{key}.model_key must match the profile key")


def print_model_lifecycle(runtime_config: dict[str, Any], models: dict[str, Any], lifecycle: dict[str, Any]) -> None:
    model_profiles = lifecycle["model_profiles"]
    print("=== MODEL LIFECYCLE ===")
    print(f"production_model_key={lifecycle['production_model_key']}")
    print(
        "onboarding_model_keys="
        + (", ".join(lifecycle["onboarding_model_keys"]) if lifecycle["onboarding_model_keys"] else "none")
    )
    print(
        "selected_onboarding_model_key="
        + (lifecycle["selected_onboarding_model_key"] or "none")
    )
    for key in [lifecycle["production_model_key"], *lifecycle["onboarding_model_keys"]]:
        model_cfg = models.get(key, {})
        profile = model_profiles.get(key, {})
        if not isinstance(model_cfg, dict):
            model_cfg = {}
        if not isinstance(profile, dict):
            profile = {}
        model_name = str(model_cfg.get("model") or "unknown")
        role = str(profile.get("role") or "unknown")
        readiness = str(profile.get("readiness") or "unknown")
        promotion_ready = bool(profile.get("promotion_ready", False))
        intended_use = str(profile.get("intended_use") or "")
        print(f"- {key}")
        print(f"  role={role}")
        print(f"  readiness={readiness}")
        print(f"  promotion_ready={str(promotion_ready).lower()}")
        print(f"  provider_model={model_name}")
        if intended_use:
            print(f"  intended_use={intended_use}")
        criteria = profile.get("promotion_criteria")
        if isinstance(criteria, list) and criteria:
            print("  promotion_criteria:")
            for item in criteria:
                print(f"    - {item}")
    print("")


def load_provider_profile(runtime_config: dict[str, Any], provider: str) -> dict[str, Any]:
    provider_profiles = runtime_config.get("provider_profiles", {})
    if provider_profiles and not isinstance(provider_profiles, dict):
        raise ValueError("hermes_runtime.json provider_profiles must be an object")
    profile = provider_profiles.get(provider, {}) if isinstance(provider_profiles, dict) else {}
    if profile and not isinstance(profile, dict):
        raise ValueError(f"hermes_runtime.json provider_profiles.{provider} must be an object")
    return profile


def invoke_model(
    model_key: str,
    prompt: str,
    runtime_config: dict[str, Any],
    *,
    system_prompt: str | None = None,
    response_format: str = "json_object",
) -> str:
    models = load_model_registry()
    if model_key not in models:
        raise ValueError(f"Unknown model key: {model_key}")

    model_cfg = models[model_key]
    if not isinstance(model_cfg, dict):
        raise ValueError(f"Invalid model config for {model_key}")

    provider = str(model_cfg.get("provider") or "").strip().lower()
    model_name = str(model_cfg.get("model") or "").strip()
    if not provider or not model_name:
        raise ValueError(f"Incomplete model config for {model_key}")

    provider_profile = load_provider_profile(runtime_config, provider)
    mode_safe_settings = runtime_config.get("mode_safe_settings", {})
    if mode_safe_settings and not isinstance(mode_safe_settings, dict):
        raise ValueError("hermes_runtime.json mode_safe_settings must be an object")

    temperature = float(mode_safe_settings.get("temperature", 0.2)) if isinstance(mode_safe_settings, dict) else 0.2
    timeout_seconds = int(provider_profile.get("timeout_seconds", mode_safe_settings.get("timeout_seconds", 120))) if isinstance(mode_safe_settings, dict) else int(provider_profile.get("timeout_seconds", 120))
    ollama_options = normalize_ollama_options(model_cfg) if provider == "ollama" else {}
    if response_format not in {"json_object", "text"}:
        raise ValueError(f"Unsupported response_format: {response_format}")
    resolved_system_prompt = (
        system_prompt.strip()
        if isinstance(system_prompt, str) and system_prompt.strip()
        else "Return only a JSON object that matches the Sentinel-Spinetop v1 run schema. No markdown, no code fences, no commentary."
    )

    if provider == "ollama":
        base_url = str(provider_profile.get("base_url") or "").strip()
        if not base_url:
            services = load_json_file(SERVICES_PATH)
            if not isinstance(services, dict):
                raise ValueError("services.json must be a JSON object")
            ollama = services.get("ollama", {})
            if not isinstance(ollama, dict):
                raise ValueError("services.json ollama entry must be an object")
            host = str(provider_profile.get("host") or ollama.get("host") or "127.0.0.1").strip()
            port = int(provider_profile.get("port") or ollama.get("port") or 11434)
            base_url = f"http://{host}:{port}"
        url = f"{base_url}/api/chat"
        body = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": resolved_system_prompt},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                **ollama_options,
            },
        }
        if response_format == "json_object":
            body["format"] = "json"
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama call failed for {model_key}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Ollama response shape")
        message = payload.get("message", {})
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"].strip()
        if isinstance(payload.get("response"), str):
            return str(payload["response"]).strip()
        raise ValueError("Ollama response missing message.content")

    if provider == "api":
        api_key = str(provider_profile.get("api_key") or os.getenv("OPENAI_API_KEY", "")).strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set for api model invocation")
        base_url = str(provider_profile.get("base_url") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        url = f"{base_url}/chat/completions"
        body = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": resolved_system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
        }
        if response_format == "json_object":
            body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"API call failed for {model_key}: {exc}") from exc
        choices = payload.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise ValueError("API response missing choices")
        message = choices[0].get("message", {})
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"].strip()
        raise ValueError("API response missing message.content")

    raise ValueError(f"Unsupported provider for model key {model_key}: {provider}")


def extract_json_candidate(raw_response: str) -> str | None:
    text = raw_response.strip()
    if not text:
        return None
    if text.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if match:
            text = match.group(1).strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return None


def validate_response_object(data: Any, expected_run_id: str, expected_mode: str) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "response is not a JSON object"

    required = [
        "run_id",
        "mode",
        "status",
        "summary",
        "evidence_refs",
        "recommended_action",
        "petition_kind",
        "confidence",
    ]
    missing = [field for field in required if field not in data]
    if missing:
        return False, f"missing required field(s): {', '.join(missing)}"

    if not isinstance(data["run_id"], str) or not data["run_id"].strip():
        return False, "run_id must be a non-empty string"
    if data["run_id"] != expected_run_id:
        return False, f"run_id mismatch: expected {expected_run_id}, got {data['run_id']}"

    if data["mode"] != expected_mode:
        return False, f"mode mismatch: expected {expected_mode}, got {data['mode']}"
    if data["mode"] not in ALLOWED_MODES:
        return False, f"unsupported mode: {data['mode']}"

    if data["status"] not in ALLOWED_STATUS:
        return False, f"unsupported status: {data['status']}"
    if not isinstance(data["summary"], str) or not data["summary"].strip():
        return False, "summary must be a non-empty string"

    evidence_refs = data["evidence_refs"]
    if not isinstance(evidence_refs, list) or any(not isinstance(item, str) or not item.strip() for item in evidence_refs):
        return False, "evidence_refs must be a list of non-empty strings"

    if data["recommended_action"] not in ALLOWED_RECOMMENDED_ACTION:
        return False, f"unsupported recommended_action: {data['recommended_action']}"

    petition_kind = data["petition_kind"]
    if petition_kind is not None and petition_kind not in ALLOWED_PETITION_KIND:
        return False, f"unsupported petition_kind: {petition_kind}"
    if data["recommended_action"] == "create_dispatch_petition" and petition_kind is None:
        return False, "petition_kind is required when recommended_action is create_dispatch_petition"
    if data["status"] == "petition_recommended" and data["recommended_action"] != "create_dispatch_petition":
        return False, "petition_recommended status requires create_dispatch_petition"
    if data["status"] == "blocked" and data["recommended_action"] == "create_dispatch_petition":
        return False, "blocked status cannot recommend create_dispatch_petition"

    confidence = data["confidence"]
    if not isinstance(confidence, (int, float)):
        return False, "confidence must be numeric"
    if confidence < 0.0 or confidence > 1.0:
        return False, "confidence must be between 0.0 and 1.0"

    classification = data.get("classification")
    if classification is not None:
        if not isinstance(classification, dict):
            return False, "classification must be an object when present"
        cls_required = ["kind", "title", "severity", "boundedness", "affected_system"]
        missing_cls = [field for field in cls_required if field not in classification]
        if missing_cls:
            return False, f"classification missing field(s): {', '.join(missing_cls)}"
        if classification["kind"] not in ALLOWED_CLASSIFICATION_KIND:
            return False, f"unsupported classification.kind: {classification['kind']}"
        if not isinstance(classification["title"], str) or not classification["title"].strip():
            return False, "classification.title must be a non-empty string"
        if classification["severity"] not in ALLOWED_SEVERITY:
            return False, f"unsupported classification.severity: {classification['severity']}"
        if classification["boundedness"] not in ALLOWED_BOUNDEDNESS:
            return False, f"unsupported classification.boundedness: {classification['boundedness']}"
        if not isinstance(classification["affected_system"], str) or not classification["affected_system"].strip():
            return False, "classification.affected_system must be a non-empty string"

    if data["status"] == "summary_only" and data["recommended_action"] not in {"none", "defer"}:
        return False, "summary_only status should not recommend an action beyond none or defer"
    if data["status"] == "no_action" and data["recommended_action"] not in {"none", "defer", "operator_review"}:
        return False, "no_action status should recommend none, defer, or operator_review"

    return True, "ok"


def normalize_response_object(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    if "classification" in normalized and normalized["classification"] is None:
        normalized.pop("classification", None)
    return normalized


def read_input_snapshot(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = load_json_file(path)
    if not isinstance(payload, dict):
        raise ValueError(f"input file must contain a JSON object: {path}")
    return coerce_input_snapshot(path, payload)


def coerce_input_snapshot(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    snapshot_keys = {
        "run_id",
        "world_state",
        "nanny_state",
        "return_all_state",
        "dispatch_status",
        "promotion_backlog",
        "collective_summaries",
        "bridge_status",
        "recent_governance_events",
        "recent_logs",
        "subject",
        "evidence_bundle",
        "recovery_constraints",
        "repeated_events",
    }
    if any(key in payload for key in snapshot_keys):
        return {key: payload[key] for key in snapshot_keys if key in payload}

    stem = path.stem.lower()
    if {"enabled", "issued_by", "issued_at", "allow_custodial_bypass"} <= set(payload):
        return {"return_all_state": payload}
    if {"temperature", "burst_score", "error_score"} <= set(payload):
        return {"nanny_state": payload}
    if "dispatch" in stem and {"record_type", "petition_id"} <= set(payload):
        return {"dispatch_status": {"counts": {}, "recent_items": [payload]}}
    if "collective" in stem and {"record_id", "summary"} <= set(payload):
        return {"collective_summaries": [payload]}
    if "promotion" in stem and {"record_id", "summary"} <= set(payload):
        return {"promotion_backlog": {"count": 1, "recent_items": [payload]}}

    return payload


def merge_snapshot(live_snapshot: dict[str, Any], input_snapshot: dict[str, Any]) -> dict[str, Any]:
    merged = dict(live_snapshot)
    for key, value in input_snapshot.items():
        merged[key] = value
    if "evidence_bundle" not in merged:
        merged["evidence_bundle"] = {
            "world_state": merged.get("world_state", {}),
            "nanny_state": merged.get("nanny_state", {}),
            "return_all_state": merged.get("return_all_state", {}),
            "dispatch_status": merged.get("dispatch_status", {}),
            "promotion_backlog": merged.get("promotion_backlog", {}),
            "collective_summaries": merged.get("collective_summaries", []),
            "bridge_status": merged.get("bridge_status", {}),
            "recent_governance_events": merged.get("recent_governance_events", []),
            "recent_logs": merged.get("recent_logs", {}),
        }
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a single Sentinel-Spinetop v1 review pass.")
    parser.add_argument("mode", nargs="?", choices=sorted(ALLOWED_MODES))
    parser.add_argument("--dry-run", action="store_true", help="Render the prompt and exit without calling a model.")
    parser.add_argument("--input-file", type=Path, help="Load a JSON snapshot override from a file.")
    parser.add_argument("--model-key", help="Override the policy default model key, if allowed.")
    parser.add_argument(
        "--onboarding-model-key",
        help="Run a specific onboarding candidate explicitly, if it is listed in onboarding_model_keys.",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="Print the current production and onboarding lifecycle configuration and exit.",
    )
    args = parser.parse_args()

    if not args.mode and not args.list_models:
        parser.error("mode is required unless --list-models is set")

    runtime_policy = load_runtime_policy(EXPERT_ID)
    runtime_config = load_hermes_runtime_config()
    models = load_model_registry()
    lifecycle = load_model_lifecycle(runtime_config)
    activation = load_runtime_activation(runtime_config)
    validate_model_lifecycle(runtime_policy, models, lifecycle)

    if args.list_models:
        print_model_lifecycle(runtime_config, models, lifecycle)
        return 0

    if not activation["active"]:
        print("=== RUNTIME STATUS ===")
        print(f"active=false")
        print(f"inactive_mode={activation['inactive_mode']}")
        note = str(activation.get("inactive_note") or "").strip()
        if note:
            print(note)
        print("")
        print("=== DISABLED SAFE RESULT ===")
        print("Sentinel runtime inactive; no model run attempted and no writes performed.")
        return 0

    model_key = resolve_runtime_model_key(runtime_policy, runtime_config, args.model_key, args.onboarding_model_key)
    model_cfg = models.get(model_key, {})
    provider = str(model_cfg.get("provider") or "").strip().lower() if isinstance(model_cfg, dict) else ""
    model_name = str(model_cfg.get("model") or "").strip() if isinstance(model_cfg, dict) else ""
    provider_profile = load_provider_profile(runtime_config, provider) if provider else {}
    selected_profile = lifecycle["model_profiles"].get(model_key, {}) if isinstance(lifecycle["model_profiles"], dict) else {}
    if not isinstance(selected_profile, dict):
        selected_profile = {}
    live_snapshot = build_snapshot()
    input_snapshot = read_input_snapshot(args.input_file) if args.input_file else {}
    snapshot = merge_snapshot(live_snapshot, input_snapshot)
    run_id = str(snapshot.get("run_id") or live_snapshot["run_id"])
    prompt = build_prompt(args.mode, snapshot, run_id)

    print("=== MODEL SELECTION ===")
    print(f"profile={str(runtime_config.get('profile') or 'local').strip() or 'local'}")
    print(f"model_key={model_key}")
    print(f"provider={provider or 'unknown'}")
    print(f"model={model_name or 'unknown'}")
    print(f"role={str(selected_profile.get('role') or 'unknown')}")
    print(f"readiness={str(selected_profile.get('readiness') or 'unknown')}")
    print(f"promotion_ready={str(bool(selected_profile.get('promotion_ready', False))).lower()}")
    selected_target = str(runtime_config.get("selected_onboarding_model_key") or "").strip() or "none"
    print(f"selected_onboarding_model_key={selected_target}")
    if provider_profile:
        base_url = str(provider_profile.get("base_url") or "").strip()
        if not base_url and provider == "ollama":
            host = str(provider_profile.get("host") or "").strip()
            port = provider_profile.get("port")
            if host and port is not None:
                base_url = f"http://{host}:{int(port)}"
        if base_url:
            print(f"base_url={base_url}")
    if isinstance(runtime_config.get("mode_safe_settings"), dict):
        print(f"mode_safe_settings={compact_json(runtime_config['mode_safe_settings'])}")
    print("")

    if args.dry_run:
        print("=== RENDERED PROMPT ===")
        print(prompt)
        print("\n=== DRY RUN ===")
        print("pass: prompt rendered; model call skipped")
        return 0

    try:
        raw_response = invoke_model(model_key, prompt, runtime_config)
    except Exception as exc:
        print("=== RAW RESPONSE ===")
        print(f"[unavailable: {exc}]")
        print("\n=== VALIDATION ===")
        print(f"fail: model invocation failed ({exc})")
        return 1

    candidate = extract_json_candidate(raw_response)
    parsed: Any = None
    if candidate is not None:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None

    ok, reason = validate_response_object(parsed, run_id, args.mode) if parsed is not None else (False, "response is not valid JSON")

    print("=== RAW RESPONSE ===")
    print(raw_response)
    print("\n=== VALIDATION ===")
    print(f"{'pass' if ok else 'fail'}: {reason}")
    if ok and isinstance(parsed, dict):
        print("\n=== NORMALIZED RESULT ===")
        print(compact_json(normalize_response_object(parsed)))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
