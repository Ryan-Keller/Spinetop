# Spinetop UI Wiring Plan v1

This document defines a docs-first UI wiring plan for the current stable and near-stable flows in Spinetop.

It is intentionally conservative.
It does not redesign backend architecture, add autonomy, add truth authority, or ask for broad styling work.

If this document conflicts with [`doctrine.md`](./doctrine.md), [`state_machine_v1.md`](./state_machine_v1.md), [`support_orchestration_contract_v1.md`](./support_orchestration_contract_v1.md), or [`autonomy_phase_plan_v1.md`](./autonomy_phase_plan_v1.md), those documents win.

## Wiring Rules

- Prefer read-only surfaces first.
- Wire directly to existing files, logs, and small API endpoints before inventing new backend shape.
- Keep UI surfaces thin and explicit about source of truth.
- Never let the UI become a hidden approval layer.
- Never treat UI display as evidence of legitimacy.
- If a surface implies a write, approval, or admission, it must wait for a separate governed path.

## Minimum Useful Surfaces

These are the smallest UI surfaces worth wiring now.

| Surface | Minimum useful UI | Source script or file | Read-only or action-capable | Stable enough to wire now? | Notes |
|---|---|---|---|---|---|
| System state | Compact status cards for `return_all`, nanny temperature, dispatch counts, promotion backlog, and collective count | `scripts/dashboard_api.py`, `logs/governance/return_all.json`, `logs/nanny/item_world_status.json`, `memory/dispatch/`, `memory/promotion/`, `memory/collective/` | Read-only | Yes | This is already the best-supported live surface. Keep it as the default landing view. |
| Sentinel runs | Run list and run detail view with `run_id`, `mode`, `status`, `summary`, `evidence_refs`, and `confidence` | `scripts/run_hermes_v1.py`, `docs/hermes_v1_run_schema.md`, optional captured stdout artifacts | Read-only | Yes | Wire as a viewer first. Do not turn it into an executor control. |
| Petition drafts | Draft list and draft detail view showing `petition_id`, `petition_kind`, `requested_action`, `summary`, and `source_run_id` | `scripts/hermes_to_petition.py`, `memory/drafts/` | Read-only | Yes | This is a stable, low-risk inspection surface. Draft creation remains outside the UI for now. |
| Support helper activity | Event stream and helper instance panel showing spawn, replace, complete, failed, blocked, and expired states | `scripts/support_orchestration.py`, `logs/support/orchestration/events.jsonl`, `logs/support/orchestration/instances/`, `logs/support/orchestration/artifacts/` | Read-only | Yes | Good candidate for a live activity feed. Keep it operational, not managerial. |
| Governance state | Return-all banner plus dispatch queue summary split by pending, approved, deferred, and rejected | `scripts/dashboard_api.py`, `logs/governance/return_all.json`, `memory/dispatch/` | Read-only | Yes | This is safe to wire as a status surface only. No toggle buttons yet. |
| Mirror-door test summaries | Test run summary with pass/fail counts, blocked cases, unexpected accepts, and failed categories | `scripts/test_mirror_door_contracts.py`, `tests/mirror_door_contracts/` | Read-only | Yes | Good for a small QA/status page or a section in the system dashboard. |

## Recommended UI Surface Mapping

### 1. Default Dashboard

Use this as the main landing surface.

Show:

- system state
- governance state
- a small Sentinel run summary strip
- a small support activity strip

This should remain a read-only overview.

### 2. Sentinel Run Viewer

Keep this as a detail page or panel.

Show:

- one run at a time
- evidence refs
- mode and status
- confidence
- recommendation

This is the right place for the manual runner output, not for execution buttons.

### 3. Draft Inbox

Show petition drafts as records.

Useful fields:

- petition ID
- petition kind
- requested action
- source run ID
- evidence refs
- draft status

The UI should let an operator inspect drafts, not silently submit them.

