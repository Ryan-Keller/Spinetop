from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from repo_paths import repo_root


ROOT = repo_root()
SUPPORT_LANE_PREFIXES = ("logs/support/", "memory/drafts/")
FORBIDDEN_WRITE_PREFIXES = (
    "memory/collective/",
    "memory/dispatch/approved/",
    "Honcho",
)
SUPPORTED_HELPER_TYPES = ("retrieval_helper_2b", "runner_helper_2b")
MAX_TTL_SECONDS = 7 * 24 * 60 * 60


class SupportValidationError(ValueError):
    pass


def _path_hint(path: Path | None) -> str:
    return f" ({path})" if path else ""


def _is_under(path: Path, root: Path) -> bool:
    path = path.resolve()
    root = root.resolve()
    return path == root or root in path.parents


def _scope_to_path(scope: str) -> Path:
    candidate = Path(scope)
    if candidate.is_absolute():
        return candidate.resolve()
    return (ROOT / candidate).resolve()


def require_object(data: Any, *, path: Path | None = None, error_cls: type[ValueError] = SupportValidationError) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise error_cls(f"JSON root must be an object{_path_hint(path)}")
    return dict(data)


def require_string(
    data: dict[str, Any],
    field: str,
    *,
    path: Path | None = None,
    error_cls: type[ValueError] = SupportValidationError,
    allow_empty: bool = False,
) -> str:
    value = data.get(field)
    if not isinstance(value, str):
        raise error_cls(f"Field '{field}' must be a string{_path_hint(path)}")
    text = value.strip()
    if not text and not allow_empty:
        raise error_cls(f"Field '{field}' must not be empty{_path_hint(path)}")
    return text


def require_int(
    data: dict[str, Any],
    field: str,
    *,
    path: Path | None = None,
    error_cls: type[ValueError] = SupportValidationError,
    min_value: int | None = None,
) -> int:
    value = data.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise error_cls(f"Field '{field}' must be an integer{_path_hint(path)}")
    if min_value is not None and value < min_value:
        raise error_cls(f"Field '{field}' must be >= {min_value}{_path_hint(path)}")
    return value


def validate_ttl_seconds(
    value: Any,
    *,
    path: Path | None = None,
    field: str = "ttl_seconds",
    error_cls: type[ValueError] = SupportValidationError,
    min_value: int = 1,
    max_value: int = MAX_TTL_SECONDS,
) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise error_cls(f"Field '{field}' must be an integer{_path_hint(path)}")
    if value < min_value:
        raise error_cls(f"Field '{field}' must be >= {min_value}{_path_hint(path)}")
    if value > max_value:
        raise error_cls(f"Field '{field}' must be <= {max_value}{_path_hint(path)}")
    return value


def _list_of_strings(
    value: Any,
    *,
    field: str,
    path: Path | None = None,
    error_cls: type[ValueError] = SupportValidationError,
) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        raise error_cls(f"Field '{field}' must be a string or list of strings{_path_hint(path)}")

    out: list[str] = []
    for idx, item in enumerate(items):
        if not isinstance(item, str):
            raise error_cls(f"Field '{field}' item {idx} must be a string{_path_hint(path)}")
        text = item.strip()
        if not text:
            raise error_cls(f"Field '{field}' item {idx} must not be empty{_path_hint(path)}")
        out.append(text.replace("\\", "/"))
    return out


def _validate_forbidden_destinations(
    value: str,
    *,
    field: str,
    path: Path | None = None,
    error_cls: type[ValueError] = SupportValidationError,
) -> None:
    for forbidden in FORBIDDEN_WRITE_PREFIXES:
        if forbidden == "Honcho":
            if value == "Honcho" or value.startswith("Honcho/"):
                raise error_cls(f"Field '{field}' must not target Honcho{_path_hint(path)}")
        elif value.startswith(forbidden):
            raise error_cls(f"Field '{field}' must not target {forbidden}{_path_hint(path)}")


