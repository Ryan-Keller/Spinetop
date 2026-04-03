# Expert Template

This template defines how experts operate within Spinetop. Experts are scoped specialists who inherit shared knowledge but do not redefine canonical memory.

The canonical world contract lives in [`docs/doctrine.md`](./doctrine.md).

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
- Approved changes are admitted into collective only through dispatch review and governed admission.

4. Retirement or Re-scope
- Expert is retired when redundant or merged.
- Scope changes require explicit review.

## Memory Layers Reference

- Canonical memory (Spinetop): read-only unless admitted through governance.
- Project memory: scoped notes that may be promoted.
- Experimental memory (Spinelab): temporary and non-canonical.
- Local scratch: task-bound and disposable.

## Memory Handling

- Shared knowledge is read-only unless admitted through governance.
- Expert memory stays local until reviewed.
- Avoid rewriting collective memory without approval.
- New truth requires a governance trail.

## Promotion Pipeline (Expert View)

1. Draft
- Work begins in Spinelab or local expert space.

2. Review
- Check doctrine alignment, scope, dependencies, blast radius, and governance trail requirements.

3. Promotion
- Admit into Spinetop collective when approved through the governed path.

4. Adoption
- Experts inherit updates on next sync.

## Blast-Radius Containment

- Keep experiments isolated to Spinelab or the expert workspace.
- Document rollback steps for any operational change.
- Avoid cross-cutting edits without explicit approval.

## Recovery Philosophy Touchpoints

- Contain impact before repair.
- Prefer reversible steps and explicit scripts.
- Admit fixes to canonical memory only after stability is verified and governance allows it.

## Promotion Checklist

- Scope is explicit and bounded.
- Dependencies are known and documented.
- Rollback path is clear.
- Changes align with Spinetop doctrine.

## Coordination Notes

- Use Spinelab for experimental reasoning.
- Use Spinetop for canonical updates only after dispatch review and governed admission.
- Codex may implement changes, but does not define identity.

## Why One Canonical Workspace

Spinetop is the single source of truth to prevent identity drift and conflicting policies. Experts inherit shared knowledge but do not automatically write to collective memory.
