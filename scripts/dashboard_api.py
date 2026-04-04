from __future__ import annotations

import json
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from flask import Flask, jsonify, request

from governance_utils import read_nanny_state
from review_and_submit_petition import build_review_payload, validate_draft_petition
from run_hermes_v1 import validate_response_object

ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG = ROOT / "logs" / "topology" / "events.jsonl"
HERMES_RUNS_DIR = ROOT / "logs" / "hermes" / "runs"
MEMORY_DIR = ROOT / "memory"
DISPATCH_DIR = MEMORY_DIR / "dispatch"
GOVERNANCE_DIR = ROOT / "logs" / "governance"
SUPPORT_ORCHESTRATION_DIR = ROOT / "logs" / "support" / "orchestration"
SUPPORT_RETRIEVAL_DIR = ROOT / "logs" / "support" / "retrieval"
HONCHO_BASE = "http://127.0.0.1:8000"
WORKSPACE_ID = "shared-coordination"
IN_MEMORY_EVENTS: list[dict[str, Any]] = []
IN_MEMORY_EVENTS_MAX = 200
MIRROR_DOOR_CACHE: dict[str, Any] = {"signature": "", "value": None}

KNOWN_PEERS = [
    {"id": "desktop", "metadata": {"created_by": "system"}},
    {"id": "laptop", "metadata": {"created_by": "system"}},
]

app = Flask(__name__)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_event(raw: dict[str, Any]) -> dict[str, Any]:
    allowed_types = {
        "hermes_write",
        "watcher_scan",
        "promote",
        "approve",
        "honcho_bridge",
        "hopper_clean",
        "honcho_bridge_file",
        "honcho_bridge_watcher",
        "dispatch_petition",
        "item_world_nanny",
    }
    allowed_statuses = {
        "created",
        "promotable",
        "success",
        "error",
        "skipped",
        "partial",
        "archived",
        "quarantined",
        "pending",
        "approved",
        "deferred",
        "rejected",
        "cool",
        "warm",
        "hot",
        "paused",
    }
    raw_type = raw.get("event_type") or "watcher_scan"
    raw_status = raw.get("status") or "created"
    return {
        "timestamp": str(raw.get("timestamp") or iso_now()),
        "event_type": raw_type if raw_type in allowed_types else "watcher_scan",
        "record_name": str(raw.get("record_name") or "unknown"),
        "status": raw_status if raw_status in allowed_statuses else "created",
        "detail": str(raw.get("detail") or ""),
        "machine": str(raw.get("machine") or "local"),
    }


def read_recent_events(limit: int = 50) -> list[dict]:
    rows: list[dict] = []
    if EVENT_LOG.exists():
        lines = EVENT_LOG.read_text(encoding="utf-8").splitlines()
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    if IN_MEMORY_EVENTS:
        rows.extend(IN_MEMORY_EVENTS[-limit:])
    if not rows and MEMORY_DIR.exists():
        # Minimal fallback: surface memory directory presence as a scan event
        rows.append({
            "timestamp": iso_now(),
            "event_type": "watcher_scan",
            "record_name": "memory_dir",
            "status": "success",
            "detail": f"memory files: {len(list(MEMORY_DIR.glob('*')))}",
            "machine": "local",
        })
    normalized = [normalize_event(row) for row in rows]
    return normalized[-limit:]


