# Helper Catalog v1

This catalog is fixed for v1.

The helpers below are disposable support workers, not truth authorities.
They may support bounded operations, but they may not define legitimacy.

Helper runtime selection is governed separately through `config/helper_model_registry.json`.
In the current implementation, `helper_2b` remains `scripted` by default even though the registry can name future local model keys for that role.

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
