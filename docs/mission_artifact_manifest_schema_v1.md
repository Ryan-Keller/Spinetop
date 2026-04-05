# Mission Artifact Manifest Schema v1

This document defines a docs-first manifest layer for mission and run outputs in the code foundry / expedition flow.

Goal:

- group many artifacts under one mission
- summarize what a mission produced at a glance
- keep the layout boring and explicit
- avoid reopening every artifact just to orient

This is a schema note only. It does not define runtime behavior.

## 1. Manifest Shape

Suggested top-level object:

```json
{
  "manifest_id": "manifest_<mission_id>_<run_id>_<shortid>",
  "mission_id": "mission_20260404T235426Z_4debf1",
  "run_id": "hermes-20260404T235426Z-9354",
  "status": "active",
  "summary": "Mission produced one Hermes run, one clarification packet, and one draft-ready review note.",
  "artifact_counts": {
    "total": 4,
    "by_kind": {
      "hermes_run": 1,
      "clarification_packet": 1,
      "draft": 1,
      "finding": 1
    },
    "by_stage": {
      "intake": 1,
      "processing": 1,
      "review": 2
    }
  },
  "artifact_refs": [],
  "priority_views": [],
  "mission_signals": [],
  "open_questions": [],
  "recommended_next_step": "review",
  "created_at": "2026-04-04T23:54:26.336434+00:00",
  "updated_at": "2026-04-04T23:54:34.267746+00:00"
}
```

## 2. Core Fields

Required fields:

- `manifest_id`
- `mission_id`
- `run_id`
- `status`
- `summary`
- `artifact_counts`
- `artifact_refs`
- `priority_views`
- `mission_signals`
- `open_questions`
- `recommended_next_step`
- `created_at`
- `updated_at`

Suggested `status` values:

- `draft`
- `active`
- `needs_review`
- `ready_for_review`
- `complete`
- `archived`
- `blocked`

Suggested `recommended_next_step` values:

- `review`
- `clarify`
- `classify`
- `promote`
- `archive`
- `reconsider`
- `none`

## 3. Artifact Counts

`artifact_counts` is a compact operational summary.

Suggested shape:

```json
{
  "total": 4,
  "by_kind": {
    "raw_data": 1,
    "finding": 1,
    "hermes_run": 1,
    "draft": 1
  },
  "by_stage": {
    "intake": 1,
    "processing": 1,
    "review": 2
  },
  "by_problem_role": {
    "source": 1,
    "analysis": 1,
    "decision_support": 2
  }
}
```

Suggested `by_kind` labels should align with the artifact-kind convention.

## 4. Artifact References

Each `artifact_refs` entry should carry enough metadata to be useful without reopening the artifact.

Suggested shape:

```json
{
  "artifact_id": "artifact_001",
  "artifact_kind": "hermes_run",
  "artifact_stage": "intake",
  "problem_role": "source",
  "quality_signal": "validated",
  "reusability_class": "single_use",
  "path": "logs/hermes/runs/hermes-20260404T235426Z-9354_anomaly_review.json"
}
```

Required fields for each artifact reference:

- `artifact_id`
- `artifact_kind`
- `artifact_stage`
- `problem_role`
- `quality_signal`
- `reusability_class`
- `path`

Suggested `artifact_kind` values:

- `raw_data`
- `idea`
- `finding`
- `classification`
- `review_note`
- `hermes_run`
- `clarification_packet`
- `draft`

Suggested `artifact_stage` values:

- `intake`
- `processing`
- `analysis`
- `review`
- `classification`
- `promotion`
- `archive`

Suggested `problem_role` values:

- `source`
- `evidence`
- `analysis`
- `decision_support`
- `review_note`
- `candidate`
- `derived`

Suggested `quality_signal` values:

- `raw`
- `validated`
- `partial`
- `provisional`
- `preferred`
- `superseded`

Suggested `reusability_class` values:

- `single_use`
- `mission_local`
- `cross_mission_candidate`
- `review_only`
- `reusable`

## 5. Priority Views

`priority_views` is a small set of operator-facing slices.

Each item may include:

- `view_id`
- `title`
- `focus`
- `artifact_ids`
- `signal`

Suggested `focus` values:

- `what_changed`
- `what_matters_next`
- `what_needs_review`
- `what_is_reusable`

Example:

```json
[
  {
    "view_id": "view_1",
    "title": "Review Needed",
    "focus": "what_needs_review",
    "artifact_ids": ["artifact_002", "artifact_004"],
    "signal": "clarification_needed"
  }
]
```

## 6. Mission Signals

`mission_signals` should be a short list of mission-level observations.

Suggested entries may include:

- `clarification_needed`
- `review_ready`
- `code_generated`
- `research_partial`
- `needs_classification`
- `candidate_for_promotion`
- `low_confidence`

Each signal may be a compact object:

```json
{
  "signal": "clarification_needed",
  "impact": "high",
  "reason": "Task text asked for an open-ended answer and Hermes deferred."
}
```

Suggested `impact` values:

- `low`
- `medium`
- `high`

## 7. Open Questions

`open_questions` should record what the mission still needs.

Suggested shape:

```json
[
  {
    "question": "Which branch should receive the code change?",
    "impact": "high",
    "source": "mission review"
  }
]
```

Suggested fields:

- `question`
- `impact`
- `source`

Suggested `impact` values:

- `low`
- `medium`
- `high`

## 8. Worked Example: Code-Generation Mission

