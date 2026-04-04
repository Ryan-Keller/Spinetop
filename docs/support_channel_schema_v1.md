# Support Channel Schema v1

This schema defines the coordination lane for helper orchestration.

It is operational only.

It does not approve truth, create governance decisions, admit to collective, or act as hidden consensus.

## Record Type

Every support channel event should be stored as a support event record.

Canonical event types:

- `spawn`
- `replace`
- `assign`
- `complete`
- `fail`
- `block`

## Required Fields

These fields should be present on every support event record.

| Field | Required | Type | Meaning |
|---|---|---|---|
| `support_event_id` | Yes | string | Canonical identity for the support event |
| `event_type` | Yes | enum | One of `spawn`, `replace`, `assign`, `complete`, `fail`, `block` |
| `requested_by` | Yes | string | Actor or system that issued the request |
| `mandate_id` | Yes | string | Mandate the helper is acting under |
| `task_scope` | Yes | string | Narrow bounded task description |
| `status` | Yes | enum | Current event status |
| `created_at` | Yes | timestamp | Event creation time |
| `helper_id` | No for spawn, yes otherwise | string | Identifier for the active helper instance |
| `helper_type` | Yes for spawn and replace | string | Fixed helper class from the catalog |
| `ttl_seconds` | Yes for spawn and replace | integer | Requested helper lifetime |
| `return_lane` | Yes for spawn and replace | string | Lane where outputs must return |
| `write_scope` | Yes for spawn and replace | array[string] or string | Allowed write boundary |
| `inputs_refs` | Recommended | array[string] | References to inputs used by the helper |
| `outputs_refs` | Recommended | array[string] | References to outputs produced by the helper |
| `ttl_used` | Recommended | integer | TTL consumed when the event ended |

## Spawn Request Shape

A spawn request is a support event with `event_type = spawn`.

Required spawn fields:

- `helper_type`
- `requested_by`
- `mandate_id`
- `task_scope`
- `ttl_seconds`
- `return_lane`
- `write_scope`

Spawn validation rules:

- the helper type must exist in the fixed catalog
- the task scope must be bounded
- the return lane must be named before spawn
- the write scope must be named before spawn
- missing required fields make the request invalid

## Replacement Request Shape

A replacement request is a support event with `event_type = replace`.

Required replacement fields:

- `helper_type`
- `requested_by`
- `mandate_id`
- `task_scope`
- `ttl_seconds`
- `return_lane`
- `write_scope`
- `helper_id`
- `replaces_helper_id`
- `replacement_reason`

Replacement validation rules:

- the replacement should stay in the same helper class unless explicitly changed
- replacement is operational only
- replacement must be logged
- replacement does not change truth or governance

## Assign, Complete, Fail, Block

These event types describe the live lifecycle of a helper.

### `assign`

Required fields:

- `helper_id`
- `helper_type`
- `requested_by`
- `mandate_id`
- `task_scope`
- `status`

### `complete`

Required fields:

- `helper_id`
- `helper_type`
- `mandate_id`
- `task_scope`
- `outputs_refs`
- `status`
- `ttl_used`

### `fail`

Required fields:

- `helper_id`
- `helper_type`
- `mandate_id`
- `task_scope`
- `status`
- `failure_reason`
- `ttl_used`

### `block`

Required fields:

- `helper_id`
- `helper_type`
- `mandate_id`
- `task_scope`
- `status`
- `blocking_reason`
- `ttl_used` when known

## Status Values

Suggested status values:

- `requested`
- `queued`
- `assigned`
- `running`
- `blocked`
- `complete`
- `fail`
- `replaced`

## Minimal Log Requirement

Every support event should be recoverable from logs with enough data to reconstruct:

- `helper_id`
- `helper_type`
- `mandate_id`
- `task_scope`
- `inputs_refs`
- `outputs_refs`
- `status`
- `ttl_used`

The log should also preserve:

- `requested_by`
- `return_lane`
- `write_scope`
- replacement chain, if any

## Invalid Conditions

Support events should fail validation when they:

- omit a required field
- reference a helper type outside the fixed catalog
- try to write beyond the declared scope
- imply collective admission
- imply governance approval
- imply hidden consensus

## Boundary Note

This schema is only for support orchestration.

It must not be reused as a truth schema, governance schema, or collective admission schema.
