# Role Testing Sandbox

This is the smallest safe pattern for clean role testing in Spinetop.

Use a freshly created mission and mark it explicitly as a role-test sandbox.

Why this pattern:

- fresh mission creation already preserves governance and mission-local boundaries
- parked state, trigger history, retry ledgers, chat history, and role outputs are mission-local, so a new mission starts without inherited noise
- the sandbox marker makes the mission easy to recognize later without adding any runtime behavior
- nothing in this flow adds autonomy, loops, hidden chaining, or truth-lane writes

## Operator Pattern

Preferred objective pattern:

- `Sandbox role validation: helper_2b -> Expeditioner -> Mirror`

Avoid objectives starting with `test`, `tmp`, `temp`, or `scratch` if you want the mission to stay clearly recognizable without looking like queue junk.

## Create A Clean Sandbox Mission

Run:

```powershell
python scripts/role_test_sandbox.py create
```

What this does:

- creates a mission through the existing `POST /api/expeditions` path
- leaves governance and mission-agent creation unchanged
- writes one marker file at `workbench/missions/<mission_id>/notes/role_test_sandbox.json`
- verifies that the mission is still clean for role testing

Clean means:

- parking status is active
- no trigger records or pending trigger handoff
- retry budget is unused
- no chat history
- no operator intake inputs
- no prior agent runs
- no runner returns
- no mirror notes

## Re-check An Existing Mission

Run:

```powershell
python scripts/role_test_sandbox.py check <mission_id>
```

If this returns `is_clean=False`, do not reuse that mission for fresh role validation.

## Exact Role-Test Sequence

1. Create a fresh sandbox mission.
2. Invoke `helper_2b` first.
3. Invoke `Expeditioner` second.
4. Invoke `Mirror` last.
5. Keep each run explicit and operator-triggered.

Example first invocation:

```powershell
python scripts/agent_invocation.py spinetop-helper_2b <mission_id> --input-json "{\"trigger_reason\":\"role_test_sandbox\"}"
```

Then inspect the resulting `agent_run` artifact under `workbench/missions/<mission_id>/notes/agent_runs/`.

Use that artifact path as an explicit input for the next role when you want a controlled handoff:

```powershell
python scripts/agent_invocation.py spinetop_expeditioner <mission_id> --input-json "{\"trigger_reason\":\"role_test_sandbox\",\"artifact_refs\":[\"workbench/missions/<mission_id>/notes/agent_runs/<helper_run>.json\"]}"
```

Then invoke Mirror with the Expeditioner artifact:

```powershell
python scripts/agent_invocation.py spinetop-mirror <mission_id> --input-json "{\"trigger_reason\":\"role_test_sandbox\",\"artifact_refs\":[\"workbench/missions/<mission_id>/notes/agent_runs/<expeditioner_run>.json\"]}"
```

## Why This Is Cleaner Than Reusing A Parked Mission

- a reused parked mission already carries mission-local state such as parking reasons, blocked context, retry history, and prior trigger outcomes
- those records are useful governance evidence, so deleting or silently resetting them would be the wrong move
- a fresh mission avoids inheriting that noise instead of trying to scrub it
- the marker file gives operators a visible, low-tech way to recognize the intended sandbox mission later
- the only new artifact is mission-local and descriptive; it does not alter authority, routing, or automation behavior
