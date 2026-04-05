# Artifact Kind Convention v1

Use these labels in mission-local artifact indexes and related lightweight trackers.

Goal:

- keep labels small
- keep labels boring
- avoid inventing near-duplicates

Recommended kinds:

- `raw_data`
- `idea`
- `finding`
- `classification`
- `review_note`
- `hermes_run`
- `clarification_packet`
- `draft`
- `mirror_reflection`
- `memory_gap_report`
- `contradiction_note`
- `session_pattern_summary`

Rules:

- Prefer one of the recommended kinds when the artifact fits.
- Use the same kind consistently for the same artifact family.
- Do not create a new kind unless the existing set clearly does not fit.
- Keep `path` as a storage path, not a semantic label.
- Keep `created_at` as UTC.

Examples:

- raw gathered logs -> `raw_data`
- operator thought or out-of-the-box note -> `idea`
- processed interpretation -> `finding`
- structured classification record -> `classification`
- short manual review note -> `review_note`
- Hermes run artifact -> `hermes_run`
- clarification reasoning packet -> `clarification_packet`
- governed draft artifact -> `draft`
- mission-local memory interpretation reflection -> `mirror_reflection`
- missing-memory or stale-memory note -> `memory_gap_report`
- contradiction-focused interpretation note -> `contradiction_note`
- session/message pattern digest -> `session_pattern_summary`
