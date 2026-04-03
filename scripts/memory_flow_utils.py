from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "agent_id": str,
    "session_id": str,
    "workspace": str,
    "timestamp_created": str,

    "source": str,
    "expert_name": str,
    "task": str,
    "summary": str,
    "key_findings": list,
    "confidence": (int, float),
    "recommended_action": str,
    "promotion_candidate": bool,
}

AUTO_FIELDS = {"agent_id", "session_id", "workspace", "timestamp_created"}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def infer_agent_id(data: dict[str, Any], path: Path) -> str:
    value = data.get("agent_id")
    if isinstance(value, str) and value.strip():
        return value.strip()

    source = str(data.get("source", "")).lower()
    expert_name = str(data.get("expert_name", "")).lower()
    path_str = str(path).lower()

    if "laptop" in source or "laptop" in expert_name or "spinelab" in path_str:
        return "hermes-laptop"

    return "hermes-desktop"


def infer_workspace(data: dict[str, Any], path: Path) -> str:
    value = data.get("workspace")
    if isinstance(value, str) and value.strip():
        return value.strip()

    agent_id = str(data.get("agent_id", "")).lower()
    path_str = str(path).lower()

    if "laptop" in agent_id or "spinelab" in path_str:
        return "spinelab"

    return "spinetop"


def infer_session_id(data: dict[str, Any]) -> str:
    value = data.get("session_id")
    if isinstance(value, str) and value.strip():
        return value.strip()

    agent_id = str(data.get("agent_id", "")).strip() or "hermes-desktop"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{agent_id}-session-{stamp}"


def normalize_record(data: Any, path: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")

    normalized = dict(data)

    normalized["agent_id"] = infer_agent_id(normalized, path)
    normalized["workspace"] = infer_workspace(normalized, path)
    normalized["session_id"] = infer_session_id(normalized)

    value = normalized.get("timestamp_created")
    if not isinstance(value, str) or not value.strip():
        normalized["timestamp_created"] = now_iso()

    return normalized


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def memory_dir(name: str) -> Path:
    return repo_root() / "memory" / name


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"Missing file: {path}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in {path}: {exc}")


def validate_schema(data: Any, path: Path) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")

    missing = [key for key in REQUIRED_FIELDS.keys() if key not in data]
    if missing:
        raise ValueError(f"Missing required fields in {path}: {', '.join(missing)}")

    for key, expected in REQUIRED_FIELDS.items():
        value = data.get(key)
        if not isinstance(value, expected):
            raise ValueError(
                f"Field '{key}' has wrong type in {path}: expected {expected}, got {type(value).__name__}"
            )

    if any(not isinstance(item, str) or not item.strip() for item in data["key_findings"]):
        raise ValueError(f"Field 'key_findings' must be a list of non-empty strings in {path}")


def validate_file(path: Path) -> dict[str, Any]:
    data = load_json(path)
    data = normalize_record(data, path)
    validate_schema(data, path)
    write_json(path, data)
    return data


def add_timestamp(data: dict[str, Any], field: str) -> dict[str, Any]:
    data[field] = datetime.now().isoformat(timespec="seconds")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_in_dir(path_or_name: str, directory: Path) -> Path:
    candidate = Path(path_or_name)
    if candidate.is_absolute():
        return candidate
    return (directory / path_or_name).resolve()


def ensure_in_dir(path: Path, directory: Path) -> None:
    directory = directory.resolve()
    path = path.resolve()
    if directory not in path.parents:
        raise ValueError(f"File {path} is not inside {directory}")


def safe_destination(path: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = destination_dir / path.name
    if not target.exists():
        return target
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return destination_dir / f"{path.stem}_{stamp}{path.suffix}"