def honcho_post(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        HONCHO_BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def safe_honcho_post(path: str, payload: dict) -> dict:
    try:
        return honcho_post(path, payload)
    except Exception as e:
        return {"error": str(e)}


def normalize_session(raw: dict[str, Any]) -> dict[str, Any]:
    meta = raw.get("metadata") or {}
    return {
        "id": str(raw.get("id") or "unknown"),
        "is_active": bool(raw.get("is_active", False)),
        "metadata": {
            "agent_id": str(meta.get("agent_id") or "unknown"),
            "workspace": str(meta.get("workspace") or WORKSPACE_ID),
        },
        "created_at": str(raw.get("created_at") or iso_now()),
    }


def normalize_peer(raw: dict[str, Any]) -> dict[str, Any]:
    meta = raw.get("metadata") or {}
    return {
        "id": str(raw.get("id") or "unknown"),
        "metadata": {
            "created_by": str(meta.get("created_by") or "system"),
        },
    }


def get_sessions(limit: int = 10) -> tuple[int, list[dict]]:
    sessions = safe_honcho_post(f"/v3/workspaces/{WORKSPACE_ID}/sessions/list", {})
    items = sessions.get("items") if isinstance(sessions, dict) else None
    if isinstance(items, list) and items:
        normalized = [normalize_session(row) for row in items[:limit]]
        total = sessions.get("total", len(items))
        return int(total or 0), normalized
    return 0, []


def get_peers(limit: int = 10) -> tuple[int, list[dict]]:
    peers = safe_honcho_post(f"/v3/workspaces/{WORKSPACE_ID}/peers/list", {})
    items = peers.get("items") if isinstance(peers, dict) else None
    if isinstance(items, list) and items:
        normalized = [normalize_peer(row) for row in items[:limit]]
        total = peers.get("total", len(items))
        return int(total or 0), normalized
    normalized = [normalize_peer(row) for row in KNOWN_PEERS[:limit]]
    return len(normalized), normalized


def get_events(limit: int = 50) -> list[dict]:
    return read_recent_events(limit)


def log_topology_event(event_type: str, record_name: str, status: str, detail: str) -> None:
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": iso_now(),
        "machine": "Spinetop",
        "event_type": event_type,
        "record_name": record_name,
        "status": status,
        "detail": detail,
    }
    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_return_all_state() -> dict[str, Any]:
    path = GOVERNANCE_DIR / "return_all.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "ok": True,
                "enabled": bool(data.get("enabled", False)),
                "issued_by": str(data.get("issued_by") or "operator"),
                "issued_at": str(data.get("issued_at") or ""),
                "reason": str(data.get("reason") or ""),
                "allow_custodial_bypass": bool(data.get("allow_custodial_bypass", False)),
            }
        except Exception:
            pass
    return {
        "ok": True,
        "enabled": False,
        "issued_by": "operator",
        "issued_at": "",
        "reason": "",
        "allow_custodial_bypass": False,
    }


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def is_bypass_allowed(petition: dict[str, Any], return_all: dict[str, Any]) -> bool:
    if not return_all.get("allow_custodial_bypass"):
        return False
    spawn_authority = str(petition.get("spawn_authority") or "")
    dispatch_mode = str(petition.get("dispatch_mode") or "")
    entry_class = str(petition.get("entry_class") or "")
    return (
        spawn_authority == "custodial"
        and dispatch_mode == "rapid"
        and entry_class in {"self_heal", "repair"}
    )


