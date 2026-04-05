# Tool Use Governance v1

This document defines a docs-first governance layer for tool use in Spinetop.
It is meant to let Spine use tools through the Book/UI in a controlled, impersonal, health-safe way.

It does not grant truth authority.
It does not bypass the state machine.
It does not replace governance.
If this document conflicts with `doctrine.md`, `state_machine_v1.md`, `support_orchestration_contract_v1.md`, or `hermes_v1_contract.md`, those docs win.

## 1. Purpose

Tool use must be:

- classified before it runs
- recorded with a structured receipt
- bounded to an explicit target
- reversible when possible
- subordinate to world state and governance

Tool use must not become a hidden control layer.
Spine may request and execute tools only inside the allowed lane for the current mission and health state.

## 2. Tool Classes

Tool actions are classified into one of the following classes.

| Class | Meaning | Typical use | Never allowed to do |
| --- | --- | --- | --- |
| `observe` | Read-only inspection of state, logs, docs, UI, and artifacts | Read status, summarize logs, inspect records | Write files, mutate state, approve truth |
| `research` | Read-only information gathering with bounded external or local lookup | Search docs, inspect code, compare references | Install packages, write governed records, bypass gates |
| `workbench_write` | Write only inside mission workbench or other declared draft area | Draft notes, scratch files, task-local artifacts | Touch governed paths, collective memory, dispatch truth |
| `sandbox_execute` | Run a bounded command in a mission-local sandbox | Tests, generators, local scripts, temporary transforms | Reach system Python, hidden services, or governed paths |
| `package_prepare` | Prepare a package, bundle, or staged artifact for later review | Build bundle, stage release assets, collect dependencies | Publish, admit, or mutate canonical truth directly |
| `governed_submit` | Hand a prepared artifact to an existing governed path or review lane | Submit a package through the approved process | Invent a new truth path or skip review/state checks |
| `install_change` | Make a local install or environment change inside a safe target | Install into workbench, project venv, or mission sandbox | Use system Python, global site-packages, or hidden services |
| `forbidden` | Anything that is not permitted by doctrine or health policy | None | Direct truth writing, bypass, stealth, or unsafe mutation |

### Classification rule

Every tool action must be classified before execution.
If it cannot be classified safely, the correct class is `forbidden`.

## 3. Spine Health Policy

Spine health is the runtime condition that says whether a tool action is safe to attempt.

Health is measured by the current state machine, governance state, and target confinement.
For installs and runtime changes, the default rule is conservative:

- if the action could affect system-wide state, it is blocked
- if the action could hide behavior in a background service, it is blocked
- if the action would mutate governed truth directly, it is blocked
- if the action cannot be rolled back or cleanly contained, it requires proposal first

### Health gate levels

- `open`: safe to run as classified, inside the allowed target
- `review_required`: may proceed only after a proposal or explicit review step
- `blocked`: may not proceed

### Health gate inputs

A health gate should consider:

- `return_all` state
- nanny temperature and cooldown
- dispatch backlog and current mission state
- target path confinement
- reversibility
- whether the action touches governed truth
- whether the action would create a hidden runtime dependency

### Health gate defaults

- read-only `observe` actions are normally `open`
- `research` is normally `open` if it stays read-only
- `workbench_write` is normally `open` only inside the declared workbench
- `sandbox_execute` is `open` only inside a mission-local sandbox
- `package_prepare` is `open` only for staging, not publishing
- `governed_submit` is `review_required`
- `install_change` is `review_required` unless the target is a mission-local sandbox and the install is clearly disposable
- `forbidden` is always `blocked`

## 4. Tool Action Record

Every tool action should produce a structured receipt.
Suggested receipt location:

- `logs/governance/tool_actions/<tool_action_id>.json`

Suggested record shape:

```json
{
  "tool_action_id": "tool_action_20260404T235426Z_4debf1",
  "mission_id": "mission_20260404T235426Z_4debf1",
  "requested_by": "spine",
  "tool_name": "python",
  "action_summary": "Generate a draft helper script from the approved template.",
  "tool_class": "workbench_write",
  "target_path": "workbench/mission_20260404T235426Z_4debf1/drafts/helper_stub.py",
  "risk_level": "low",
  "health_gate": "open",
  "rollback_hint": "Delete the generated draft file and restore the previous workbench snapshot.",
  "governance_effect": "none",
  "created_at": "2026-04-04T23:54:26.336434+00:00"
}
```

### Required fields

- `tool_action_id`
- `mission_id`
- `requested_by`
- `tool_name`
- `action_summary`
- `tool_class`
- `target_path`
- `risk_level`
- `health_gate`
- `rollback_hint`
- `governance_effect`
- `created_at`

### Suggested values

- `requested_by`: `spine`, `operator`, `assistant`, or another explicit actor label
- `risk_level`: `low`, `medium`, `high`, `critical`
- `health_gate`: `open`, `review_required`, `blocked`
- `governance_effect`: `none`, `proposal_created`, `review_request_created`, `submit_request_created`, `blocked`

## 5. What Spine May Do Freely

Spine may do the following freely when they stay inside the current mission and health gate:

- observe system state
- research code, docs, and local artifacts
- write only into the declared workbench
- execute bounded commands in a mission-local sandbox
- prepare packages or bundles for later review
- create tool-action receipts

Free does not mean invisible.
Every action still gets classified and logged.

## 6. What Must Be Gated Or Proposed First

The following require a proposal, review step, or explicit governable handoff:

- any write outside the mission workbench
- any install into the project-local venv
- any action that changes shared runtime behavior
- any action that touches dispatch, governance, collective, or Return All paths
- any `governed_submit`
- any action that could not be cleanly rolled back
- any action with unclear target ownership

## 7. What Is Forbidden

The following are forbidden:

- direct truth writing
- bypassing governance
- direct mutation of governed paths
- hidden background services that act without a receipt
- installs into system Python
- global package mutation as a default behavior
- writing to collective memory without the governed path
- making tools act as a second truth authority
- stealth escalation from read-only to write-capable behavior

## 8. Safe Install Targets

Safe install targets are:

- `workbench`
- `project-local venv`
- `mission-local sandbox`

Unsafe defaults are:

- `system Python`
- hidden background services
- direct governed path mutation

### Install rule

An install is only acceptable if it:

- targets one of the safe install targets
- has a rollback hint
- does not change canonical truth directly
- does not create a hidden service or hidden dependency
- does not weaken Spine health

## 9. Runtime Change Rule

Runtime changes are allowed only when they are:

- bounded
- classified
- logged
- reversible or explicitly disposable
- confined to the mission scope

If a runtime change can outlive the mission without a clear owner, it must be proposed first.

## 10. UI Implication

The Book/UI should treat every tool action as a classified receipt, not as a free-form command stream.

The UI may show:

- the tool class
- the health gate
- the target path
- the rollback hint
- the governance effect

The UI may not:

- infer truth authority from tool use
- hide the gate status
- convert a blocked action into a silent success

## 11. Minimal Next Step

The smallest implementation step after this spec is a read-only tool-action log view that lists:

- `tool_action_id`
- `mission_id`
- `tool_class`
- `health_gate`
- `target_path`
- `governance_effect`

That view should only read receipts from the suggested log location.

