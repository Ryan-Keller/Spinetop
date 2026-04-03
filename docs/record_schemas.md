# Spinetop Record Schemas v1

This file defines the boring, enforceable contracts for Spinetop record classes.

Rules that apply everywhere:

- Every record has `record_type`.
- Every record has a canonical ID.
- Every record has a UTC creation time.
- Filenames are storage detail, not identity.
- New truth must carry a governance trail.
- Ambiguous or pressured states defer.

## 1. Dispatch Petition

A dispatch petition is a request for governed action. It is not memory truth.

Required fields:

- `petition_id`
- `record_type`: `dispatch_petition`
- `created_at`
- `created_by`
- `workspace`
- `status`
- `petition_kind`
- `summary`
- `reason`
- `evidence_refs`
- `requested_action`
- `risk_level`
- `requires_operator_approval`
- `entry_class`

Allowed values:

- `status`: `pending`, `approved`, `deferred`, `rejected`
- `petition_kind`: `memory_admission`, `anomaly_review`, `repair_request`, `operator_review`, `self_heal_request`
- `requested_action`: `admit_to_collective`, `operator_review`, `repair`, `defer`, `reject`
- `risk_level`: `low`, `medium`, `high`
- `entry_class`: `normal`, `repair`, `self_heal`, `anomaly_review`

Optional fields:

- `related_record_id`
- `related_petition_id`
- `cooldown_observed`
- `governance_notes`
- `operator_id`
- `source_host`

Rule:

- A dispatch petition may authorize movement or repair, but it is never the memory being admitted.

## 2. Governance Decision

A governance decision is the explicit judgment between petition and collective admission.

Legal creators:

- Operator
- Governance automation
- Custodial, only for narrow repair or self-heal cases that do not admit memory into collective

Required fields:

- `decision_id`
- `record_type`: `governance_decision`
- `created_at`
- `created_by`
- `petition_id`
- `petition_kind`
- `decision_outcome`
- `summary`
- `reason`
- `evidence_refs`
- `review_state`
- `risk_level`
- `requires_operator_review`

Allowed values:

- `decision_outcome`: `approve_collective`, `defer`, `reject`, `operator_review`
- `review_state`: `pending`, `final`, `amended`, `superseded`
- `risk_level`: `low`, `medium`, `high`

Optional fields:

- `governance_decision_ref`
- `related_collective_id`
- `decision_notes`
- `governance_notes`
- `operator_id`
- `source_host`
- `legacy_compatibility`

Rule:

- A governance decision is the judgment record.
- It records the reason a petition did or did not move toward collective admission.
- Final petition states (`approved`, `deferred`, `rejected`) must each have a matching governance decision record.
- It does not itself become collective memory.

## 3. Candidate Memory

A candidate memory is a validated record waiting for governance.

Required fields:

- `record_id`
- `record_type`: `candidate_memory`
- `created_at`
- `source_workspace`
- `submitted_by`
- `summary`
- `key_findings`
- `recommended_action`
- `confidence`
- `promotion_candidate`

Optional fields:

- `source_record_ref`
- `related_petition_id`
- `tags`
- `archival_status`
- `legacy_compatibility`

Rule:

- Candidate memory is not truth.
- Candidate memory is the thing the watcher promotes and the governor reviews.

## 4. Collective Record

A collective record is trusted memory.

Required fields:

- `record_id`
- `collective_record_id`
- `record_type`: `collective_memory`
- `created_at`
- `admitted_at`
- `source_workspace`
- `submitted_by`
- `governance_approval_ref`
- `related_petition_id`
- `governance_decision_id`
- `summary`
- `key_findings`
- `recommended_action`
- `confidence`
- `durability_class`

Allowed values:

- `durability_class`: `working_truth`, `stable_truth`, `temporary_truth`

Optional fields:

- `source_record_ref`
- `tags`
- `archival_status`
- `legacy_compatibility`
- `compaction_parent_ref`

Rule:

- A collective record without `governance_approval_ref` is invalid for new admissions.
- For modern records, the cleanest reference chain is both `related_petition_id` and `governance_decision_id`, with `governance_approval_ref` as the compact admission reference.

## 5. Operational Classification

This schema describes anomalies and repair candidates.

Required fields:

- `classification_id`
- `record_type`: `operational_classification`
- `created_at`
- `classified_by`
- `classification_kind`
- `title`
- `affected_system`
- `severity`
- `boundedness`
- `evidence_summary`
- `recommended_next_step`
- `repairability`

Allowed values:

- `classification_kind`: `anomaly`, `repair_candidate`
- `affected_system`: `memory_pipeline`, `dispatch`, `nanny`, `custodial`, `honcho_bridge`, `model_policy`, `governance`, `unknown`
- `severity`: `low`, `medium`, `high`
- `boundedness`: `localized`, `cross_system`, `ambiguous`
- `recommended_next_step`: `none`, `operator_review`, `defer`, `repair_petition`, `recall`
- `repairability`: `not_applicable`, `likely_repairable`, `unclear`, `do_not_attempt`

Optional fields:

- `linked_petition_id`
- `linked_record_id`
- `cooldown_context`
- `return_all_active`
- `notes`

## 6. Simple Decision Rule

- Use `anomaly` when the issue is real but the cause is unclear or the action should begin with review.
- Use `repair_candidate` when the issue is bounded, the cause is likely known, and a reversible repair path exists.
