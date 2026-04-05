# Support Orchestration Contract v1

This document defines a bounded support layer for disposable helper agents.
It is docs-first, fulfillment-biased, and non-authoritative.

It does not create autonomy, truth authority, governance, or UI.

If this document conflicts with [`doctrine.md`](./doctrine.md) or [`state_machine_v1.md`](./state_machine_v1.md), those docs win.

## Purpose

The support layer exists to:

- coordinate narrow helper work
- move bounded tasks through support lanes
- preserve evidence and return references
- keep helper labor disposable and replaceable
- prevent helper output from becoming a truth layer

The support layer does not exist to:

- define legitimacy
- define truth
- create governance decisions
- admit records to collective
- mirror to Honcho
- run open-ended loops
- provide a user-facing UI

## Actors

### Librarian

The librarian is trapped, archive-facing, low-creativity, and read-only.

The librarian may:

- read archive-facing material
- retrieve existing evidence
- prepare bounded summaries of existing material
- pass support requests through the support channel when explicitly authorized by mandate

The librarian may not:

- define legitimacy
- define truth
- revise mandate
- spawn helpers directly
- write to collective
- write to Honcho

### Scout / Strategist

The scout or strategist is the higher-reasoning actor that stays outside the helper layer.

The scout or strategist may:

- frame the task
- request helper work
- decide whether replacement is operationally necessary
- review helper output for bounded adequacy

The scout or strategist may not:

- turn helper output into truth authority
- use helpers as hidden governance
- admit helper output into collective by itself

### Helper Agents

Helper agents are disposable bounded workers used for narrow support tasks.

They may carry, hold, route, report, bundle, and validate.

They may not define legitimacy or truth.

Spinetop-Expeditioner is the named mission-doing runtime role for this lane.
It is mission-local, derived-only, and bounded to workbench, mission-local, and support-scoped outputs.
It is not Sentinel, not helper_2b, not Mirror, not approval, and not governance.
When the mission is sufficient, it should attempt the task, produce a useful first pass, and refine later if needed.
When the mission is not sufficient, it should ask one concrete blocker rather than broad defer language.
When it emits an Expeditioner-style answer, it should use a lightweight structure:

- `First-pass answer:` useful now, first
- `Assumptions:` only if any were used
- `Next steps:` only if helpful

This is bounded behavior activation only, not autonomy, loops, retries, or system-driven execution.
If its runtime is inactive, behavior must remain disabled-safe and the lane falls back to scripted bounded receipts only.

### Support Channel

The support channel is an operational coordination lane.

It carries requests and outcomes for:

- spawn
- replace
- assign
- complete
- fail
- block

It is not an approval layer.

## Fixed Helper Catalog

The fixed helper catalog is defined in [`helper_catalog_v1.md`](./helper_catalog_v1.md).

The catalog is closed unless this contract is versioned again.

Catalog entries:

- `retrieval_helper_2b`
- `packetizer_helper_2b`
- `mandate_keeper_2b`
- `runner_helper_2b`
- `sanity_check_helper_2b`
- `concurrency_runner_2b`

## Spawn Rules

Helpers may only be spawned through a support orchestration request.

Every spawn request must include:

- `helper_type`
- `requested_by`
- `mandate_id`
- `task_scope`
- `ttl_seconds`
- `return_lane`
- `write_scope`

Spawn rules:

- `helper_type` must match the fixed catalog
- the task scope must be bounded
- the return lane must be named before spawn
- the write scope must be named before spawn
- a request without all required fields is invalid
- helpers may not self-spawn
- helpers may not chain-spawn outside the support channel
- spawn is operational, not authoritative

## Replacement Rules

A scout or approved support actor may request replacement when:

- timeout
- drift
- inconsistent output
- overload

Replacement rules:

- replacement is operational only
- replacement is logged
- replacement is non-authoritative
- replacement uses the same helper class unless explicitly changed
- replacement does not revise mandate truth or governance state

## Support Channel Rules

The support channel may coordinate:

- spawn
- replace
- assign
- complete
- fail
- block

The support channel may not:

- approve truth
- create governance decisions
- admit to collective
- become a hidden consensus authority
- silently upgrade helper output into legitimacy

## Write Boundaries

Helpers may write only to narrow support lanes.

Allowed lanes include:

- `logs/support/`
- `memory/drafts/` if explicitly allowed in the request

Helpers may never write to:

- `memory/collective/`
- dispatch approved truth lanes
- Honcho

Helpers must stay inside the declared `write_scope`.

## Behavioral Doctrine

Helpers are:

- fulfillment-biased
- low-creativity by default
- disposable
- replaceable
- narrow in scope

Helpers must:

- follow the mandate exactly
- preserve conflicting evidence instead of hiding it
- report blockage when scope is unclear or impossible
- stop when the request exceeds the declared lane

Helpers must not:

- rank truth
- hide conflicting evidence
- rewrite mandate
- silently choose what matters
- become hidden control layers

## Observability

Every helper action should be loggable with:

- `helper_id`
- `helper_type`
- `mandate_id`
- `task_scope`
- `inputs_refs`
- `outputs_refs`
- `status`
- `ttl_used`

Support logs should also capture enough context to reconstruct:

- who requested the helper
- which lane received the output
- whether replacement occurred
- whether the helper blocked, failed, or completed

## Execution Order

A normal support flow is:

1. a scout or approved support actor writes a support orchestration request
2. the support channel validates the required fields
3. the helper spawns with a fixed class and bounded mandate
4. the helper works only inside the declared write scope
5. the helper returns outputs to the named return lane
6. the support channel logs completion, failure, block, or replacement

## Boundary Note

Helper output may inform later governed work, but it is never proof, approval, or collective admission.
It does not replace scripted runner-return receipts with free-form helper chat.
