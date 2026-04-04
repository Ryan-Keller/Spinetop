# Spinetop Autonomy Phase Plan v1

This document defines a safe staged autonomy roadmap for Spinetop.

It is docs-first and deliberately conservative.
It does not grant full autonomy, direct truth authority, or bypass rights.

If this document conflicts with [`doctrine.md`](./doctrine.md), [`state_machine_v1.md`](./state_machine_v1.md), [`support_orchestration_contract_v1.md`](./support_orchestration_contract_v1.md), or [`hermes_v1_contract.md`](./hermes_v1_contract.md), those documents win.

## Core Invariants

- No phase grants direct truth authority to helpers.
- No phase bypasses governance.
- No phase allows helpers to write directly into collective truth.
- Autonomy remains subordinate to the state machine and world state.
- Return All and nanny state remain global brakes.
- If evidence is ambiguous, the safe default is defer, block, or quarantine.
- Every phase must be reversible at the operational boundary.

## Roadmap Overview

The phases are cumulative. Each later phase assumes the earlier phase is already stable, observable, and reversible.

- Phase 1: manual observe
- Phase 2: manual draft assistance
- Phase 3: explicit review-and-submit helper
- Phase 4: gated semi-autonomous support tasks
- Phase 5: bounded autonomous support orchestration

The terms "semi-autonomous" and "bounded autonomous" in this document describe operational coordination only.
They do not mean independent truth-making, approval, or admission.

## Shared Safety Rules For All Phases

These rules apply in every phase:

- Helpers may observe, summarize, classify, and prepare bounded output.
- Helpers may not approve, admit, or legitimize truth.
- Helpers may not write directly to collective or invent governance decisions.
- Helpers may not self-escalate past their declared phase.
- Any helper output that affects truth-adjacent state must be routed through the governed state machine.
- Any action that conflicts with Return All, nanny cooldown, or operator instruction must stop or defer.
- Every action should be attributable to an actor, phase, input, and output reference.

## Phase 1: Manual Observe

### Intent

This is the safest baseline.
An operator manually triggers a bounded observation run, reads the result, and decides what happens next.

### Allowed Capabilities

- Read world state snapshots
- Read governance and dispatch status
- Summarize the current operating picture
- Identify bounded anomalies
- Emit evidence references
- Recommend no action, defer, or operator review

### Forbidden Capabilities

- Any write to memory outside a temporary run artifact
- Petition submission
- Draft mutation outside the run output
- Truth claims beyond the supplied evidence
- Any approval, admission, or mirror action
- Any background loop or self-scheduling

### Write Boundaries

- Allowed: ephemeral run output, logs, and operator-facing summaries
- Forbidden: `memory/collective/`, dispatch approved lanes, Honcho, and any path that could be mistaken for truth admission

### Observability Requirements

- Must log run ID, operator trigger, input snapshot references, and output summary
- Must record the exact world state consulted
- Must record whether Return All or nanny state constrained the result

### Kill Switch Behavior

- Operator can stop the run before output is stored
- Return All immediately suppresses forward motion
- Nanny warm or hot can force a no-action or deferred outcome

### Rollback Conditions

- Any malformed input snapshot
- Any evidence of accidental write beyond run logs
- Any output that cannot cite its sources
- Any sign that the run attempted to act instead of observe

### Preconditions For Entry

- Manual runner exists
- State snapshot is available
- Operator is present
- Logging and retention for the run output are enabled
- State machine constraints are active

## Phase 2: Manual Draft Assistance

### Intent

This phase allows Hermes to help prepare drafts, but not submit them.
It is still operator-led and still non-authoritative.

### Allowed Capabilities

- Draft petition text
- Draft structured summaries
- Draft anomaly notes
- Draft bounded repair hypotheses
- Prepare candidate evidence bundles
- Write only to `memory/drafts/` or another explicitly approved draft lane

### Forbidden Capabilities

