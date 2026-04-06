# Hermes Profile Bootstrap v1

This document adds a repo-local bootstrap path for external Hermes Agent profiles without changing Spinetop governance behavior.

## What This Is

- a tracked profile registry at `config/hermes_profile_registry.json`
- tracked role templates under `services/hermes/roles/`
- a repo-local bootstrap/admin helper at `scripts/bootstrap_hermes_profiles.py`
- a small install helper at `scripts/install_hermes_agent.sh`

## What This Is Not

- not a new autonomy loop
- not a replacement for existing role cards
- not a second governance system
- not an automatic bridge, Honcho, or truth-writing path

## Audit Summary

Current Hermes/model seams already present in the repo:

- Sentinel runtime config: `config/hermes_runtime.json`
- Sentinel role card: `config/sentinel_role.json`
- External Sentinel expert card: `experts/hermes_spinetop.json`
- Helper runtime seam: `config/helper_model_registry.json`
- Helper role cards: `config/expeditioner_role.json`, `config/helper_role.json`, `config/mirror_role.json`
- Helper runtime loader and validation: `scripts/helper_model_runtime.py`, `scripts/validate_expert_config.py`
- Existing Hermes runner seam: `scripts/run_hermes_v1.py`
- Existing Hermes/Honcho compatibility docs: `docs/hermes_v1_contract.md`, `docs/mirror_contract_v1.md`, `docs/expert_model_governance.md`

## Install Path

Official Hermes Agent docs currently say:

- Linux/macOS/WSL2 quick install uses `curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash`
- native Windows is not supported; WSL2 is the intended Windows path
- Hermes stores config in `~/.hermes/` by default, but if `HERMES_HOME` is set then `SOUL.md` is read from `$HERMES_HOME/SOUL.md`

Repo-local path added here:

1. Run `scripts/install_hermes_agent.sh` from WSL2/Linux.
2. Run `python scripts/bootstrap_hermes_profiles.py bootstrap`.
3. Point `HERMES_HOME` at one bootstrapped home when you want to run a specific role.

Example:

```bash
export HERMES_HOME="$PWD/services/hermes/runtime/profiles/spinetop-sentinel/home"
cd /path/to/Spinetop
hermes
```

This keeps the repo-owned role identity material local and reversible while still using Hermes' normal home-directory model.

## Role Mapping

Defined now:

- `spinetop-sentinel`
- `spinetop-expeditioner`
- `spinetop-helper-2b`
- `spinetop-mirror`

Deferred intentionally:

- `spinetop-nanny`

Each profile definition includes:

- profile name
- role purpose
- config root
- memory root and memory reference
- `SOUL.md` reference
- active/inactive control reference
- model/provider slot reference

## Separation Rules

Separation is explicit in two places:

1. `config/hermes_profile_registry.json`
   - every profile has its own runtime home, memory root, and `SOUL.md`
   - every profile sets `shared_identity_allowed`, `shared_memory_allowed`, and `shared_runtime_home_allowed` to `false`
2. `services/hermes/roles/<profile>/SOUL.md`
   - every role explicitly says what it is and what it must not become
   - each one forbids collapsing into the other Spinetop identities

This means the repo bootstrap keeps identity material separate even before Hermes is launched.

## Activation And Safe Defaults

The bootstrap does not introduce a new active-state file.

Instead, each profile points back to the existing control flag:

- Sentinel: `config/hermes_runtime.json#runtime_state.active`
- Expeditioner: `config/helper_model_registry.json#roles.spinetop_expeditioner.active`
- helper_2b: `config/helper_model_registry.json#roles.spinetop-helper_2b.active`
- Mirror: `config/helper_model_registry.json#roles.spinetop-mirror.active`

Safe defaults remain:

- Sentinel stays mapped to the existing active runtime
- Expeditioner stays inactive by default
- helper_2b stays inactive by default
- Mirror stays inactive by default

To inspect status:

```bash
python scripts/bootstrap_hermes_profiles.py status
```

To toggle the existing mapped control explicitly:

```bash
python scripts/bootstrap_hermes_profiles.py set-active spinetop-expeditioner active
python scripts/bootstrap_hermes_profiles.py set-active spinetop-expeditioner inactive
```

Those commands edit the already-existing runtime flags; they do not add a second source of truth.

## Verification

Run:

```bash
python scripts/bootstrap_hermes_profiles.py validate
python scripts/validate_expert_config.py
python scripts/test_hermes_profile_bootstrap.py
```

What these checks cover:

- registry structure is valid
- required roles exist
- profile separation is explicit
- tracked `SOUL.md` templates exist
- runtime homes and memory roots are not shared
- disabled-safe defaults still resolve through the existing runtime flags

## Intentionally Deferred

- `spinetop-nanny` profile definition
- automatic Hermes launch wrappers
- gateway/webhook/cron setup
- any Honcho write path
- any autonomous scheduler or self-trigger path
- any governance policy change
