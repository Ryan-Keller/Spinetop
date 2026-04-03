#!/usr/bin/env python
"""Create a new expert and its memory instance from templates.

Idempotent behavior:
- Existing directories are left in place.
- Existing files are not overwritten.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
EXPERTS = ROOT / "experts"
MEMORY_INSTANCES = ROOT / "memory" / "instances"


def _snake_case_name(name: str) -> str:
    return name.strip().lower()


def _validate_name(name: str) -> None:
    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise ValueError("expert_name must be snake_case: [a-z0-9_]+")


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="ascii") as f:
        return json.load(f)


def _write_json_if_missing(path: Path, data: dict) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _copy_text_template_if_missing(src: Path, dst: Path, substitutions: dict[str, str]) -> None:
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="ascii")
    for key, value in substitutions.items():
        text = text.replace(key, value)
    dst.write_text(text, encoding="ascii")


def _ensure_dirs(base: Path, dirs: list[str]) -> None:
    for d in dirs:
        (base / d).mkdir(parents=True, exist_ok=True)


def create_expert(expert_name: str) -> None:
    expert_name = _snake_case_name(expert_name)
    _validate_name(expert_name)

    timestamp = datetime.now().isoformat(timespec="seconds")

    expert_template = TEMPLATES / "expert_template"
    memory_template = TEMPLATES / "memory_instance_template"

    expert_dir = EXPERTS / expert_name
    memory_dir = MEMORY_INSTANCES / expert_name

    # Ensure required directories exist.
    _ensure_dirs(expert_dir, ["workspace", "logs"])
    memory_dir.mkdir(parents=True, exist_ok=True)

    # Profile metadata (derived from template defaults).
    profile_template = _read_json(expert_template / "profile.json")
    profile = {
        **profile_template,
        "name": expert_name,
        "display_name": expert_name.replace("_", " ").title(),
        "created_at": timestamp,
    }
    _write_json_if_missing(expert_dir / "profile.json", profile)

    # Simple markdown templates.
    substitutions = {
        "{{expert_name}}": expert_name,
        "{{date}}": datetime.now().date().isoformat(),
    }
    _copy_text_template_if_missing(expert_template / "goals.md", expert_dir / "goals.md", substitutions)
    _copy_text_template_if_missing(expert_template / "notes.md", expert_dir / "notes.md", substitutions)

    # Memory instance templates.
    memory_template_json = _read_json(memory_template / "memory.json")
    memory_json = {
        **memory_template_json,
        "expert_name": expert_name,
        "created_at": timestamp,
    }
    _write_json_if_missing(memory_dir / "memory.json", memory_json)

    lessons_template_json = _read_json(memory_template / "lessons_candidate.json")
    lessons_json = {
        **lessons_template_json,
        "expert_name": expert_name,
        "created_at": timestamp,
    }
    _write_json_if_missing(memory_dir / "lessons_candidate.json", lessons_json)

    _copy_text_template_if_missing(
        memory_template / "journal.md", memory_dir / "journal.md", substitutions
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new expert from templates.")
    parser.add_argument("expert_name", help="snake_case expert name")
    args = parser.parse_args()

    create_expert(args.expert_name)


if __name__ == "__main__":
    main()