def normalize_write_scope(
    value: Any,
    *,
    allowed_write_scope: Iterable[str],
    required_write_scope: Iterable[str] = (),
    path: Path | None = None,
    error_cls: type[ValueError] = SupportValidationError,
) -> list[str]:
    items = _list_of_strings(value, field="write_scope", path=path, error_cls=error_cls)
    allowed = {item.replace("\\", "/") for item in allowed_write_scope}
    required = [item.replace("\\", "/") for item in required_write_scope]
    normalized: list[str] = []

    for idx, item in enumerate(items):
        scope_path = _scope_to_path(item)
        if not _is_under(scope_path, ROOT):
            raise error_cls(f"Field 'write_scope' item {idx} must stay inside the repository root{_path_hint(path)}")
        _validate_forbidden_destinations(item, field="write_scope", path=path, error_cls=error_cls)
        if not any(item.startswith(prefix) for prefix in SUPPORT_LANE_PREFIXES):
            raise error_cls(
                f"Field 'write_scope' item {idx} must be a support lane under logs/support/ or memory/drafts/{_path_hint(path)}"
            )
        if item not in allowed:
            raise error_cls(f"Field 'write_scope' item {idx} is not allowed{_path_hint(path)}")
        normalized.append(item)

    for required_item in required:
        if required_item not in normalized:
            raise error_cls(f"Field 'write_scope' must include {required_item}{_path_hint(path)}")

    return normalized


def require_support_lane(
    value: str,
    write_scope: list[str],
    *,
    field: str,
    path: Path | None = None,
    error_cls: type[ValueError] = SupportValidationError,
) -> str:
    lane = value.strip().replace("\\", "/")
    if not lane:
        raise error_cls(f"Field '{field}' must not be empty{_path_hint(path)}")
    _validate_forbidden_destinations(lane, field=field, path=path, error_cls=error_cls)
    if not any(lane.startswith(prefix) for prefix in SUPPORT_LANE_PREFIXES):
        raise error_cls(
            f"Field '{field}' must be a support lane under logs/support/ or memory/drafts/{_path_hint(path)}"
        )
    if lane not in write_scope:
        raise error_cls(f"Field '{field}' must appear in write_scope{_path_hint(path)}")
    return lane


def normalize_support_ref(
    value: str,
    *,
    field: str,
    path: Path | None = None,
    error_cls: type[ValueError] = SupportValidationError,
    require_support_lane: bool = True,
) -> str:
    normalized = value.strip().replace("\\", "/")
    if not normalized:
        raise error_cls(f"Field '{field}' must not be empty{_path_hint(path)}")
    _validate_forbidden_destinations(normalized, field=field, path=path, error_cls=error_cls)
    if require_support_lane and not any(normalized.startswith(prefix) for prefix in SUPPORT_LANE_PREFIXES):
        raise error_cls(f"Field '{field}' must stay inside logs/support/ or memory/drafts/{_path_hint(path)}")
    return normalized


def normalize_support_ref_list(
    value: Any,
    *,
    field: str,
    path: Path | None = None,
    error_cls: type[ValueError] = SupportValidationError,
    require_support_lane: bool = True,
) -> list[str]:
    if value is None:
        return []
    refs = _list_of_strings(value, field=field, path=path, error_cls=error_cls)
    return [
        normalize_support_ref(
            ref,
            field=field,
            path=path,
            error_cls=error_cls,
            require_support_lane=require_support_lane,
        )
        for ref in refs
    ]


