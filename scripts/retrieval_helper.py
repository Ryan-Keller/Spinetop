from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from repo_paths import repo_root


ROOT = repo_root()
HELPER_TYPE = "retrieval_helper_2b"
ALLOWED_RESULT_STATUSES = {"complete", "partial", "none_found", "blocked", "failed"}
ALLOWED_INSTANCE_STATUSES = {
    "spawned",
    "running",
    "complete",
    "partial",
    "none_found",
    "blocked",
    "failed",
    "replaced",
    "expired",
}
ALLOWED_REPLACEMENT_REASONS = {"timeout", "drift", "inconsistent_output", "overload"}

# Approved retrieval sources are read-only. They are not truth lanes.
APPROVED_READ_ROOTS = [
    ROOT / "docs",
    ROOT / "scripts",
    ROOT / "config",
    ROOT / "experts",
    ROOT / "memory" / "inbox",
    ROOT / "memory" / "promotion",
    ROOT / "memory" / "dispatch" / "pending",
    ROOT / "memory" / "dispatch" / "approved",
    ROOT / "memory" / "collective",
    ROOT / "memory" / "drafts",
]

LOG_ROOT = ROOT / "logs" / "support" / "retrieval"
INSTANCE_DIR = LOG_ROOT / "instances"
ARTIFACT_DIR = LOG_ROOT / "artifacts"
EVENT_LOG = LOG_ROOT / "events.jsonl"

CONTRACT = {
    "helper_type": HELPER_TYPE,
    "instance_fields": [
        "helper_id",
        "helper_type",
        "mandate_id",
        "task_scope",
        "created_at",
        "expires_at",
        "write_scope",
        "status",
    ],
    "output_fields": [
        "helper_id",
        "query_scope",
        "evidence_refs",
        "result_status",
        "notes",
    ],
    "allowed_result_status": sorted(ALLOWED_RESULT_STATUSES),
    "allowed_replacement_reasons": sorted(ALLOWED_REPLACEMENT_REASONS),
    "approved_read_roots": [path.relative_to(ROOT).as_posix() for path in APPROVED_READ_ROOTS],
    "support_write_root": "logs/support/",
}


class RetrievalHelperError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")


def _path_hint(path: Path | None) -> str:
    return f" ({path})" if path else ""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise RetrievalHelperError(f"Missing file{_path_hint(path)}") from exc
    except json.JSONDecodeError as exc:
        raise RetrievalHelperError(f"Malformed JSON{_path_hint(path)}: {exc}") from exc


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False) + "\n")


