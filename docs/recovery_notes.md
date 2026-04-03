# Recovery Notes

This document captures recovery philosophy and practical steps. It favors containment, diagnosis, and safe rollback over aggressive automation.

## Roles In Recovery

Spinetop
- Canonical workspace for recovery doctrine and approved fixes.

Spinelab
- Reflective and experimental workspace for trial fixes and diagnostics.

Experts
- Provide scoped recovery procedures and proposals.
- Inherit shared knowledge but do not rewrite collective memory.

Codex
- Executes recovery steps and repairs.
- Does not define identity or policy.

## Recovery Philosophy

- Contain blast radius before attempting repairs.
- Prefer reversible actions and explicit scripts.
- Keep recovery local-first and observable.
- Promote fixes only after they are stable and reviewed.

## Expert Lifecycle During Recovery

1. Initiation
- Scope and ownership are defined.
- Baseline recovery knowledge is inherited from Spinetop.

2. Operation
- Expert performs scoped diagnosis and repair tasks.
- Drafts proposals for recovery improvements.

3. Review and Promotion
- Recovery proposals are checked for doctrine alignment and blast radius.
- Approved changes are promoted into Spinetop.

4. Retirement or Re-scope
- Recovery experts may be retired or merged after stabilization.

## Triage Steps

1. Identify scope
- Which workspace is affected: Spinetop, Spinelab, or expert?
- Which services or memory layers are impacted?

2. Stabilize
- Stop non-essential operations.
- Preserve logs and current state.

3. Diagnose
- Check service status and configs.
- Compare expected vs actual configuration.

4. Repair
- Apply minimal, reversible changes.
- Avoid system-level changes without explicit scripts.

5. Verify
- Re-run health checks.
- Confirm system behavior is normal.

6. Promote
- Document the fix and promote to Spinetop only after review.

## Memory Layers During Recovery

- Canonical memory is read-only until stabilization.
- Experimental memory can be discarded if it increases risk.
- Local scratch should be captured before shutdown if relevant.

## Promotion Pipeline (Recovery Changes)

1. Proposal in Spinelab or expert workspace.
2. Review for blast radius, reversibility, and doctrine alignment.
3. Promotion into Spinetop when stable.
4. Adoption by experts on next sync.

## Blast-Radius Containment

- Isolate experiments to Spinelab or a scoped expert workspace.
- Keep recovery actions local-first and reversible.
- Avoid cross-system changes without explicit approval.

## Why One Canonical Workspace

A single canonical workspace prevents recovery actions from rewriting identity or doctrine. It ensures that fixes remain consistent and that divergent changes do not propagate unexpectedly.