- Submitting petitions
- Approving petitions
- Admitting records
- Mirroring to Honcho
- Editing governance state
- Hiding uncertainty or conflicting evidence

### Write Boundaries

- Allowed: `memory/drafts/` only, unless a future document names another draft lane
- Forbidden: `memory/collective/`, dispatch approved paths, Honcho, and any state transition that would look like truth admission

### Observability Requirements

- Must record draft ID, source evidence refs, authoring actor, and intended downstream target
- Must retain a diffable representation of the draft content
- Must show what was omitted or marked uncertain

### Kill Switch Behavior

- Operator may discard the draft at any time
- Return All blocks draft creation if the draft would advance a truth-adjacent path
- Nanny warm or hot can require shorter drafts, stronger disclaimers, or no draft at all

### Rollback Conditions

- Draft contains a false claim that cannot be traced to evidence
- Draft accidentally includes approval language
- Draft targets the wrong lane
- Draft becomes a substitute for governance

### Preconditions For Entry

- Phase 1 has been stable and audited
- Draft lanes are separated from governed lanes
- Operator can review and delete drafts
- Draft provenance is logged

## Phase 3: Explicit Review-and-Submit Helper

### Intent

This phase introduces a helper that can prepare a petition and present it for explicit human review and submission.
The helper does not submit on its own.

### Allowed Capabilities

- Assemble petition packages from bounded evidence
- Check petition shape against schema
- Highlight missing fields or conflicts
- Prepare a submission-ready artifact
- Recommend one of: submit, defer, reject, or revise

### Forbidden Capabilities

- Direct submission without human confirmation
- Petition approval by the helper
- Any direct truth write
- Any hidden retry loop that auto-resubmits
- Any change to authoritative state outside the governed channel

### Write Boundaries

- Allowed: draft lanes, support lanes, and review artifacts
- Forbidden: collective truth lanes, Honcho, and dispatch approval lanes
- Any generated submission artifact must be clearly marked as non-authoritative until a human submits it

### Observability Requirements

- Must log evidence refs, schema checks, and missing fields
- Must log the exact review target and operator decision
- Must preserve the chain from evidence to draft to submission artifact

### Kill Switch Behavior

- Operator can cancel submission at the final review step
- Return All blocks automatic escalation
- Nanny warm or hot can force the helper into draft-only mode

### Rollback Conditions

- Submission artifact diverges from the source evidence
- Helper attempts to auto-submit
- Helper cannot explain why the petition belongs in the governed lane
- Any mismatch between draft and final review artifact

### Preconditions For Entry

- Phase 2 is stable
- The review step is explicit and human-visible
- Submission rights stay with the operator or governed script
- A rejection path exists and is tested

## Phase 4: Gated Semi-Autonomous Support Tasks

### Intent

This is the earliest phase that could reasonably be called semi-autonomous.

The helper may perform bounded support tasks end-to-end inside a narrow lane, but only under explicit gates, with no truth authority and no governance bypass.

### Allowed Capabilities

- Execute bounded support workflows with fixed scope
- Route work through the support orchestration contract
- Spawn or replace disposable helpers only within the support channel rules
- Collect evidence, bundle output, and return results to a named lane
- Make narrow operational choices that do not alter truth or governance

### Forbidden Capabilities

- Direct truth authority
- Petition approval
- Collective admission
- Honcho mirroring unless a separate governed mirror step already allows it
- Open-ended planning outside the declared task scope
- Self-expanding scope
- Hidden delegation chains that escape the support contract

### Write Boundaries

- Allowed: bounded support lanes such as `logs/support/` and explicitly named draft lanes
- Forbidden: authoritative truth lanes, collective memory, and any write path that implies admission or approval
- Any support write must remain inside the declared `write_scope`

### Observability Requirements

- Must log task scope, mandate ID, helper ID, inputs, outputs, and TTL
- Must expose gate state before any action starts
- Must record the reason for each block, defer, replace, or completion
- Must preserve enough provenance to reconstruct the workflow without trusting the helper's judgment