def _obj(data: Any, *, path: Path | None = None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RetrievalHelperError(f"JSON root must be an object{_path_hint(path)}")
    return dict(data)


def _s(data: dict[str, Any], field: str, *, path: Path | None = None, allow_empty: bool = False) -> str:
    value = data.get(field)
    if not isinstance(value, str):
        raise RetrievalHelperError(f"Field '{field}' must be a string{_path_hint(path)}")
    text = value.strip()
    if not text and not allow_empty:
        raise RetrievalHelperError(f"Field '{field}' must not be empty{_path_hint(path)}")
    return text


def _i(data: dict[str, Any], field: str, *, path: Path | None = None, min_value: int | None = None) -> int:
    value = data.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RetrievalHelperError(f"Field '{field}' must be an integer{_path_hint(path)}")
    if min_value is not None and value < min_value:
        raise RetrievalHelperError(f"Field '{field}' must be >= {min_value}{_path_hint(path)}")
    return value


def _li(data: dict[str, Any], field: str, *, path: Path | None = None) -> list[str]:
    value = data.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        raise RetrievalHelperError(f"Field '{field}' must be a list{_path_hint(path)}")
    out: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            raise RetrievalHelperError(f"Field '{field}' item {idx} must be a string{_path_hint(path)}")
        text = item.strip()
        if not text:
            raise RetrievalHelperError(f"Field '{field}' item {idx} must not be empty{_path_hint(path)}")
        out.append(text)
    return out


def _parse_iso(value: str, *, path: Path | None = None, field: str = "timestamp") -> datetime:
    text = value.strip()
    raw = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise RetrievalHelperError(f"Field '{field}' must be ISO-8601{_path_hint(path)}: {exc}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _scope_to_path(scope: str) -> Path:
    candidate = Path(scope)
    if candidate.is_absolute():
        return candidate.resolve()
    return (ROOT / candidate).resolve()


def _scope_to_ref(scope: str) -> str:
    return Path(scope).as_posix().rstrip("/")


def _path_to_ref(path: Path, *, line: int | None = None) -> str:
    try:
        rel = path.resolve().relative_to(ROOT)
        ref = rel.as_posix()
    except Exception:
        ref = path.resolve().as_posix()
    if line is not None:
        return f"{ref}#L{line}"
    return ref


def _is_under(path: Path, root: Path) -> bool:
    path = path.resolve()
    root = root.resolve()
    return path == root or root in path.parents


def _normalize_write_scope(value: Any, *, path: Path | None = None) -> list[str]:
    if isinstance(value, str):
        scopes = [value]
    elif isinstance(value, list):
        scopes = value
    else:
        raise RetrievalHelperError(f"Field 'write_scope' must be a string or list of strings{_path_hint(path)}")
    out: list[str] = []
    for idx, item in enumerate(scopes):
        if not isinstance(item, str):
            raise RetrievalHelperError(f"Field 'write_scope' item {idx} must be a string{_path_hint(path)}")
        text = item.strip()
        if not text:
            raise RetrievalHelperError(f"Field 'write_scope' item {idx} must not be empty{_path_hint(path)}")
        normalized = text.replace("\\", "/")
        scope_path = _scope_to_path(normalized)
        if not (normalized.startswith("logs/support/") or normalized.startswith("memory/drafts/")):
            raise RetrievalHelperError(
                f"Field 'write_scope' item {idx} must be a support lane under logs/support/ or memory/drafts/{_path_hint(path)}"
            )
        if not _is_under(scope_path, ROOT):
            raise RetrievalHelperError(
                f"Field 'write_scope' item {idx} must stay inside the repository root{_path_hint(path)}"
            )
        out.append(normalized)
    return out


def _scope_allowed(scope: Path, allowed_roots: Iterable[Path]) -> bool:
    for root in allowed_roots:
        if _is_under(scope, root):
            return True
    return False


def _validate_read_scope(value: Any, *, path: Path | None = None) -> list[str]:
    if value is None:
        return [root.relative_to(ROOT).as_posix() for root in APPROVED_READ_ROOTS]
    if isinstance(value, str):
        scopes = [value]
    elif isinstance(value, list):
        scopes = value
    else:
        raise RetrievalHelperError(f"Field 'read_scope' must be a string or list of strings{_path_hint(path)}")

    normalized: list[str] = []
    for idx, item in enumerate(scopes):
        if not isinstance(item, str):
            raise RetrievalHelperError(f"Field 'read_scope' item {idx} must be a string{_path_hint(path)}")
        text = item.strip().replace("\\", "/")
        if not text:
            raise RetrievalHelperError(f"Field 'read_scope' item {idx} must not be empty{_path_hint(path)}")
        scope_path = _scope_to_path(text)
        if not _scope_allowed(scope_path, APPROVED_READ_ROOTS):
            raise RetrievalHelperError(
                f"Field 'read_scope' item {idx} is outside approved retrieval sources{_path_hint(path)}"
            )
        normalized.append(_scope_to_ref(text))
    return normalized


def _validate_lane(lane: str, write_scope: list[str], *, path: Path | None = None) -> str:
    lane = lane.strip().replace("\\", "/")
    if not lane:
        raise RetrievalHelperError(f"Field 'return_lane' must not be empty{_path_hint(path)}")
    if not (lane.startswith("logs/support/") or lane.startswith("memory/drafts/")):
        raise RetrievalHelperError(
            f"Field 'return_lane' must be a support lane under logs/support/ or memory/drafts/{_path_hint(path)}"
        )
    if lane not in write_scope:
        raise RetrievalHelperError(f"Field 'return_lane' must appear in write_scope{_path_hint(path)}")
    return lane


def _build_helper_id(*, requested_by: str, mandate_id: str, task_scope: str, query_scope: str) -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    digest = hashlib.sha1(
        f"{requested_by}|{mandate_id}|{task_scope}|{query_scope}|{stamp}".encode("utf-8")
    ).hexdigest()[:8]
    return f"{HELPER_TYPE}_{stamp}_{digest}"


def validate_retrieval_request(data: Any, *, path: Path | None = None, is_replacement: bool = False) -> dict[str, Any]:
    record = _obj(data, path=path)
    helper_type = _s(record, "helper_type", path=path)
    if helper_type != HELPER_TYPE:
        raise RetrievalHelperError(f"helper_type must be {HELPER_TYPE}{_path_hint(path)}")
    requested_by = _s(record, "requested_by", path=path)
    mandate_id = _s(record, "mandate_id", path=path)
    task_scope = _s(record, "task_scope", path=path)
    ttl_seconds = _i(record, "ttl_seconds", path=path, min_value=1)
    query_scope = _s(record, "query_scope", path=path)
    write_scope = _normalize_write_scope(record.get("write_scope"), path=path)
    if not any(scope.startswith("logs/support/") for scope in write_scope):
        raise RetrievalHelperError(
            f"Field 'write_scope' must include a support log lane under logs/support/{_path_hint(path)}"
        )
    return_lane = _validate_lane(_s(record, "return_lane", path=path), write_scope, path=path)
    read_scope = _validate_read_scope(record.get("read_scope"), path=path)

    normalized = dict(record)
    normalized["helper_type"] = helper_type
    normalized["requested_by"] = requested_by
    normalized["mandate_id"] = mandate_id
    normalized["task_scope"] = task_scope
    normalized["ttl_seconds"] = ttl_seconds
    normalized["query_scope"] = query_scope
    normalized["write_scope"] = write_scope
    normalized["return_lane"] = return_lane
    normalized["read_scope"] = read_scope

    if is_replacement:
        replaces_helper_id = _s(record, "replaces_helper_id", path=path)
        replacement_reason = _s(record, "replacement_reason", path=path)
        if replacement_reason not in ALLOWED_REPLACEMENT_REASONS:
            raise RetrievalHelperError(
                f"replacement_reason must be one of {sorted(ALLOWED_REPLACEMENT_REASONS)}{_path_hint(path)}"
            )
        normalized["replaces_helper_id"] = replaces_helper_id
        normalized["replacement_reason"] = replacement_reason

    return normalized


def build_instance_record(request: dict[str, Any], *, replaced_helper_id: str = "") -> dict[str, Any]:
    now = utc_now()
    created_at = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    expires_at = (now + timedelta(seconds=int(request["ttl_seconds"]))).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    helper_id = _build_helper_id(
        requested_by=request["requested_by"],
        mandate_id=request["mandate_id"],
        task_scope=request["task_scope"],
        query_scope=request["query_scope"],
    )
    instance = {
        "helper_id": helper_id,
        "helper_type": HELPER_TYPE,
        "mandate_id": request["mandate_id"],
        "task_scope": request["task_scope"],
        "created_at": created_at,
        "expires_at": expires_at,
        "write_scope": request["write_scope"],
        "status": "spawned",
        "requested_by": request["requested_by"],
        "ttl_seconds": int(request["ttl_seconds"]),
        "return_lane": request["return_lane"],
        "query_scope": request["query_scope"],
        "read_scope": request["read_scope"],
        "result_status": "",
        "evidence_refs": [],
        "notes": [],
        "outputs_refs": [],
        "replaced_helper_id": replaced_helper_id,
    }
    return instance


def _event_record(
    *,
    event_type: str,
    instance: dict[str, Any],
    request_path: Path,
    result_status: str = "",
    inputs_refs: list[str] | None = None,
    outputs_refs: list[str] | None = None,
    ttl_used: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "support_event_id": _build_helper_id(
            requested_by=instance.get("requested_by", "unknown"),
            mandate_id=instance.get("mandate_id", "unknown"),
            task_scope=instance.get("task_scope", "unknown"),
            query_scope=str(instance.get("query_scope", "")) or event_type,
        ),
        "event_type": event_type,
        "requested_by": instance.get("requested_by", "unknown"),
        "helper_id": instance.get("helper_id", ""),
        "helper_type": instance.get("helper_type", HELPER_TYPE),
        "mandate_id": instance.get("mandate_id", ""),
        "task_scope": instance.get("task_scope", ""),
        "status": instance.get("status", ""),
        "created_at": utc_now_iso(),
        "ttl_seconds": int(instance.get("ttl_seconds") or 0),
        "ttl_used": ttl_used if ttl_used is not None else 0,
        "return_lane": instance.get("return_lane", ""),
        "write_scope": instance.get("write_scope", []),
        "query_scope": instance.get("query_scope", ""),
        "read_scope": instance.get("read_scope", []),
        "inputs_refs": inputs_refs or [],
        "outputs_refs": outputs_refs or [],
        "result_status": result_status,
        "request_ref": _path_to_ref(request_path),
    }
    if extra:
        event.update(extra)
    return event


def _write_support_event(event: dict[str, Any]) -> None:
    _append_jsonl(EVENT_LOG, event)


def _instance_paths(helper_id: str) -> tuple[Path, Path]:
    instance_path = INSTANCE_DIR / f"{helper_id}.json"
    artifact_dir = ARTIFACT_DIR
    return instance_path, artifact_dir


def _validate_instance(data: Any, *, path: Path | None = None) -> dict[str, Any]:
    instance = _obj(data, path=path)
    if instance.get("helper_type") != HELPER_TYPE:
        raise RetrievalHelperError(f"helper_type must be {HELPER_TYPE}{_path_hint(path)}")
    _s(instance, "helper_id", path=path)
    _s(instance, "mandate_id", path=path)
    _s(instance, "task_scope", path=path)
    _s(instance, "created_at", path=path)
    _s(instance, "expires_at", path=path)
    _s(instance, "status", path=path)
    if instance["status"] not in ALLOWED_INSTANCE_STATUSES:
        raise RetrievalHelperError(f"Unsupported helper status{_path_hint(path)}: {instance['status']}")
    instance["write_scope"] = _normalize_write_scope(instance.get("write_scope"), path=path)
    instance["query_scope"] = _s(instance, "query_scope", path=path)
    instance["return_lane"] = _validate_lane(_s(instance, "return_lane", path=path), instance["write_scope"], path=path)
    instance["ttl_seconds"] = _i(instance, "ttl_seconds", path=path, min_value=1)
    instance["read_scope"] = _validate_read_scope(instance.get("read_scope"), path=path)
    return instance


def _search_scope(scope: str, query_scope: str) -> tuple[list[str], list[str]]:
    scope_path = _scope_to_path(scope)
    if not scope_path.exists():
        return [], [f"missing:{_path_to_ref(scope_path)}"]

    refs: list[str] = []
    notes: list[str] = []
    query_text = query_scope.strip().lower()
    tokens = [token for token in re.findall(r"[A-Za-z0-9_\-./:]+", query_text) if len(token) >= 3]

    targets: list[Path] = []
    if scope_path.is_file():
        targets = [scope_path]
    else:
        targets = [path for path in sorted(scope_path.rglob("*")) if path.is_file()]

    for file_path in targets:
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            notes.append(f"skipped_non_utf8:{_path_to_ref(file_path)}")
            continue
        except OSError as exc:
            notes.append(f"read_error:{_path_to_ref(file_path)}:{exc.__class__.__name__}")
            continue

        matched_lines = 0
        for lineno, line in enumerate(text.splitlines(), start=1):
            lower = line.lower()
            hit = query_text in lower if query_text else False
            if not hit and tokens:
                hit = any(token in lower for token in tokens)
            if hit:
                matched_lines += 1
                refs.append(_path_to_ref(file_path, line=lineno))
        if matched_lines:
            notes.append(f"matched:{_path_to_ref(file_path)}:{matched_lines}")

    return refs, notes


def _collect_evidence(read_scope: list[str], query_scope: str) -> tuple[list[str], list[str], list[str]]:
    evidence_refs: list[str] = []
    notes: list[str] = []
    warnings: list[str] = []

    for scope in read_scope:
        scope_refs, scope_notes = _search_scope(scope, query_scope)
        evidence_refs.extend(scope_refs)
        notes.extend(scope_notes)

    unique_refs = list(dict.fromkeys(sorted(evidence_refs)))
    if not unique_refs:
        notes.append("no_evidence_found")
    for note in notes:
        if note.startswith("missing:") or note.startswith("read_error:"):
            warnings.append(note)
    return unique_refs, notes, warnings


def _output_target(instance: dict[str, Any]) -> Path:
    lane = _scope_to_path(str(instance["return_lane"]))
    if lane.suffix:
        return lane
    if lane.exists() and lane.is_file():
        return lane
    lane.mkdir(parents=True, exist_ok=True)
    return lane / f"{instance['helper_id']}_result.json"


def _can_write(target: Path, write_scope: list[str]) -> bool:
    if _is_under(target, LOG_ROOT):
        return True
    for scope in write_scope:
        scope_path = _scope_to_path(scope)
        if _is_under(target, scope_path):
            return True
    return False


def spawn_helper(request_path: Path) -> tuple[dict[str, Any], Path]:
    request = validate_retrieval_request(_load_json(request_path), path=request_path, is_replacement=False)
    instance = build_instance_record(request)
    instance_path, _ = _instance_paths(instance["helper_id"])
    if not _can_write(instance_path, instance["write_scope"]):
        raise RetrievalHelperError(f"instance path {instance_path} is outside write_scope{_path_hint(request_path)}")
    _write_json(instance_path, instance)
    _write_support_event(
        _event_record(
            event_type="spawn",
            instance=instance,
            request_path=request_path,
            inputs_refs=[_path_to_ref(request_path)],
            outputs_refs=[_path_to_ref(instance_path)],
            ttl_used=0,
            extra={"status": "spawned"},
        )
    )
    return instance, instance_path


def run_helper(instance_path: Path) -> tuple[dict[str, Any], Path]:
    instance = _validate_instance(_load_json(instance_path), path=instance_path)
    now = utc_now()
    created_at = _parse_iso(instance["created_at"], path=instance_path, field="created_at")
    expires_at = _parse_iso(instance["expires_at"], path=instance_path, field="expires_at")
    ttl_used = max(0, int((now - created_at).total_seconds()))

    if now > expires_at:
        instance["status"] = "expired"
        artifact = {
            "helper_id": instance["helper_id"],
            "query_scope": instance["query_scope"],
            "evidence_refs": [],
            "result_status": "blocked",
            "notes": ["ttl_expired"],
        }
        output_path = _output_target(instance)
        if not _can_write(output_path, instance["write_scope"]):
            raise RetrievalHelperError(
                f"output path {output_path} is outside write_scope{_path_hint(instance_path)}"
            )
        _write_json(output_path, artifact)
        _write_json(instance_path, instance | artifact | {"status": "blocked", "ttl_used": ttl_used})
        _write_support_event(
            _event_record(
                event_type="block",
                instance=instance,
                request_path=instance_path,
                result_status="blocked",
                inputs_refs=[_path_to_ref(instance_path)],
                outputs_refs=[_path_to_ref(output_path)],
                ttl_used=ttl_used,
                extra={"blocking_reason": "ttl_expired", "status": "blocked"},
            )
        )
        return artifact, output_path

    evidence_refs, notes, warnings = _collect_evidence(instance["read_scope"], instance["query_scope"])
    result_status = "complete"
    if warnings:
        result_status = "partial" if evidence_refs else "blocked"
    if not evidence_refs and not warnings:
        result_status = "none_found"

    artifact_notes = list(notes)
    if result_status == "partial":
        artifact_notes.append("partial_retrieval")
    elif result_status == "blocked":
        artifact_notes.append("blocked_retrieval")

    artifact = {
        "helper_id": instance["helper_id"],
        "query_scope": instance["query_scope"],
        "evidence_refs": evidence_refs,
        "result_status": result_status,
        "notes": artifact_notes,
    }
    output_path = _output_target(instance)
    if not _can_write(output_path, instance["write_scope"]):
        raise RetrievalHelperError(f"output path {output_path} is outside write_scope{_path_hint(instance_path)}")

    _write_json(output_path, artifact)
    instance.update(
        {
            "status": result_status,
            "result_status": result_status,
            "evidence_refs": evidence_refs,
            "notes": artifact_notes,
            "outputs_refs": [_path_to_ref(output_path)],
            "ttl_used": ttl_used,
            "last_run_at": utc_now_iso(),
        }
    )
    _write_json(instance_path, instance)
    _write_support_event(
        _event_record(
            event_type="complete" if result_status in {"complete", "partial", "none_found"} else "block",
            instance=instance,
            request_path=instance_path,
            result_status=result_status,
            inputs_refs=[_path_to_ref(instance_path)],
            outputs_refs=[_path_to_ref(output_path)],
            ttl_used=ttl_used,
            extra={"status": result_status},
        )
    )
    return artifact, output_path


def replace_helper(request_path: Path) -> tuple[dict[str, Any], Path]:
    request = validate_retrieval_request(_load_json(request_path), path=request_path, is_replacement=True)
    replaced_helper_id = request["replaces_helper_id"]
    replaced_instance_path = INSTANCE_DIR / f"{replaced_helper_id}.json"
    old_instance: dict[str, Any] | None = None
    if replaced_instance_path.exists():
        old_instance = _validate_instance(_load_json(replaced_instance_path), path=replaced_instance_path)
        old_instance["status"] = "replaced"
        old_instance["replaced_by"] = request_path.as_posix()
        old_instance["replaced_at"] = utc_now_iso()
        _write_json(replaced_instance_path, old_instance)

    instance = build_instance_record(request, replaced_helper_id=replaced_helper_id)
    instance_path, _ = _instance_paths(instance["helper_id"])
    if not _can_write(instance_path, instance["write_scope"]):
        raise RetrievalHelperError(f"instance path {instance_path} is outside write_scope{_path_hint(request_path)}")
    _write_json(instance_path, instance)
    _write_support_event(
        _event_record(
            event_type="replace",
            instance=instance,
            request_path=request_path,
            inputs_refs=[_path_to_ref(request_path), _path_to_ref(replaced_instance_path)],
            outputs_refs=[_path_to_ref(instance_path)],
            ttl_used=0,
            extra={
                "status": "replaced",
                "replacement_reason": request["replacement_reason"],
                "replaces_helper_id": replaced_helper_id,
            },
        )
    )
    return instance, instance_path


def print_contract() -> int:
    print(json.dumps(CONTRACT, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieval helper for bounded support fetching.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("contract", help="Print the exact retrieval helper contract.")

    spawn_parser = subparsers.add_parser("spawn", help="Spawn retrieval_helper_2b from a request JSON file.")
    spawn_parser.add_argument("request_json")

    run_parser = subparsers.add_parser("run", help="Run retrieval_helper_2b from a helper instance JSON file.")
    run_parser.add_argument("instance_json")

    replace_parser = subparsers.add_parser("replace", help="Replace an existing retrieval helper instance.")
    replace_parser.add_argument("request_json")

    args = parser.parse_args()

    try:
        if args.command == "contract":
            return print_contract()
        if args.command == "spawn":
            instance, instance_path = spawn_helper(Path(args.request_json))
            print(instance_path)
            return 0
        if args.command == "run":
            artifact, output_path = run_helper(Path(args.instance_json))
            print(output_path)
            return 0
        if args.command == "replace":
            instance, instance_path = replace_helper(Path(args.request_json))
            print(instance_path)
            return 0
    except RetrievalHelperError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
