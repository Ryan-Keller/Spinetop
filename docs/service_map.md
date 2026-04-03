# Service Map

This document describes how services are tracked and validated in Spinetop. It is intentionally local-first and avoids hardcoded ports or internet dependencies.

## Roles In This Doc

Spinetop
- Canonical workspace for service definitions and approved health checks.

Spinelab
- Reflective and experimental workspace for proposed service changes.

Experts
- Maintain scoped service knowledge and propose updates.
- Do not rewrite collective memory without promotion.

Codex
- Implements service changes and repair steps.
- Does not define identity or policy.

## Principles

- Local-first: services are validated on the local machine.
- Explicit config: host/port values live in config or service map files.
- Conservative control: no automatic installs or system service changes.

## Service Registry

Each service should have:
- Name and role
- Local host and port placeholders
- Health check method (process or HTTP)
- Start helper (optional, conservative)

## In-Scope Services

- Ollama
- Honcho
- Open WebUI

## Health Check Expectations

- Ollama: HTTP health or process check depending on config.
- Honcho: process check or local endpoint if enabled.
- Open WebUI: HTTP reachability on configured port.

## Workflow

1. Update the services map/config with local host and port values.
2. Run the status script to get a readable summary.
3. Use optional start helpers only when you explicitly choose to.

## Memory Layers (Service Context)

- Canonical memory (Spinetop): approved service map entries and rules.
- Project memory: service notes tied to a specific initiative.
- Experimental memory (Spinelab): trial configs or checks.
- Local scratch: temporary commands and test output.

## Promotion Pipeline For Service Changes

1. Proposal in Spinelab or expert workspace.
2. Review for doctrine alignment, dependencies, and blast radius.
3. Promotion into Spinetop if approved.
4. Adoption by experts on next sync.

## Blast-Radius Containment

- Health checks do not mutate system state.
- Start helpers are opt-in and minimal.
- Changes to configs are reviewed before promotion.

## Recovery Philosophy (Service Context)

- Prefer reversible changes and explicit scripts.
- Stabilize before attempting repairs.
- Promote only after service behavior is stable.

## Why One Canonical Workspace

Spinetop anchors the service map so service identity and expectations cannot drift across workspaces.