def normalize_petition(raw: dict[str, Any], status: str, filename: str, return_all: dict[str, Any]) -> dict[str, Any]:
    petition_id = str(raw.get("petition_id") or "").strip()
    if not petition_id:
        petition_id = f"legacy:{filename}"
        log_topology_event("dispatch_petition", filename, "error", "missing petition_id")

    ask_count = raw.get("ask_count")
    if ask_count is None:
        asks = raw.get("asks")
        if isinstance(asks, list):
            ask_count = len(asks)
        else:
            ask_count = 1
    ask_count = int(ask_count)

    requires_operator_approval = raw.get("requires_operator_approval")
    if requires_operator_approval is None:
        requires_operator_approval = ask_count > 1

    spawn_authority = str(raw.get("spawn_authority") or "emissary")
    dispatch_mode = str(raw.get("dispatch_mode") or "normal")
    operator_id = str(raw.get("operator_id") or "")
    entry_class = str(raw.get("entry_class") or "normal")
    created_at = str(raw.get("created_at") or raw.get("timestamp_created") or iso_now())
    created_by = str(raw.get("created_by") or raw.get("agent_id") or "unknown")
    petition_kind = str(raw.get("petition_kind") or "").strip()
    if not petition_kind:
        petition_kind = "repair_request" if entry_class == "repair" else "self_heal_request" if entry_class == "self_heal" else "anomaly_review" if entry_class == "anomaly_review" else "memory_admission"
    requested_action = str(raw.get("requested_action") or "").strip()
    if not requested_action:
        requested_action = "repair" if petition_kind in {"repair_request", "self_heal_request"} else "operator_review" if petition_kind == "anomaly_review" else "admit_to_collective"
    risk_level = str(raw.get("risk_level") or ("high" if petition_kind in {"anomaly_review", "repair_request"} else "medium"))
    reason = str(raw.get("reason") or raw.get("task") or raw.get("summary") or "")
    evidence_refs = raw.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    related_record_id = str(raw.get("related_record_id") or "")
    related_petition_id = str(raw.get("related_petition_id") or "")
    cooldown_observed = raw.get("cooldown_observed")
    governance_notes = str(raw.get("governance_notes") or "")
    status_updated_at = str(raw.get("status_updated_at") or created_at or iso_now())
    source_host = str(raw.get("source_host") or "unknown")

    petition_status = status
    if return_all.get("enabled") and status == "pending" and not is_bypass_allowed(raw, return_all):
        issued_at = parse_iso(str(return_all.get("issued_at") or ""))
        updated_at = parse_iso(status_updated_at) or datetime.now(timezone.utc)
        if not issued_at or updated_at >= issued_at:
            petition_status = "deferred"
            requires_operator_approval = True

    return {
        "record_type": str(raw.get("record_type") or "dispatch_petition"),
        "petition_id": petition_id,
        "record_name": str(raw.get("record_name") or filename),
        "agent_id": str(raw.get("agent_id") or "unknown"),
        "created_by": created_by,
        "workspace": str(raw.get("workspace") or "unknown"),
        "source": str(raw.get("source") or "dispatch"),
        "timestamp_created": str(raw.get("timestamp_created") or created_at),
        "created_at": created_at,
        "summary": str(raw.get("summary") or ""),
        "task": str(raw.get("task") or ""),
        "confidence": float(raw.get("confidence") or 0.0),
        "promotion_candidate": bool(raw.get("promotion_candidate", False)),
        "payload_type": str(raw.get("payload_type") or "pattern"),
        "urgency": str(raw.get("urgency") or "normal"),
        "requires_emissary": bool(raw.get("requires_emissary", True)),
        "petition_status": petition_status,
        "status": petition_status,
        "ask_count": ask_count,
        "requires_operator_approval": bool(requires_operator_approval),
        "spawn_authority": spawn_authority,
        "dispatch_mode": dispatch_mode,
        "operator_id": operator_id,
        "status_updated_at": status_updated_at,
        "source_host": source_host,
        "entry_class": entry_class,
        "petition_kind": petition_kind,
        "reason": reason,
        "evidence_refs": evidence_refs,
        "requested_action": requested_action,
        "risk_level": risk_level,
        "related_record_id": related_record_id,
        "related_petition_id": related_petition_id,
        "cooldown_observed": cooldown_observed,
        "governance_notes": governance_notes,
    }


def read_dispatch_petitions() -> list[dict]:
    folders = [
        ("pending", DISPATCH_DIR / "pending"),
        ("approved", DISPATCH_DIR / "approved"),
        ("deferred", DISPATCH_DIR / "deferred"),
        ("rejected", DISPATCH_DIR / "rejected"),
    ]
    petitions: list[dict] = []
    seen_ids: dict[str, int] = {}
    logged_duplicates: set[str] = set()
    return_all = read_return_all_state()
    for status, folder in folders:
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                log_topology_event(
                    "dispatch_petition",
                    path.name,
                    "error",
                    "malformed json",
                )
                continue
            petition = normalize_petition(raw, status, path.name, return_all)
            pid = petition["petition_id"]
            if pid in seen_ids:
                seen_ids[pid] += 1
                if pid not in logged_duplicates:
                    log_topology_event(
                        "dispatch_petition",
                        path.name,
                        "error",
                        "duplicate petition_id across dispatch folders",
                    )
                    logged_duplicates.add(pid)
            else:
                seen_ids[pid] = 1
            petitions.append(petition)
    return petitions


