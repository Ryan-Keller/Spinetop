# Spinetop State Machine v1

## Purpose

This document defines the governed state machine for Spinetop.

Schemas define what records are.  
This document defines how records are allowed to move.

A transition is valid only if:
1. the record schema is valid,
2. the actor is authorized,
3. the source state is legal,
4. the destination state is legal,
5. required transition fields are added,
6. global governance conditions allow the move.

---

## Core Principles

- No direct truth writes.
- Collective requires governance trail.
- Honcho is append-only storage only.
- Return All overrides forward motion.
- Nanny temperature influences automation posture.
- Ambiguity defers.
- Non-destructive always: defer, reject, or quarantine rather than silently discard.
- Canonical identity is record ID or petition ID, never filename.

---

## Territories

- `draft/external`
- `inbox`
- `promotion`
- `dispatch/pending`
- `dispatch/approved`
- `dispatch/deferred`
- `dispatch/rejected`
- `collective`
- `mirrored/honcho`
- `quarantine`

---

## Actors

- Operator
- Watcher
- Hermes-Spinetop
- Hermes-Spinelab
- Custodial
- Nanny
- Honcho Bridge
- Governed Admission Script

---

## Transition Matrix

### Memory Path

| Source state | Actor | Destination state | Allowed? | Required fields added | Blocked by Return All? | Blocked by Nanny? | Notes |
|---|---|---:|---|---|---|---|---|
| draft/external | Hermes-Spinelab | inbox | Yes | `inboxed_at`, `source_workspace`, `submitted_by` | No | No | Arrival only, not truth |
| draft/external | Operator | inbox | Yes | `inboxed_at`, `source_workspace`, `submitted_by` | No | No | Manual intake allowed |
| inbox | Watcher | promotion | Yes | `promotion_timestamp`, `validated_by`, `validation_result` | No | Warm/Hot may defer | Promotion is candidate-only |
| inbox | Watcher | quarantine | Yes | `quarantined_at`, `quarantined_by`, `quarantine_reason` | No | No | For malformed/unsafe input |
| inbox | Operator | quarantine | Yes | `quarantined_at`, `quarantined_by`, `quarantine_reason` | No | No | Manual quarantine |
| promotion | Watcher | dispatch/pending | Yes | `related_petition_id`, `petition_kind=memory_admission` | No | Warm/Hot may prefer defer | Governance handoff |
| promotion | Operator | dispatch/pending | Yes | `related_petition_id`, `petition_kind=memory_admission` | No | Warm/Hot may prefer defer | Manual petition creation |
| promotion | Watcher | collective | No | - | - | - | Explicitly illegal |
| promotion | Hermes-Spinetop | collective | No | - | - | - | Explicitly illegal |
| dispatch/pending | Operator | dispatch/approved | Yes | `approved_at`, `approved_by`, `approval_reason`, `governance_decision_ref` | Yes | Warm/Hot may still allow if manual | Human approval path |
| dispatch/pending | Operator | dispatch/deferred | Yes | `deferred_at`, `deferred_by`, `defer_reason` | No | Yes | Safe fallback |
| dispatch/pending | Operator | dispatch/rejected | Yes | `rejected_at`, `rejected_by`, `rejection_reason` | No | No | Terminal denial |
| dispatch/approved | Governed Admission Script | collective | Yes | `admitted_at`, `collective_record_id`, `candidate_id`, `governance_approval_ref`, `related_petition_id`, `governance_decision_id`, `admission_actor`, `durability_class` | Yes | Warm/Hot may defer | Must verify governance trail |
| collective | Honcho Bridge | mirrored/honcho | Yes | `mirrored_at`, `mirrored_by`, optional `honcho_ref` | Yes | Hot may pause | Mirror only, no mutation |
| collective | Any actor except bridge | honcho | No | - | - | - | Prevents bypass |

### Petition Path

| Source state | Actor | Destination state | Allowed? | Required fields added | Blocked by Return All? | Blocked by Nanny? | Notes |
|---|---|---:|---|---|---|---|---|
| none | Watcher | dispatch/pending | Yes | `petition_id`, `created_at`, `created_by`, `status=pending`, `petition_kind`, `requested_action`, `evidence_refs` | No | Warm/Hot may defer | Typical memory admission petition |
| none | Hermes-Spinetop | dispatch/pending | Yes | same as above | Action-advancing petitions may defer | Warm/Hot may defer | Hermes can initiate, not resolve |
| none | Hermes-Spinelab | dispatch/pending | Yes | same as above | Action-advancing petitions may defer | Warm/Hot may defer | Proposal only |
| none | Custodial | dispatch/pending | Yes | same as above plus repair context | Usually yes unless bypass rule | Yes | Narrow repair/self-heal only |
| dispatch/pending | Operator | dispatch/approved | Yes | approval fields | Yes | Manual override possible | Final authorization |
| dispatch/pending | Governance automation | dispatch/deferred | Yes | defer fields | No | Yes | Safe automatic pause |
| dispatch/pending | Governance automation | dispatch/rejected | Yes, limited | reject fields | No | No | Only for malformed or policy-invalid petition |

### Classification Path