```json
{
  "manifest_id": "manifest_mission_20260404T235426Z_4debf1_hermes-20260404T235426Z-9354_a1b2c3",
  "mission_id": "mission_20260404T235426Z_4debf1",
  "run_id": "hermes-20260404T235426Z-9354",
  "status": "needs_review",
  "summary": "Mission produced one Hermes run, one mission brief, one clarification packet, and one draft-ready artifact.",
  "artifact_counts": {
    "total": 4,
    "by_kind": {
      "mission_brief": 1,
      "hermes_run": 1,
      "clarification_packet": 1,
      "draft": 1
    },
    "by_stage": {
      "intake": 1,
      "processing": 1,
      "review": 2
    }
  },
  "artifact_refs": [
    {
      "artifact_id": "artifact_001",
      "artifact_kind": "mission_brief",
      "artifact_stage": "intake",
      "problem_role": "source",
      "quality_signal": "validated",
      "reusability_class": "mission_local",
      "path": "expeditions/active/mission_20260404T235426Z_4debf1/mission_brief.json"
    },
    {
      "artifact_id": "artifact_002",
      "artifact_kind": "hermes_run",
      "artifact_stage": "processing",
      "problem_role": "analysis",
      "quality_signal": "validated",
      "reusability_class": "review_only",
      "path": "logs/hermes/runs/hermes-20260404T235426Z-9354_anomaly_review.json"
    },
    {
      "artifact_id": "artifact_003",
      "artifact_kind": "clarification_packet",
      "artifact_stage": "review",
      "problem_role": "decision_support",
      "quality_signal": "validated",
      "reusability_class": "review_only",
      "path": "logs/citadel/clarification_packets/clarification_20260404T235434Z_cda129.json"
    },
    {
      "artifact_id": "artifact_004",
      "artifact_kind": "draft",
      "artifact_stage": "review",
      "problem_role": "candidate",
      "quality_signal": "provisional",
      "reusability_class": "single_use",
      "path": "memory/drafts/draft_20260404T235442Z_7a91f4.json"
    }
  ],
  "priority_views": [
    {
      "view_id": "view_1",
      "title": "What Needs Review",
      "focus": "what_needs_review",
      "artifact_ids": ["artifact_003", "artifact_004"],
      "signal": "clarification_needed"
    }
  ],
  "mission_signals": [
    {
      "signal": "clarification_needed",
      "impact": "high",
      "reason": "The task was open-ended and Hermes deferred."
    },
    {
      "signal": "code_generated",
      "impact": "medium",
      "reason": "The mission produced a draft artifact and a Hermes run artifact."
    }
  ],
  "open_questions": [
    {
      "question": "Should the draft be submitted or revised?",
      "impact": "high",
      "source": "mission review"
    }
  ],
  "recommended_next_step": "review",
  "created_at": "2026-04-04T23:54:26.336434+00:00",
  "updated_at": "2026-04-04T23:54:44.267746+00:00"
}
```

## 9. Worked Example: Research Mission

```json
{
  "manifest_id": "manifest_mission_20260404T101500Z_88c1aa_research_0f12ab",
  "mission_id": "mission_20260404T101500Z_88c1aa",
  "run_id": "hermes-20260404T101500Z-0f12",
  "status": "active",
  "summary": "Mission gathered raw notes, one finding, and one review note for later classification.",
  "artifact_counts": {
    "total": 4,
    "by_kind": {
      "raw_data": 2,
      "finding": 1,
      "review_note": 1
    },
    "by_stage": {
      "intake": 2,
      "analysis": 1,
      "review": 1
    }
  },
  "artifact_refs": [
    {
      "artifact_id": "artifact_001",
      "artifact_kind": "raw_data",
      "artifact_stage": "intake",
      "problem_role": "source",
      "quality_signal": "raw",
      "reusability_class": "cross_mission_candidate",
      "path": "memory/archive/raw_notes_001.json"
    },
    {
      "artifact_id": "artifact_002",
      "artifact_kind": "raw_data",
      "artifact_stage": "intake",
      "problem_role": "source",
      "quality_signal": "raw",
      "reusability_class": "cross_mission_candidate",
      "path": "memory/archive/raw_notes_002.json"
    },
    {
      "artifact_id": "artifact_003",
      "artifact_kind": "finding",
      "artifact_stage": "analysis",
      "problem_role": "analysis",
      "quality_signal": "validated",
      "reusability_class": "reusable",
      "path": "memory/compacted/finding_001.json"
    },
    {
      "artifact_id": "artifact_004",
      "artifact_kind": "review_note",
      "artifact_stage": "review",
      "problem_role": "decision_support",
      "quality_signal": "provisional",
      "reusability_class": "review_only",
      "path": "memory/inbox/review_note_001.json"
    }
  ],
  "priority_views": [
    {
      "view_id": "view_1",
      "title": "Reusable Findings",
      "focus": "what_is_reusable",
      "artifact_ids": ["artifact_003"],
      "signal": "finding_ready"
    }
  ],
  "mission_signals": [
    {
      "signal": "research_partial",
      "impact": "medium",
      "reason": "The mission gathered useful evidence but has not yet reached final classification."
    }
  ],
  "open_questions": [
    {
      "question": "Which findings should be promoted into a classification record?",
      "impact": "medium",
      "source": "mission review"
    }
  ],
  "recommended_next_step": "classify",
  "created_at": "2026-04-04T10:15:00.000000+00:00",
  "updated_at": "2026-04-04T10:18:22.000000+00:00"
}
```

## 10. Notes on Use

- The manifest is an orientation layer, not a truth layer.
- The manifest should point at artifacts that already exist.
- The manifest should stay short enough to inspect quickly.
- If a mission grows large, add more artifact refs before you add more prose.
