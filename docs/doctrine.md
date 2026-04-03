# Spinetop World Contract v1

Spinetop is the governed environment the agent lives inside. It is not the agent. It is a memory civilization with laws, territories, actors, rituals, and state transitions.

## Purpose

- Spinetop is the canonical, governed, durable memory system.
- Spinelab is experimental and may propose, but does not define truth.
- Honcho is append-only storage only. No intelligence belongs there.
- Agents do not own memory. They read and write only through controlled system layers.
- Non-destructive always: archive, quarantine, or defer rather than silently delete.
- Governance first, performance second.

## World State

World state is operational weather, not memory truth.

Examples:

- `return_all` on or off
- nanny `cool`, `warm`, or `hot`
- bridge healthy or failing
- petition backlog
- compaction pressure
- quarantine pressure

## Territories

Territories are places where records can exist. They are not just folders. They are states of legitimacy.

### Inbox

- Meaning: untrusted arrival.
- Source: Spinelab, external inputs, or agents.
- Allowed: read, validate, reject, promote to candidate.
- Forbidden: direct use as truth, direct writes to collective.

Minimal record shape:

- `source`
- `expert_name`
- `task`
- `summary`
- `key_findings`
- `confidence`
- `recommended_action`
- `promotion_candidate`

### Promotion

- Meaning: candidate layer, not truth.
- Use: validated records waiting for governance trail.
- Required next step: dispatch petition or governance review.
- Forbidden: treating promotion as acceptance into collective.

Minimal record shape:

- inbox fields
- `promotion_timestamp`
- `related_petition_id` or equivalent governance link
- `governance_review_state`

### Dispatch

- Meaning: governance space.
- Sub-states: `pending`, `approved`, `deferred`, `rejected`.
- Use: decisions live here, not memory truth.
- Canonical identity: `petition_id`.

Minimal record shape:

- `petition_id`
- `record_type`
- `created_at`
- `created_by`
- `status`
- `petition_kind`
- `requested_action`
- `risk_level`
- `evidence_refs`
- `record_name`
- `agent_id`
- `workspace`
- `summary`
- `task`
- `status_updated_at`
- `spawn_authority`
- `dispatch_mode`
- `entry_class`

### Collective

- Meaning: trusted memory.
- Requirements: governance trail present and approved.
- Forbidden: direct writes and bypassing petition review.

Minimal record shape:

- candidate fields
- `record_id`
- `record_type`
- `candidate_id`
- `created_at`
- `admitted_at`
- `governance_approval_ref`
- `related_petition_id`
- `governance_decision_id`
- `governance_review_state`
- `admission_actor`
- `durability_class`

### Honcho

- Meaning: raw storage mirror.
- Properties: append-only, storage-only, no reasoning.
- Source: collective only, and only when governance allows.

Minimal record shape:

- record as mirrored from collective
- no new authorization data invented here

### Quarantine

- Meaning: unsafe or failed records.
- Use: schema failure, corruption, suspicious input, or broken bridge state.
- Non-destructive: quarantine preserves evidence.

### Logs and World State

- Meaning: operational weather and control state.
- Includes: nanny status, return_all, topology events, bridge events, custodial decisions.

## Actors

Actors are defined by permissions, not by intelligence.

### Operator

- Can approve or reject governance outcomes.
- Can override system pressure when appropriate.
- Has final authority.

### Watcher

- Reads inbox.
- Validates promotable records.
- Promotes to candidate only.
- Creates or triggers governance petition flow.
- Must not approve into collective.

### Custodial

- Handles repair and stabilization.
- Bounded and reversible only.
- Must defer when state is ambiguous or cooling.

### Nanny

- Observes system pressure.
- Emits temperature and cooldown.
- Does not decide truth.
- Its output constrains other actors.

### Honcho Bridge

- Mirrors collective into Honcho.
- Storage-only behavior.
- Must obey return_all and nanny pressure.

### Hermes-Spinetop

- Licensed worker in the city.
- May observe, validate, and petition.
- Must not approve to collective.
- Must not write directly to truth layers.

### Hermes-Spinelab

- Experimental scout.
- May propose and write candidates to inbox or dispatch.
- Must not define canonical truth.

## Laws

These are non-negotiable invariants.

- No direct truth writes.
- Honcho is blind and storage-only.
- Return_all overrides convenience.
- Ambiguous states defer.
- New truth requires a governance trail.
- Model use must follow expert policy at runtime.
- Non-destructive always.
- Actors stay in lane.

## Rituals

Rituals are repeated governed motions. A script may perform a motion, but a ritual is the motion plus its meaning and constraints.

- Observe
- Validate
- Petition
- Review
- Approve
- Defer
- Reject
- Quarantine
- Repair
- Mirror
- Recall
- Cool down
- Compact later
- Archive later

## Allowed Transitions

The core transition skeleton is:

- `inbox -> promotion`
- `promotion -> dispatch/pending`
- `dispatch/approved + governance trail -> collective`
- `collective -> mirrored/honcho`
- `failure -> quarantine`
- `return_all / warm / hot -> defer or pause`

Promotion is candidate status only. It never means acceptance into truth.

The practical implementation contract for these movements lives in [state_machine_v1.md](state_machine_v1.md).

## Record Types

The world currently recognizes these record classes:

- observation record
- candidate memory record
- collective memory record
- dispatch petition
- governance decision
- custodial decision
- nanny status
- bridge event
- quarantine record
- compaction proposal
- artifact or insight record

Canonical field contracts live in [record_schemas.md](record_schemas.md).

## State Types

The world can be in one or more of these operational states:

- calm
- warm
- hot
- recall
- degraded
- ambiguous
- repairable
- operator-review-needed

## Acceptance Rule

The system is mechanically correct when:

- new records cannot enter collective without an approved governance trail
- old records may bridge only as legacy compatibility
- legacy compatibility cannot become a loophole for newly governed records
- return_all and nanny pressure can pause or defer the system safely
