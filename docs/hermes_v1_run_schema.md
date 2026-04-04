# Hermes-Spinetop v1 Run Schema

This is a small output contract for Hermes v1 runs.

It is intentionally narrow so a manual runner can print, store, or inspect it without implying autonomy.

## Run Shape

```json
{
  "run_id": "string",
  "mode": "observe | anomaly_review | repair_check | repetition_review",
  "status": "summary_only | no_action | petition_recommended | blocked",
  "summary": "string",
  "evidence_refs": ["non-empty string"],
  "classification": {
    "kind": "observation | anomaly | repair_candidate",
    "title": "string",
    "severity": "low | medium | high",
    "boundedness": "localized | cross_system | ambiguous",
    "affected_system": "string"
  },
  "recommended_action": "none | operator_review | create_dispatch_petition | defer",
  "petition_kind": "anomaly_review | operator_review | repair_request | memory_admission | null",
  "confidence": 0.0
}
```

## Field Notes

- `run_id` is the canonical identity for the Hermes run.
- `mode` is the operator-selected review mode.
- `status` tells the operator whether Hermes only summarized, took no action, recommends a petition, or was blocked.
- `status` and `recommended_action` must stay paired: `summary_only` or `no_action` use `none` or `defer`; `petition_recommended` uses `operator_review` or `create_dispatch_petition`; `blocked` uses `none` or `defer`.
- `summary` should be concise and operator-facing.
- `evidence_refs` must be a list of non-empty strings that point to the exact state or records Hermes used.
- `classification` is optional in practice, but if present it must stay bounded and diagnostic.
- `repetition_review` should usually classify as `anomaly` or `repair_candidate`, not a new class.
- `recommended_action` must never imply direct repair execution.
- `petition_kind` is only set when Hermes recommends a governed petition.
- `confidence` should be conservative. If evidence is weak, lower the number and prefer no_action.

## Example: No Action

```json
{
  "run_id": "hermes-2026-04-03-001",
  "mode": "observe",
  "status": "no_action",
  "summary": "Return All is active, nanny is warm, dispatch is stable, and no bounded anomaly is visible in the current state snapshot.",
  "evidence_refs": [
    "world_state:return_all=on",
    "world_state:nanny=warm",
    "dispatch:stable",
    "bridge:healthy"
  ],
  "classification": {
    "kind": "observation",
    "title": "stable snapshot",
    "severity": "low",
    "boundedness": "localized",
    "affected_system": "dispatch"
  },
  "recommended_action": "none",
  "petition_kind": null,
  "confidence": 0.88
}
```

## Example: Anomaly Review With Petition Recommended

```json
{
  "run_id": "hermes-2026-04-03-002",
  "mode": "anomaly_review",
  "status": "petition_recommended",
  "summary": "A repeated dispatch failure pattern is visible across the last three attempts. The issue looks bounded to dispatch intake and is worth governed review.",
  "evidence_refs": [
    "dispatch:failed_attempts=3",
    "recent_governance_events:petition_backlog_increased",
    "world_state:return_all=off",
    "world_state:nanny=cool"
  ],
  "classification": {
    "kind": "anomaly",
    "title": "repeated dispatch failure",
    "severity": "medium",
    "boundedness": "localized",
    "affected_system": "dispatch"
  },
  "recommended_action": "create_dispatch_petition",
  "petition_kind": "anomaly_review",
  "confidence": 0.71
}
```

## Minimal Manual Runner Expectation

A manual Hermes runner only needs to:

1. load the selected state snapshot
2. fill the prompt template
3. capture the run output shape above
4. stop

It should not schedule itself, mutate collective, or bypass governance.