| Source state | Actor | Destination state | Allowed? | Required fields added | Blocked by Return All? | Blocked by Nanny? | Notes |
|---|---|---:|---|---|---|---|---|
| observation | Hermes-Spinetop | anomaly classification | Yes | `classification_kind`, `severity`, `boundedness`, `affected_system`, `evidence_summary`, `recommended_next_step` | No | No | Read/diagnose only |
| observation | Custodial | anomaly classification | Yes | same as above | No | No | Operational diagnostics |
| anomaly classification | Hermes-Spinetop | repair candidate | Conditional | `repairability=likely_repairable`, `repair_scope`, `linked_petition_id` | No | Warm/Hot may force defer | Only if bounded and reversible |
| anomaly classification | Operator | review petition | Yes | petition fields | No | No | Human escalation |
| repair candidate | Custodial | dispatch/pending | Yes | petition fields plus repair context | Usually yes unless bypass rule | Yes | Still not direct action |

### World State Path

| Source state | Actor | Destination state | Allowed? | Required fields added | Notes |
|---|---|---:|---|---|---|
| return_all inactive | Operator | return_all active | Yes | `changed_at`, `changed_by`, `reason` | Global brake |
| return_all active | Operator | return_all inactive | Yes | `changed_at`, `changed_by`, `reason` | Resume governed ops |
| cool | Nanny | warm | Yes | `temperature`, `burst_score`, `error_score`, `global_cooldown_seconds`, `recommended_actions` | Pressure rising |
| warm | Nanny | hot | Yes | same as above | Strong caution |
| hot | Nanny | warm | Yes | same as above | Recovery |
| warm | Nanny | cool | Yes | same as above | Recovery complete |

---

## Validator Checklist

Every governed transition should pass the following checks in order.

### 1. Identity Check
- Does the record have a canonical ID?
- Is the system using the ID, not the filename, as identity?
- If this is a petition, does `petition_id` exist?
- If this is collective memory, does `record_id` exist?

### 2. Schema Check
- Does `record_type` exist and match the expected type?
- Are all required fields present for the current state?
- Are field types valid?
- Are enum fields valid?

### 3. Authority Check
- Is this actor allowed to create this record type?
- Is this actor allowed to perform this transition?
- Is the actor staying within its lane?

### 4. Source-State Check
- Is the record actually in the source state claimed?
- Is the source state legal for this transition?
- Is this transition explicitly allowed in the matrix?

### 5. Global Governance Check
- Is Return All active?
- Is nanny warm or hot?
- Is cooldown active?
- Does policy require defer instead of forward motion?

### 6. Transition Field Check
Before committing the move, were the required transition fields added?

Examples:
- inbox → promotion: `promotion_timestamp`, `validated_by`, `validation_result`
- pending → approved: `approved_at`, `approved_by`, `approval_reason`, `governance_decision_ref`
- approved → collective: `admitted_at`, `collective_record_id`, `candidate_id`, `governance_approval_ref`, `related_petition_id`, `governance_decision_id`, `admission_actor`, `durability_class`

### 7. Governance Trail Check
For any truth-adjacent transition:
- Is there a linked petition?
- Is there an approval reference?
- Is the governance trail complete?
- Is this a new record trying to sneak through a legacy path?

### 8. Non-Destructive Fallback Check
If blocked:
- Should this be deferred?
- Should this be quarantined?
- Should it be rejected?
- Is the system avoiding silent deletion?

### 9. Logging Check
- Was the transition decision logged?
- Was the block or defer reason logged?
- Can an operator reconstruct what happened?

### 10. Mirror Safety Check
For collective → honcho only:
- Is the record already in collective?
- Does it have governance trail?
- Is Return All inactive?
- Is the bridge allowed to run now?
- Is this truly mirroring, not mutation?

---

## Enforcement Outcomes

### Hard Fail
Use for:
- illegal transition
- missing canonical ID
- actor not authorized
- promotion → collective direct attempt
- Hermes → approved state attempt

### Defer
Use for:
- Return All active
- nanny warm or hot with nonessential automation
- ambiguous evidence
- competing actions

### Quarantine
Use for:
- malformed JSON
- schema corruption
- unsafe or suspicious record shape
- missing mandatory structure that makes safe handling impossible

### Reject
Use for:
- invalid petition intent
- disallowed request
- clearly unsupported action

---

## Critical Guards

### Guard A — Truth Admission Guard
A record may only enter collective if:
- source state is `dispatch/approved`
- actor is `Governed Admission Script` or Operator
- `governance_approval_ref` exists
- current world state allows it

### Guard B — Hermes Guard
Hermes may:
- observe
- classify
- petition

Hermes-Spinetop v1 does not validate or promote. It may only observe, classify, and petition into those governed paths. Validation, promotion, approval, and admission remain system functions outside Hermes authority.

Hermes may not:
- approve
- admit
- mirror
- mutate collective

### Guard C — Legacy Compatibility Guard
Legacy handling must apply only to pre-existing records.
It must never become a valid route for newly created records.

---

## Illegal Transitions

The following transitions are explicitly illegal:

- `inbox → collective`
- `promotion → collective` without approved petition
- `Hermes → collective`
- `Hermes → dispatch/approved`
- `Honcho Bridge → create memory`
- `Nanny → admit memory`
- `Custodial → approve its own petition into collective`
- any new record using legacy compatibility path
- filename-based identity replacing canonical ID

These should fail hard or defer, depending on context.

---

## Minimal Execution Order

Every governed transition should roughly follow this sequence:

1. load record
2. validate schema
3. verify actor authority
4. verify source state
5. check Return All, nanny, and policy
6. add required transition fields
7. verify governance trail if truth-adjacent
8. commit move
9. log event
10. on failure, defer or quarantine rather than silently discard
