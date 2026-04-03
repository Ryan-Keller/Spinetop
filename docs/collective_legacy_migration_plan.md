# Collective Legacy Migration Plan v1

This is a small, conservative plan for the current legacy collective backlog.

Goal:

- Move from "helpful report" toward "clean bill of health"
- Avoid silent upgrades
- Avoid fabricated governance
- Keep non-destructive behavior

## Migration Note

Legacy collective records can fail the modern strict schema even when they are valid historical artifacts. That is expected during normalization because the modern contract requires canonical IDs, explicit lineage, and fully governed admission fields that older files may never have carried.

The checker separates legacy records into three practical buckets:

- `modern`: the record satisfies the current strict contract and carries governed lineage
- `grandfatherable`: the record is legacy historical memory, should stay stored as-is, and must remain explicitly marked legacy
- `operator_review_needed`: the record is too thin, ambiguous, or under-linked to safely normalize or grandfather

Normalization is allowed to explain a record, not to invent one. If a file is missing modern governance evidence, that absence is preserved rather than backfilled.

## Classification

Legacy collective records should be classified as one of:

- `normalizable`
- `grandfatherable`
- `operator_review_needed`

### 1. Normalizable

A record is normalizable only when it can be brought toward the modern collective contract without inventing semantic truth.

Criteria:

- non-empty `summary`
- non-empty `key_findings`
- stable identity exists or can be derived deterministically from existing fields
- an explicit governance trail exists, such as `governance_approval_ref` or `related_petition_id`
- missing envelope fields are derivable, not guessed

What this means:

- safe to normalize the envelope
- safe to add explicit legacy markers if needed
- not safe to invent content

### 2. Grandfatherable

A record is grandfatherable when it is clearly legacy historical memory and can remain stored as-is under explicit legacy marking, even though it is not modern-compliant.

Criteria:

- non-empty `summary`
- non-empty `key_findings`
- weak or missing modern governance trail
- legacy-shaped provenance is present, such as `promotion_candidate`, `approval_timestamp`, `timestamp_created`, `agent_id`, `session_id`, `expert_name`, or `legacy_compatibility`

What this means:

- keep it
- label it explicitly as legacy
- do not present it as modern compliant
- do not backfill governance fiction

### 3. Operator Review Needed

A record needs operator review when it is too thin or ambiguous to grandfather safely.

Criteria:

- empty `key_findings`
- missing `summary`
- missing or weak identity with no stable lineage
- no explicit governance trail
- no clear legacy marker

What this means:

- do not auto-upgrade
- do not auto-fill findings
- quarantine or flag for operator attention if needed

## Exact Boundary Cases

### Empty `key_findings`

- Never fabricate findings.
- If `key_findings` is empty, the record is not normalizable.
- If the rest of the record is otherwise clearly legacy and stable, it may still be grandfatherable.
- If the record is thin or ambiguous, classify it as `operator_review_needed`.

### Missing `governance_approval_ref`

- Do not invent one.
- Only treat the record as normalizable if a real linked petition or explicit governance reference already exists.
- Otherwise it is grandfatherable at best, or review-needed if the rest of the record is weak.

### Missing `admitted_at`

- Do not silently synthesize modern admission time.
- A legacy record may be grandfathered if it has a legacy approval time or equivalent lineage.
- If the record is meant to become modern truth, `admitted_at` must be explicit.

### Missing or Weak Identity

- `record_id` is the canonical identity for modern collective records.
- A filename is storage detail, not identity.
- A legacy record may be grandfathered if its lineage is stable and explicit.
- If identity is only guessed, the record needs operator review.

### Legacy Compatibility Markers

Useful markers for explicit legacy handling:

- `legacy_compatibility`
- `promotion_candidate`
- `approval_timestamp`
- `timestamp_created`
- `agent_id`
- `session_id`
- `expert_name`

These markers are evidence of legacy shape, not proof of modern compliance.

## Non-Destructive Migration Approach

1. Write a migration report first.
2. Classify records without mutating them.
3. Normalize only fields that are deterministically derived.
4. Mark grandfathered records explicitly as legacy.
5. Flag thin or ambiguous records for operator review.
6. Quarantine records only when safe handling is not possible.

## Proposed Schema Additions

Recommended explicit legacy markers:

- `schema_generation`: `modern` | `legacy`
- `legacy_status`: `modern` | `legacy_grandfathered` | `legacy_incomplete` | `needs_operator_review`
- `normalization_status`: `explicit` | `derived` | `legacy_marked` | `needs_operator_review`

Optional supporting fields:

- `legacy_reason`
- `derived_from`
- `identity_origin`
- `governance_origin`

These fields should describe provenance. They should not fabricate missing truth.

## Current Backlog

Based on the current collective directory:

- `grandfatherable`
  - `test.json`
- `operator_review_needed`
  - `hermes_20260402_203004.json`
  - `hermes_20260402_205412.json`
  - `hermes_20260402_205558.json`
  - `hermes_20260402_212107.json`
  - `spinelab_20260403_015746.json`
  - `spinelab_20260403_015746_20260403_015949.json`

Known legacy final petition case:

- `memory/dispatch/deferred/dispatch_hermes-desktop_20260403_043712_deferred.json`
- This file is intentionally still `operator_review_needed` because it lacks a matching governance decision record.
- It should not be auto-fixed, silently upgraded, or reclassified as modern.
- If it is migrated at all, it should remain an operator review task unless a real matching governance decision is recovered.

## Smallest Safe Next Patch

The smallest useful code change is to keep the checker conservative but let it distinguish:

- strict
- normalizable
- grandfatherable
- operator_review_needed

That improves the report without pretending the backlog is clean.
