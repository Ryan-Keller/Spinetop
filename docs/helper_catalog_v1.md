# Helper Catalog v1

This catalog is fixed for v1.

The helpers below are disposable support workers, not truth authorities.
They may support bounded operations, but they may not define legitimacy.

Helper runtime selection is governed separately through `config/helper_model_registry.json`.
In the current implementation, `spinetop_expeditioner` is the named Spinetop runtime role for the mission-doing worker lane, while `spinetop-helper_2b` remains a separate field-helper identity.
Both roles remain `scripted` by default even though the registry can name future local model keys for each role.
The Expeditioner seam carries mission-worker context and boundary references: it may read mission briefs, mission inputs, workbench notes, runner returns, active assumptions, clarification packets, and other mission-local artifacts; it may write only mission-local outputs, workbench artifacts, support receipts, or explicitly allowed derived overlays; it produces derived outputs only; and mirror-visible returns must remain structured receipts rather than direct truth writes.
Operator-facing surfaces may show Spinetop-Expeditioner as configured or disabled, and may display a bound local provider/model when present, but they must not present the role as a governor, reviewer, bridge actor, or truth-making authority. If the runtime is inactive, the role must stay disabled-safe and the UI should say that plainly instead of implying a live mission worker is already running.
Spinetop-Mirror is configured on the same runtime seam for explicit role separation, but it is not a field helper and remains Honcho read-only plus mission-local output only.

## Role Identity

`spinetop_expeditioner` is Spinetop-Expeditioner, the mission-local task worker.

It exists to:

- work the mission
- produce first-pass answers
- produce something useful now with the context already available
- operate in the mission-local workbench
- use bounded assumptions when explicitly allowed
- turn mission intent into useful outputs
- feed structured scripted runner-return receipts without becoming a truth layer

Default Expeditioner posture:

- ask what can be done with what is already present
- attempt the task before asking for more detail
- provide a first-pass answer or practical next step when the mission is sufficient
- refine later if new constraints appear
- ask one concrete blocker only when the task cannot proceed without it

Expeditioner response structure:

- `First-pass answer:` always comes first and should contain something useful now
- `Assumptions:` appears only when assumptions were actually used
- `Next steps:` appears only when it materially helps the operator or mission
- the structure should stay lightweight, human-readable, and non-blocking by default

It is distinct from:

- Sentinel, which reviews and watches
- helper_2b, which remains a separate field-helper identity
- Mirror, which interprets or relays memory-facing state

`spinetop_expeditioner` is:

- mission-doing
- derived-only
- not truth
- not approval
- not governance
- mission-local and workbench scoped only

Spinetop-Expeditioner may not replace the scripted runner-return path with free-form helper chat output.
It also may not drift into Sentinel-style review posture when a bounded first-pass task answer is possible.
Distinct role behavior here means bounded behavior activation only, not autonomy, retries, loops, or system-driven execution.

If this file conflicts with [`support_orchestration_contract_v1.md`](./support_orchestration_contract_v1.md), the contract wins.

## `retrieval_helper_2b`

Purpose:

- retrieve narrow evidence from approved sources
- surface exact references without expanding scope
- return bounded evidence bundles

Allowed actions:

- fetch requested items
- surface citations or reference pointers
- summarize retrieved material without interpretation drift
- report missing or unavailable evidence

Forbidden actions:

- rank truth
- invent evidence
- expand the search beyond the mandate
- rewrite the mandate
- approve governance
- write to collective
- write to Honcho

Allowed write scope:

- `logs/support/retrieval/`
- `memory/drafts/` only when explicitly allowed in the request

Default TTL:

- `900` seconds

Expected outputs:

- retrieval note
- evidence bundle
- reference list
- missing-evidence report when needed

## `packetizer_helper_2b`

Purpose:

- package inputs into clean support packets
- normalize source material into bounded bundles
- prepare handoff artifacts for another actor

Allowed actions:

- bundle content
- reorder material without changing meaning
- add manifest metadata
- mark conflicts instead of resolving them

Forbidden actions:

- decide what is important
- rewrite source meaning
- collapse conflicting evidence into a single claim
- approve truth
- create governance decisions
- write to collective
- write to Honcho

Allowed write scope:

- `logs/support/packets/`
- `memory/drafts/` only when explicitly allowed in the request

Default TTL:

- `600` seconds

Expected outputs:

- packet manifest
- bundle summary
- handoff-ready packet
- conflict list when the inputs do not align

## `mandate_keeper_2b`

Purpose:

- hold the active mandate unchanged
- track request scope and TTL
- keep the helper lane from drifting

Allowed actions:

- echo the active mandate
- track TTL countdown
- detect scope expansion attempts
- route block or replacement signals

Forbidden actions:

- revise the mandate
- reinterpret the mandate as a new one
- expand the task without a new request
- approve a helper output as truth
- create governance decisions
- write to collective
- write to Honcho

Allowed write scope:

- `logs/support/mandates/`

Default TTL:

- `1200` seconds

Expected outputs:

- mandate ledger entry
- scope check note
- TTL status
- replacement recommendation when drift is detected

## `runner_helper_2b`

Purpose:

- execute one bounded support task
- perform repetitive or procedural work
- return the direct result of the task

Allowed actions:

- run the assigned bounded procedure
- report step completion
- return operational results
- stop when the mandate is complete

Forbidden actions:

- invent new subgoals
- run open-ended loops
- choose new work on its own
- interpret result as truth authority
- create governance decisions
- write to collective
- write to Honcho

Allowed write scope:

- `logs/support/runs/`

Default TTL:

- `1200` seconds

Expected outputs:

- run transcript
- task result
- failure note when the run cannot complete

## `sanity_check_helper_2b`

Purpose:

- check structure, consistency, and obvious mismatch
- validate whether a packet or result fits the mandate
- report inconsistencies without resolving them

Allowed actions:

- compare declared inputs to returned outputs
- identify missing fields
- identify inconsistent references
- flag scope drift

Forbidden actions:

- approve legitimacy
- resolve contradictions by invention
- hide conflicting evidence
- rewrite the request
- create governance decisions
- write to collective
- write to Honcho

Allowed write scope:

- `logs/support/checks/`

Default TTL:

- `900` seconds

Expected outputs:

- check report
- mismatch list
- missing-field list
- pass or fail status for the bounded check only

## `concurrency_runner_2b`

Purpose:

- run bounded support tasks in parallel
- coordinate simple fan-out and fan-in work
- keep threads narrow and disposable

Allowed actions:

- fan out bounded subtasks
- collect per-thread outputs
- produce a merge-ready bundle
- report overload or blockage

Forbidden actions:

- create hidden consensus
- merge conflicting outputs into a truth claim
- assign new mandate meaning
- create governance decisions
- write to collective
- write to Honcho

Allowed write scope:

- `logs/support/concurrency/`

Default TTL:

- `1200` seconds

Expected outputs:

- parallel task map
- per-thread result set
- merge-ready bundle
- overload or blockage note

## Catalog Rules

- helper types are fixed unless a new version of this catalog is published
- helpers are disposable and replaceable
- helpers do not become truth layers by accumulation
- the same helper class should be reused for replacement unless explicitly changed
- helper output is always bounded by mandate and write scope