def validate_support_request(
    data: Any,
    *,
    allowed_helper_types: Iterable[str],
    allowed_write_scope: Iterable[str],
    required_write_scope: Iterable[str] = (),
    path: Path | None = None,
    error_cls: type[ValueError] = SupportValidationError,
) -> dict[str, Any]:
    record = require_object(data, path=path, error_cls=error_cls)

    helper_type = require_string(record, "helper_type", path=path, error_cls=error_cls)
    if helper_type not in set(allowed_helper_types):
        raise error_cls(f"helper_type must be one of {sorted(set(allowed_helper_types))}{_path_hint(path)}")

    requested_by = require_string(record, "requested_by", path=path, error_cls=error_cls)
    mandate_id = require_string(record, "mandate_id", path=path, error_cls=error_cls)
    task_scope = require_string(record, "task_scope", path=path, error_cls=error_cls)
    ttl_seconds = validate_ttl_seconds(record.get("ttl_seconds"), path=path, error_cls=error_cls)
    return_lane = require_string(record, "return_lane", path=path, error_cls=error_cls)
    write_scope = normalize_write_scope(
        record.get("write_scope"),
        allowed_write_scope=allowed_write_scope,
        required_write_scope=required_write_scope,
        path=path,
        error_cls=error_cls,
    )
    return_lane = require_support_lane(return_lane, write_scope, field="return_lane", path=path, error_cls=error_cls)

    normalized = dict(record)
    normalized["helper_type"] = helper_type
    normalized["requested_by"] = requested_by
    normalized["mandate_id"] = mandate_id
    normalized["task_scope"] = task_scope
    normalized["ttl_seconds"] = ttl_seconds
    normalized["return_lane"] = return_lane
    normalized["write_scope"] = write_scope
    return normalized


def validate_support_event_record(
    data: Any,
    *,
    allowed_helper_types: Iterable[str],
    allowed_write_scope: Iterable[str],
    required_write_scope: Iterable[str] = (),
    path: Path | None = None,
    error_cls: type[ValueError] = SupportValidationError,
) -> dict[str, Any]:
    record = require_object(data, path=path, error_cls=error_cls)

    support_event_id = require_string(record, "support_event_id", path=path, error_cls=error_cls)
    event_type = require_string(record, "event_type", path=path, error_cls=error_cls)
    requested_by = require_string(record, "requested_by", path=path, error_cls=error_cls)
    helper_id = require_string(record, "helper_id", path=path, error_cls=error_cls)
    helper_type = require_string(record, "helper_type", path=path, error_cls=error_cls)
    if helper_type not in set(allowed_helper_types):
        raise error_cls(f"helper_type must be one of {sorted(set(allowed_helper_types))}{_path_hint(path)}")
    mandate_id = require_string(record, "mandate_id", path=path, error_cls=error_cls)
    task_scope = require_string(record, "task_scope", path=path, error_cls=error_cls)
    status = require_string(record, "status", path=path, error_cls=error_cls)
    created_at = require_string(record, "created_at", path=path, error_cls=error_cls)
    ttl_seconds = validate_ttl_seconds(record.get("ttl_seconds"), path=path, error_cls=error_cls)
    return_lane = require_string(record, "return_lane", path=path, error_cls=error_cls)
    write_scope = normalize_write_scope(
        record.get("write_scope"),
        allowed_write_scope=allowed_write_scope,
        required_write_scope=required_write_scope,
        path=path,
        error_cls=error_cls,
    )
    return_lane = require_support_lane(return_lane, write_scope, field="return_lane", path=path, error_cls=error_cls)
    request_ref = record.get("request_ref")
    if request_ref is not None:
        request_ref = normalize_support_ref(
            require_string(record, "request_ref", path=path, error_cls=error_cls),
            field="request_ref",
            path=path,
            error_cls=error_cls,
            require_support_lane=False,
        )
    inputs_refs = normalize_support_ref_list(
        record.get("inputs_refs"),
        field="input_ref",
        path=path,
        error_cls=error_cls,
        require_support_lane=False,
    )
    outputs_refs = normalize_support_ref_list(
        record.get("outputs_refs"),
        field="output_ref",
        path=path,
        error_cls=error_cls,
        require_support_lane=True,
    )

    normalized = dict(record)
    normalized["support_event_id"] = support_event_id
    normalized["event_type"] = event_type
    normalized["requested_by"] = requested_by
    normalized["helper_id"] = helper_id
    normalized["helper_type"] = helper_type
    normalized["mandate_id"] = mandate_id
    normalized["task_scope"] = task_scope
    normalized["status"] = status
    normalized["created_at"] = created_at
    normalized["ttl_seconds"] = ttl_seconds
    normalized["return_lane"] = return_lane
    normalized["write_scope"] = write_scope
    if request_ref is not None:
        normalized["request_ref"] = request_ref
    normalized["inputs_refs"] = inputs_refs
    normalized["outputs_refs"] = outputs_refs
    return normalized
