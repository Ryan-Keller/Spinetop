# Architecture

This system is organized around one canonical workspace called Spinetop. Spinetop is the governed environment the agent lives inside. Other workspaces exist to explore, reflect, or test changes, but they do not redefine the core system.

The canonical world contract lives in [`docs/doctrine.md`](./doctrine.md).

## Roles

### Spinetop

- Canonical workspace for system identity and shared doctrine.
- Owns governed state transitions, shared policy, and durable memory layers.
- Accepts changes only after review, alignment checks, and governance trail validation.

### Spinelab

- Reflective and experimental workspace.
- Used for prototyping, critiques, and alternative approaches.
- Outputs are proposals and experiments, not canonical truth.

### Experts

- Specialists with scoped responsibility, such as tooling, recovery, or service operations.
- Inherit shared knowledge from Spinetop.
- Do not automatically write to collective memory; they propose changes through governed state-machine transitions.

### Field Helpers

- `spinetop-helper_2b` is a bounded field-side helper identity inside Spinetop.
- It supports mission-local expedition work, short-horizon context, and tactical next-step suggestions.
- It thinks in small tactical frames: current context, key observations, possible next steps, and open questions.
- It may highlight local contradictions, but it does not resolve them by invention or turn them into truth.
- It writes only to helper-local support lanes and never to collective, approved dispatch, or Honcho.
- Its internal helper thinking stays separate from the structured runner-return receipt.
- It stays distinct from Sentinel review, Expeditioner execution ownership, and Mirror memory interpretation.

### Spinetop-Expeditioner

- `spinetop_expeditioner` is the mission-doing worker identity inside Spinetop.
- It works the mission in the mission-local workbench and produces first-pass derived outputs.
- It should use available context, move forward under bounded assumptions when allowed, and refine later if needed.
- Its lightweight response contract is: `First-pass answer:` first, `Assumptions:` only if any, and `Next steps:` only if helpful.
- It may write only to mission-local/workbench lanes, support receipts, and explicitly allowed drafts.
- It is not Sentinel review, not `spinetop-helper_2b` tactical support, and not Mirror memory interpretation.

### Sentinel-Spinetop

- Internal reviewer, watch, and anomaly role on the existing `hermes-spinetop` seam.
- Reads bounded operational and mission-local context and emits derived review outputs.
- Does not approve, define truth, act as bridge/governance authority, or self-activate in the background.
- Remains distinct from expeditioner work, `spinetop-helper_2b` support work, and mirror/storage functions.

### Spinetop-Mirror

- `spinetop-mirror` is the read-only memory interpretation identity inside Spinetop.
- It reads Honcho or Honcho-backed query results and derives mission-local reflections about gaps, contradictions, repetition, and stale assumptions.
- It may write only to `workbench/missions/<mission_id>/notes/mirror/`.
- It must not write to Honcho, collective, approved dispatch, or canonical mission state.
- It is not Sentinel review, not `spinetop-helper_2b` tactical support, and not Expeditioner task execution.

### Codex

- Builds and repairs systems.
- Executes tasks and implements changes.
- Does not define identity; it follows Spinetop doctrine.

## Expert Lifecycle

1. Initiation
- Domain and boundaries are defined.
- Baseline knowledge is inherited from Spinetop.

2. Operation
- Work stays within scope.
- Proposals are captured as draft notes or PRs.

3. Review and Promotion
- Proposals are checked for doctrine alignment, blast radius, and governance trail requirements.
- Approved changes enter collective only through explicit governance and dispatch review.

4. Retirement or Re-scope
- Experts are retired when redundant or merged.
- Scope changes require explicit review.

## Memory Layers

1. Canonical memory (Spinetop)
- Stable, reviewed knowledge and identity.
- Used by all experts as the baseline.

2. Project memory (Spinetop or subspaces)
- Task- or domain-specific notes.
- May be admitted to canonical memory if validated through governance.

3. Experimental memory (Spinelab)
- Temporary or exploratory notes.
- Never auto-promoted.

4. Local scratch
- Ephemeral notes tied to a single task.
- Must not outlive the task unless promoted.

## Adjacent Role Boundaries

- `Spinetop-Sentinel` is the reviewer/watch/anomaly role.
- `Spinetop-Expeditioner` is the task-doing expeditioner role and should not be conflated with Sentinel.
- `Spinetop-helper_2b` is a bounded support helper seam, not a reviewer authority.
- `Spinetop-Mirror` is the read-only memory interpretation role; it is not a reviewing, approving, or task-execution actor.

## Promotion Pipeline

1. Proposal
- Changes are drafted in Spinelab or an expert workspace.

2. Review
- Proposals are assessed for doctrine alignment, blast radius, and governance trail requirements.

3. Promotion
- Approved changes enter collective only through dispatch review and governed admission.

4. Adoption
- Experts inherit the updated shared knowledge on next sync.

## Blast-Radius Containment

- Experiments are isolated to Spinelab or a scoped expert workspace.
- Changes must declare scope, dependencies, and rollback steps.
- Canonical memory updates require candidate promotion, dispatch review, and governed admission.
- Service and recovery changes follow the same containment rules.

## Why One Canonical Workspace

A single canonical workspace prevents identity drift, conflicting policies, and unbounded propagation of errors. It creates a stable center that all other workspaces can refer to and align with.
