# Architecture

This system is organized around one canonical workspace called Spinetop. Spinetop is the source of truth for identity, policy, and promotion decisions. Other workspaces exist to explore, reflect, or test changes, but they do not redefine the core system.

## Roles

Spinetop
- Canonical workspace for system identity and shared doctrine.
- Owns promotion decisions, shared policy, and durable memory layers.
- Accepts changes only after review and alignment checks.

Spinelab
- Reflective and experimental workspace.
- Used for prototyping, critiques, and alternative approaches.
- Outputs are proposals and experiments, not canonical truth.

Experts
- Specialists with scoped responsibility (e.g., tooling, recovery, service ops).
- Inherit shared knowledge from Spinetop.
- Do not automatically rewrite collective memory; they propose changes.

Codex
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
- Proposals are checked for doctrine alignment and blast radius.
- Approved changes are promoted into Spinetop.

4. Retirement or Re-scope
- Experts are retired when redundant or merged.
- Scope changes require explicit review.

## Memory Layers

1. Canonical memory (Spinetop)
- Stable, reviewed knowledge and identity.
- Used by all experts as the baseline.

2. Project memory (Spinetop or subspaces)
- Task- or domain-specific notes.
- May be promoted to canonical memory if validated.

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
- Proposals are assessed for doctrine alignment and blast radius.

3. Promotion
- Approved changes are merged into Spinetop.

4. Adoption
- Experts inherit the updated shared knowledge on next sync.

## Blast-Radius Containment

- Experiments are isolated to Spinelab or a scoped expert workspace.
- Changes must declare scope, dependencies, and rollback steps.
- Canonical memory updates require explicit promotion.
- Service and recovery changes follow the same containment rules.

## Why One Canonical Workspace

A single canonical workspace prevents identity drift, conflicting policies, and unbounded propagation of errors. It creates a stable center that all other workspaces can refer to and align with.