def read_item_world_status() -> dict[str, Any]:
    status_path = ROOT / "logs" / "nanny" / "item_world_status.json"
    if status_path.exists():
        try:
            return json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "ok": True,
        "temperature": "cool",
        "burst_score": 0,
        "error_score": 0,
        "active_agent_warnings": [],
        "recommended_actions": [],
        "global_cooldown_seconds": 0,
    }


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def read_support_helper_activity(limit: int = 24) -> dict[str, Any]:
    lane_specs = [
        ("orchestration", SUPPORT_ORCHESTRATION_DIR / "instances"),
        ("retrieval", SUPPORT_RETRIEVAL_DIR / "instances"),
    ]
    items: list[tuple[int, dict[str, Any]]] = []
    lane_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()

    for lane, instance_dir in lane_specs:
        if not instance_dir.exists():
            continue
        for path in sorted(instance_dir.glob("*.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True):
            raw = _load_json_object(path)
            if not raw:
                continue
            item = {
                "lane": lane,
                "helper_id": str(raw.get("helper_id") or path.stem),
                "helper_type": str(raw.get("helper_type") or "unknown"),
                "mandate_id": str(raw.get("mandate_id") or ""),
                "task_scope": str(raw.get("task_scope") or ""),
                "status": str(raw.get("status") or "unknown"),
                "created_at": str(raw.get("created_at") or raw.get("updated_at") or ""),
                "expires_at": str(raw.get("expires_at") or ""),
                "source_file": _safe_relative_path(path),
            }
            lane_counts[lane] += 1
            status_counts[item["status"]] += 1
            items.append((path.stat().st_mtime_ns, item))

    items.sort(key=lambda pair: pair[0], reverse=True)
    return {
        "available": bool(items),
        "total": len(items),
        "lane_counts": dict(lane_counts),
        "status_counts": dict(status_counts),
        "items": [item for _, item in items[:limit]],
        "source_dirs": {
            "orchestration": _safe_relative_path(SUPPORT_ORCHESTRATION_DIR),
            "retrieval": _safe_relative_path(SUPPORT_RETRIEVAL_DIR),
        },
    }


def _mirror_door_signature(script_path: Path, fixture_root: Path) -> str:
    fixture_mtimes: list[int] = []
    if fixture_root.exists():
        for path in fixture_root.rglob("*.json"):
            if path.is_file():
                fixture_mtimes.append(path.stat().st_mtime_ns)
    return "|".join(
        [
            str(script_path.stat().st_mtime_ns if script_path.exists() else 0),
            str(fixture_root.stat().st_mtime_ns if fixture_root.exists() else 0),
            str(len(fixture_mtimes)),
            str(sum(fixture_mtimes)),
        ]
    )


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def _latest_json_files(directory: Path, limit: int) -> list[Path]:
    if not directory.exists():
        return []
    files = [path for path in directory.glob("*.json") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files[:limit]


def _safe_relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def read_hermes_runs(limit: int = 8) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in _latest_json_files(HERMES_RUNS_DIR, limit):
        source_path = _safe_relative_path(path)
        try:
            payload = _load_json(path)
        except Exception as exc:
            items.append({
                "ok": False,
                "source_path": source_path,
                "captured_at": _mtime_iso(path),
                "error": f"malformed json: {exc}",
            })
            continue

        if not isinstance(payload, dict):
            items.append({
                "ok": False,
                "source_path": source_path,
                "captured_at": _mtime_iso(path),
                "error": "run record must be a JSON object",
            })
            continue

        run_id = str(payload.get("run_id") or "").strip()
        mode = str(payload.get("mode") or "").strip()
        if not run_id or not mode:
            items.append({
                "ok": False,
                "source_path": source_path,
                "captured_at": _mtime_iso(path),
                "error": "run record missing run_id or mode",
            })
            continue

        ok, reason = validate_response_object(payload, run_id, mode)
        if not ok:
            items.append({
                "ok": False,
                "source_path": source_path,
                "captured_at": _mtime_iso(path),
                "error": reason,
            })
            continue

        items.append({
            "ok": True,
            "source_path": source_path,
            "captured_at": _mtime_iso(path),
            "run_id": run_id,
            "mode": mode,
            "status": str(payload.get("status") or ""),
            "summary": str(payload.get("summary") or ""),
            "evidence_refs": list(payload.get("evidence_refs") or []),
            "recommended_action": str(payload.get("recommended_action") or ""),
            "petition_kind": payload.get("petition_kind"),
            "confidence": float(payload.get("confidence") or 0.0),
            "classification": payload.get("classification"),
        })
    return items


def read_petition_draft_previews(limit: int = 8) -> list[dict[str, Any]]:
    drafts_dir = MEMORY_DIR / "drafts"
    return_all = read_return_all_state()
    nanny = read_nanny_state()
    items: list[dict[str, Any]] = []

    for path in _latest_json_files(drafts_dir, limit):
        source_path = _safe_relative_path(path)
        try:
            payload = _load_json(path)
            draft = validate_draft_petition(payload, path=path)
            preview = build_review_payload(
                draft,
                draft_path=path,
                return_all=return_all,
                nanny=nanny,
            )
        except Exception as exc:
            items.append({
                "ok": False,
                "source_path": source_path,
                "error": str(exc),
            })
            continue

        items.append({
            "ok": True,
            "source_path": source_path,
            "draft": {
                "petition_id": draft["petition_id"],
                "mode": draft["mode"],
                "petition_kind": draft["petition_kind"],
                "petition_type": draft["petition_type"],
                "requested_action": draft["requested_action"],
                "confidence": draft["confidence"],
                "source_run_id": draft["source_run_id"],
                "summary": draft["summary"],
                "evidence_refs": draft["evidence_refs"],
            },
            "review_preview": preview,
        })

    return items


def read_dispatch_counts() -> dict[str, int]:
    counts = {"pending": 0, "approved": 0, "deferred": 0, "rejected": 0}
    for petition in read_dispatch_petitions():
        status = str(petition.get("status") or "").strip()
        if status in counts:
            counts[status] += 1
    counts["total"] = sum(counts.values())
    return counts


def read_mirror_door_test_status() -> dict[str, Any]:
    script_path = ROOT / "scripts" / "test_mirror_door_contracts.py"
    fixture_root = ROOT / "tests" / "mirror_door_contracts"
    signature = _mirror_door_signature(script_path, fixture_root)
    cached_signature = str(MIRROR_DOOR_CACHE.get("signature") or "")
    cached_value = MIRROR_DOOR_CACHE.get("value")
    if cached_signature == signature and isinstance(cached_value, dict):
        return cached_value

    summary: dict[str, Any] = {
        "available": script_path.exists() and fixture_root.exists(),
        "script_path": "scripts/test_mirror_door_contracts.py",
        "fixture_root": "tests/mirror_door_contracts",
        "fixture_categories": [],
        "fixture_files": 0,
        "total": 0,
        "correctly_blocked": 0,
        "validly_accepted": 0,
        "unexpected_accept": 0,
        "unexpected_error": 0,
        "recent_failures": [],
    }
    if not summary["available"]:
        MIRROR_DOOR_CACHE["signature"] = signature
        MIRROR_DOOR_CACHE["value"] = summary
        return summary

    try:
        import test_mirror_door_contracts as mirror_tests
    except Exception as exc:  # pragma: no cover - import fallback only
        summary["available"] = False
        summary["error"] = f"unable to import mirror-door test script: {exc}"
        MIRROR_DOOR_CACHE["signature"] = signature
        MIRROR_DOOR_CACHE["value"] = summary
        return summary

    try:
        cases = list(mirror_tests.iter_case_files())
        results = [mirror_tests.run_case(case) for case in cases]
    except Exception as exc:
        summary["available"] = False
        summary["error"] = f"mirror-door test execution failed: {exc}"
        MIRROR_DOOR_CACHE["signature"] = signature
        MIRROR_DOOR_CACHE["value"] = summary
        return summary

    counts: Counter[str] = Counter(result.bucket for result in results)
    failures = [
        {
            "category": result.category,
            "case_id": result.case_id,
            "expected": result.expected,
            "actual": result.actual,
            "reason": result.reason,
            "attack_surface": result.attack_surface,
            "source_file": _safe_relative_path(result.source_file),
        }
        for result in results
        if result.bucket in {"unexpected_accept", "unexpected_error"}
    ]
    fixture_categories = sorted(path.name for path in fixture_root.iterdir() if path.is_dir())

    summary.update(
        {
            "fixture_categories": fixture_categories,
            "fixture_files": sum(1 for path in fixture_root.rglob("*.json") if path.is_file()),
            "total": len(results),
            "correctly_blocked": int(counts.get("correctly_blocked", 0)),
            "validly_accepted": int(counts.get("validly_accepted", 0)),
            "unexpected_accept": int(counts.get("unexpected_accept", 0)),
            "unexpected_error": int(counts.get("unexpected_error", 0)),
            "recent_failures": failures[:6],
            "generated_at": iso_now(),
        }
    )
    MIRROR_DOOR_CACHE["signature"] = signature
    MIRROR_DOOR_CACHE["value"] = summary
    return summary


@app.get("/api/status")
def api_status():
    sessions_total, sessions_items = get_sessions(10)
    peers_total, peers_items = get_peers(10)

    return jsonify({
        "ok": True,
        "workspace_id": WORKSPACE_ID,
        "honcho_sessions_total": sessions_total,
        "honcho_peers_total": peers_total,
        "honcho_sessions": sessions_items,
        "honcho_peers": peers_items,
        "events_recent": get_events(50),
        "return_all": read_return_all_state(),
        "nanny": read_item_world_status(),
        "dispatch_counts": read_dispatch_counts(),
        "support_helper_activity": read_support_helper_activity(),
        "mirror_door_test": read_mirror_door_test_status(),
    })


@app.get("/api/events")
def api_events():
    return jsonify({
        "ok": True,
        "items": get_events(200)
    })


@app.get("/api/dispatch")
def api_dispatch():
    return jsonify({
        "ok": True,
        "petitions": read_dispatch_petitions(),
    })


@app.get("/api/hermes/runs")
def api_hermes_runs():
    try:
        limit = max(1, min(20, int(request.args.get("limit", 8))))
    except Exception:
        limit = 8
    return jsonify({
        "ok": True,
        "source_root": _safe_relative_path(HERMES_RUNS_DIR),
        "items": read_hermes_runs(limit),
    })


@app.get("/api/petition-drafts")
def api_petition_drafts():
    try:
        limit = max(1, min(20, int(request.args.get("limit", 8))))
    except Exception:
        limit = 8
    return jsonify({
        "ok": True,
        "source_root": _safe_relative_path(MEMORY_DIR / "drafts"),
        "items": read_petition_draft_previews(limit),
    })


@app.get("/api/governance/return-all")
def api_governance_return_all():
    return jsonify(read_return_all_state())


@app.get("/api/item-world-status")
def api_item_world_status():
    return jsonify(read_item_world_status())


@app.post("/api/event")
def api_event_create():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}
    event = normalize_event(payload)
    IN_MEMORY_EVENTS.append(event)
    if len(IN_MEMORY_EVENTS) > IN_MEMORY_EVENTS_MAX:
        del IN_MEMORY_EVENTS[:-IN_MEMORY_EVENTS_MAX]
    return jsonify({
        "ok": True,
        "item": event,
        "total": len(IN_MEMORY_EVENTS),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5051, debug=False)
