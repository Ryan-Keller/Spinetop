# Agent Invocation Layer v1

This layer adds explicit role invocation for Hermes-backed Spinetop roles.

It is intentionally narrow:

- invoke one role at a time
- store the result as a mission-local artifact
- let later roles read artifacts explicitly
- do not create direct agent chat
- do not auto-chain roles
- do not add loops or schedulers

## Invocation Function

Primary function:

- `scripts/agent_invocation.py`
- `invoke_role(role_id, mission_id, input_payload)`

Supported roles:

- `spinetop-sentinel`
- `spinetop-expeditioner`
- `spinetop-helper-2b`
- `spinetop-mirror`

The invocation path selects the mapped Hermes profile, loads that role's `SOUL.md`, resolves the configured model slot, and produces one bounded derived result.

## Output Contract

Each invocation returns:

```json
{
  "role": "spinetop-expeditioner",
  "mission_id": "mission_...",
  "result": "string",
  "confidence": 0.72,
  "next_step": "string",
  "derived_only": true
}
```

## Artifact Storage

Artifacts are stored under:

- `workbench/missions/<mission_id>/notes/agent_runs/`

Each run artifact records:

- role
- mission id
- trigger reason
- input payload
- output contract
- timestamp
- status

Artifacts are append-only by run id and indexed into the mission artifact index as `agent_run`.

## Controlled Handoff

Handoffs stay artifact-based:

1. invoke Expeditioner
2. Expeditioner writes an `agent_run` artifact
3. invoke Sentinel with `artifact_refs` pointing at the Expeditioner artifact
4. Sentinel writes its own separate `agent_run` artifact

No direct message channel is created between roles.

## API Surface

The dashboard API exposes one explicit route:

- `POST /api/expeditions/<mission_id>/invoke-role`

Body:

```json
{
  "role_id": "spinetop-sentinel",
  "trigger_reason": "operator_review",
  "input_payload": {
    "artifact_refs": [
      "workbench/missions/<mission_id>/notes/agent_runs/agent_run_....json"
    ]
  }
}
```

## Feed Exposure

Mission detail and feed now surface the newest explicit role artifact as:

- `latest_role_activity`

Examples:

- `Expeditioner -> produced first pass`
- `Sentinel -> flagged low confidence`

## Safe Defaults

- inactive roles return a disabled-safe artifact instead of running the model
- no auto-trigger of downstream roles
- no direct agent chat path
- no governance or truth-lane writes
