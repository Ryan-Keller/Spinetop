# Spinetop-Mirror v1 Contract

Spinetop-Mirror v1 is the passive mission-local mirror storage surface inside Spinetop. It is narrow, mission-local, and reflects only what the operator explicitly saves.

If this document conflicts with older governance-heavy or Honcho-first documentation, the active operator `save:` to mirror behavior described here wins for the live system.

## Purpose

Mirror exists to:

- store mission-local data that the operator explicitly writes with `save:`
- provide a passive reflection surface for that saved data
- allow concierge retrieval of previously saved mirror notes
- preserve saved content without promoting it into governance, dispatch, or collective truth

Mirror does not exist to:

- run continuously in the background
- trigger itself or schedule operations
- infer, interpret, validate, normalize, or approve content
- decide what should be written
- write to Honcho
- mutate collective truth
- approve governance
- answer the task itself
- behave like Sentinel review
- behave like Expeditioner execution

## Core Role

Mirror is:

- a passive storage surface
- operator-written through `save:`
- mission-local
- read-only at retrieval time
- exact-content preserving
- not truth
- not approval
- not governance
- not autonomous

Mirror is a surface, not an actor.

## Write Model

Mirror is updated only when the operator explicitly uses the `save:` command.

Mirror write path:

- operator issues `save: <content>`
- system writes the provided content to the mission-local mirror lane
- no write occurs if nothing remains after `save:`

Mirror storage lane:

- `workbench/missions/<mission_id>/notes/mirror/`

Mirror does not:

- poll for new content
- ingest background events
- auto-save conversation state
- interpret or validate the saved content before storing it

## Retrieval Model

Mirror content is retrievable through concierge only after the operator has explicitly saved data to the mirror.

Concierge retrieval is:

- read-only
- mission-local
- limited to saved mirror notes
- unable to create, rewrite, validate, or authorize mirror content

If nothing has been saved, Mirror has nothing to return.

## Forbidden Behavior

Mirror must not:

- run as an always-on process
- self-schedule or trigger autonomous actions
- activate roles automatically
- validate, interpret, summarize, or govern saved content
- write to Honcho
- mutate Honcho sessions, messages, peers, or collections
- write to `memory/collective/`
- write to `memory/dispatch/approved/`
- create hidden background sweeps or mirror loops
- mutate canonical mission state

## Invocation Model

Mirror v1 is:

- save-driven
- operator-triggered
- passive until written to
- read-only when retrieved
- not always-on
- not self-scheduling

Adjacent role behavior remains explicit:

- roles activate only when explicitly invoked
- Mirror does not auto-trigger any role
- no background execution is implied by stored mirror data

## Distinct From Adjacent Roles

Mirror is intentionally distinct from:

- `Spinetop-Sentinel`, which performs review, watch, and anomaly work when invoked
- `Spinetop-Expeditioner`, which performs mission-local task work when invoked
- `Spinetop-helper_2b`, which provides bounded field-side tactical support when invoked

Mirror output is storage, not judgment:

- it reflects saved data
- it does not interpret saved data
- it does not decide what matters
- it does not grant authority to retrieved content
