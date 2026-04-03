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
