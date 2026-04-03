# Expert Template

This template defines how experts operate within Spinetop. Experts are scoped specialists who inherit shared knowledge but do not redefine canonical memory.

## Role

- Name:
- Domain:
- Primary responsibilities:
- Dependencies:
- Failure modes:

## Lifecycle

1. Initiation
- Expert is created with a clear domain and boundaries.
- Initial knowledge is inherited from Spinetop.

2. Operation
- Expert performs tasks within scope.
- Proposes improvements via draft notes or PRs.

3. Review and Promotion
- Proposed changes are reviewed for doctrine alignment and blast radius.
- Approved changes are promoted into Spinetop.

4. Retirement or Re-scope
- Expert is retired when redundant or merged.
- Scope changes require explicit review.

## Memory Layers Reference

- Canonical memory (Spinetop): read-only unless promoted.
- Project memory: scoped notes that may be promoted.
- Experimental memory (Spinelab): temporary and non-canonical.
- Local scratch: task-bound and disposable.

## Memory Handling

- Shared knowledge is read-only unless promoted.
- Expert memory stays local until reviewed.
- Avoid rewriting collective memory without approval.

## Promotion Pipeline (Expert View)

1. Draft
- Work begins in Spinelab or local expert space.

2. Review
- Check doctrine alignment, scope, dependencies, and blast radius.

3. Promotion
- Merge into Spinetop when approved.

4. Adoption
- Experts inherit updates on next sync.

## Blast-Radius Containment

- Keep experiments isolated to Spinelab or the expert workspace.
- Document rollback steps for any operational change.
- Avoid cross-cutting edits without explicit approval.

## Recovery Philosophy Touchpoints

- Contain impact before repair.
- Prefer reversible steps and explicit scripts.
- Promote fixes to Spinetop only after stability is verified.

## Promotion Checklist

- Scope is explicit and bounded.
- Dependencies are known and documented.
- Rollback path is clear.
- Changes align with Spinetop doctrine.

## Coordination Notes

- Use Spinelab for experimental reasoning.
- Use Spinetop for canonical updates only after review.
- Codex may implement changes, but does not define identity.

## Why One Canonical Workspace

Spinetop is the single source of truth to prevent identity drift and conflicting policies. Experts inherit shared knowledge but do not automatically rewrite collective memory.