### 4. Support Activity Feed

Show helper lifecycle events from the support orchestration logs.

Useful fields:

- helper ID
- helper type
- mandate ID
- task scope
- status
- TTL
- return lane

This surface is operational telemetry, not control authority.

### 5. Governance Panel

Show the current return-all state and dispatch queue.

Useful fields:

- return-all enabled state
- issued by
- issued at
- reason
- dispatch counts
- recent pending petitions

This should remain display-only until a separate governed control path exists.

### 6. Mirror-Door Test Summary

Show the latest contract test outcome and category breakdown.

Useful fields:

- total cases
- correctly blocked
- validly accepted
- unexpected accepts
- unexpected errors

This can live in a QA tab or a footer card on the dashboard.

## Surfaces Safe To Wire Now

- System state
- Sentinel runs, as read-only run artifacts with legacy `hermes` storage compatibility
- Petition drafts, as read-only draft records
- Support helper activity, as read-only operational telemetry
- Governance state, as read-only status
- Mirror-door test summaries

These are safe because the source files already exist, the flows are bounded, and the UI only needs to present state.

## Surfaces That Must Wait

- Any button that submits a petition
- Any button that approves, rejects, or admits truth-adjacent records
- Any UI path that spawns, replaces, or retires helpers directly
- Any UI path that toggles return-all or other governance brakes
- Any UI path that triggers Honcho mirroring
- Any UI path that writes to collective memory
- Any UI path that auto-runs beyond a manual operator action

These surfaces must wait because they would turn the UI into a control plane.

## Existing UI Shells

The current React pages already suggest a sane division of labor:

- [`ui/src/pages/Dashboard.tsx`](../ui/src/pages/Dashboard.tsx) is the best fit for system state and governance summary.
- [`ui/src/pages/HonchoItemWorld.tsx`](../ui/src/pages/HonchoItemWorld.tsx) is the best fit for mirror-related summaries and QA-style event exploration.
- [`ui/src/pages/AgentMemoryTriadPage.tsx`](../ui/src/pages/AgentMemoryTriadPage.tsx) and [`ui/src/pages/EmissaryReturnGatePage.tsx`](../ui/src/pages/EmissaryReturnGatePage.tsx) are narrative/demo surfaces and should not be treated as authoritative control surfaces.

## Next Smallest Helper After `retrieval_helper_2b`

The next smallest helper implementation should be `runner_helper_2b`.

Why this one:

- `retrieval_helper_2b` fetches and bundles evidence.
- `runner_helper_2b` executes one bounded procedural task and returns a receipt.
- That makes it the smallest practical step from "find evidence" to "do one narrow thing with it" without inventing broader orchestration.

### What `runner_helper_2b` should do

- run one bounded procedural task
- report step completion
- return an operational receipt
- stop when the mandate is complete
- write only to its declared support lane
- stay disposable and replaceable

### What `runner_helper_2b` should not do

- invent new subgoals
- run open-ended loops
- choose new work on its own
- rank truth or legitimacy
- approve petitions
- admit records to collective
- write to Honcho
- become a strategist or hidden control layer

### Why it matters for UI wiring

`runner_helper_2b` gives the UI a clean, bounded activity model:

- one task
- one receipt
- one status trail

That is much easier to render safely than a generalized autonomous agent.

## Smallest Next Implementation Step

Wire the default dashboard to the existing read-only state sources first:

1. `scripts/dashboard_api.py` for system state and governance state.
2. `scripts/run_hermes_v1.py` outputs for Sentinel run summaries.
3. `scripts/hermes_to_petition.py` and `memory/drafts/` for draft visibility.
4. `scripts/support_orchestration.py` event logs for helper activity.
5. `scripts/test_mirror_door_contracts.py` summary output for the mirror-door QA strip.

If we do only one thing next, do the system state + governance strip first.
That gives the UI an honest, low-risk baseline without expanding backend power.
