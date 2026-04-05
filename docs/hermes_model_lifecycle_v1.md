# Sentinel Model Lifecycle v1

This document defines the small, manual lifecycle for local Sentinel models in Spinetop.

Compatibility note: the runtime file and script names remain `hermes_*` in this stage so existing automation and stored references continue to work.

It is intentionally boring:

- no autonomy
- no hidden switching
- no automatic promotion
- no production write path changes

## Terms

- `production local model`: the trusted default local Sentinel model used for normal manual runs.
- `onboarding candidate`: a local model that must be trained/tested before it is treated as production.
- `promotion criteria`: the explicit checks the operator uses before marking an onboarding candidate ready.
- `selected onboarding target`: the one onboarding candidate the operator chooses for the current test pass.

## Current Local Profiles

| Profile key | Model | Role | Readiness | Notes |
|---|---|---|---|---|
| `local_production_qwen2_5_coder_14b` | `qwen2.5-coder:14b` | production default | ready | Default Sentinel local model |
| `local_onboarding_gemma4_e4b_4k` | `gemma4:e4b-4k` | onboarding candidate | needs validation | Manual onboarding target |

## Runtime Config Structure

[`config/hermes_runtime.json`](../config/hermes_runtime.json) now carries the lifecycle metadata:

- `production_model_key`: the stable local default
- `default_model_key`: same value as the production model key
- `onboarding_model_keys`: one or more candidate model keys
- `selected_onboarding_model_key`: the operator's chosen onboarding target, if one is selected
- `model_profiles`: per-model readiness metadata

The profile entries are explicit and keyed by model identity, so multiple onboarding candidates can exist at once.

## Promotion Criteria

An onboarding candidate is only ready for promotion when the operator can verify all of the following manually:

- it returns valid Sentinel JSON for repeated runs
- it stays inside the governed output schema
- it does not invent autonomy, truth-writing, or automatic switching
- it behaves consistently on the intended Sentinel modes
- it does not require hidden fallback behavior to look correct

The config records `promotion_ready` and `readiness`, but those values are manual status flags only.

## Selection Rules

- Normal Sentinel runs use the production default model.
- Onboarding runs must name the target explicitly with `--onboarding-model-key`.
- If more onboarding candidates are added later, the operator chooses the one to test by key.
- Nothing switches automatically based on readiness.

## Example Runs

- Production run:
  - `python scripts/run_hermes_v1.py observe`
- Onboarding run:
  - `python scripts/run_hermes_v1.py observe --onboarding-model-key local_onboarding_gemma4_e4b_4k`
- List the current lifecycle:
  - `python scripts/run_hermes_v1.py --list-models`