### Kill Switch Behavior

- Global Return All stops the workflow immediately
- Nanny warm narrows the permitted task set
- Nanny hot forces defer, block, or operator review
- Operator may revoke the mandate or replace the helper at any time

### Rollback Conditions

- The helper exceeds its declared task scope
- The workflow loses provenance
- The helper starts acting like an approver or truth source
- Any output cannot be traced to bounded inputs
- The support lane begins to behave like a hidden control plane

### Preconditions For Entry

- Phase 3 is stable and auditable
- Support orchestration is enforced by code, not just policy text
- Helper classes are fixed and disposable
- Gate checks are logged before execution
- A rollback path exists for every supported workflow

## Phase 5: Bounded Autonomous Support Orchestration

### Intent

This phase is a cautious extension of Phase 4, not a leap to full autonomy.

The system may independently initiate or continue narrowly bounded support work only when the task class, scope, and stop conditions have all been pre-approved by policy.

### Allowed Capabilities

- Auto-start pre-approved support tasks within a fixed catalog
- Auto-retry bounded non-authoritative failures within a capped budget
- Auto-replace a failing disposable helper within the same lane
- Auto-route results to the correct support or review lane
- Auto-defer when the world state or governance state is not suitable

### Forbidden Capabilities

- Any direct truth authority
- Any ability to override governance decisions
- Any ability to invent new task classes
- Any ability to widen scope without operator approval
- Any ability to mutate collective memory or approve admission
- Any autonomous loop that persists past its allowed boundary or TTL

### Write Boundaries

- Allowed: only the explicitly approved support lanes for the specific task class
- Forbidden: collective truth, dispatch approval, Honcho, and any destination that turns orchestration into authority
- Writes must remain append-only, bounded, and attributable

### Observability Requirements

- Must log every autonomous trigger with its policy reason
- Must emit gate state, task class, helper replacement count, retry count, and stop reason
- Must expose a full audit trail of every autonomous decision
- Must be machine-readable enough for an operator to reconstruct the whole run

### Kill Switch Behavior

- Global Return All wins over all auto-start logic
- Nanny hot forces immediate pause or defer
- Operator revocation halts the orchestration graph
- A failed audit trail should collapse the phase back to Phase 4 behavior

### Rollback Conditions

- Repeated drift outside the approved support class
- Any attempt to infer new authority from repeated success
- Any safety invariant failure in the gate layer
- Any inability to reconstruct the autonomous decision path

### Preconditions For Entry

- Phase 4 has been stable over time
- The supported task catalog is closed and versioned
- Each autonomous lane has a clear stop condition, retry cap, and rollback path
- Auditability is strong enough to justify machine-triggered execution
- Governance remains the only source of truth for any truth-adjacent outcome

## Phase Transition Rules

Transitions must be explicit and versioned.

- Phase 1 to Phase 2 requires stable observation, clean logging, and no unauthorized writes
- Phase 2 to Phase 3 requires draft provenance, review visibility, and safe operator submission
- Phase 3 to Phase 4 requires bounded support orchestration with hard write boundaries
- Phase 4 to Phase 5 requires closed task classes, gated retries, and audited autonomous triggers

No phase may be skipped unless a separate governance document explicitly authorizes the skip.

## Safety Notes

- Semi-autonomy is a coordination property, not a truth property.
- A helper can be more autonomous in execution while still being completely subordinate in legitimacy.
- The moment a helper starts acting like a truth source, the phase design has failed.
- The safe target is bounded operational usefulness, not independent governance.

## Recommended Interpretation

The most conservative reading is the correct reading:

- observe first
- draft second
- submit only with explicit human review
- automate only what is narrow, reversible, and fully governed

## Summary

This roadmap intentionally stops short of full autonomy.

It gives Spinetop a path from manual observation to bounded autonomous support orchestration while keeping truth authority, governance, and admission outside helper control.
