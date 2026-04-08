# Archive Notes

This folder includes legacy scripts that are not part of the active mirror-first interaction loop.

Reference scripts retained for later archive review:

- `prompt_translator.py`
- `create_dispatch_petition.py`
- `approve_to_collective.py`
- `governance_utils.py`
- `hermes_to_petition.py`
- `item_world_nanny.py`
- `return_all_control.py`
- `set_return_all.py`
- `honcho_bridge.py`
- `honcho_bridge_watcher.py`
- `run_honcho_bridge.sh`
- `start_honcho.sh`
- `start_honcho_bridge_watcher.sh`
- `start_item_world_nanny.sh`
- `start_return_all_control.bat`
- `test_nanny_system_signals_smoke.py`
- `hermes_v1_sample_snapshot.json`

Why these stay for now:

- Several scripts are still imported, referenced by docs, or useful for compatibility review.
- Their names reflect translator, governance, dispatch, nanny, return-all, or Honcho-era flows that are no longer operator-facing defaults.
- Removing or renaming them blindly would create avoidable risk for historical tooling and diagnostics.

Archive guidance:

- Do not treat these scripts as part of the live operator `save:` to mirror path unless a task explicitly proves otherwise.
- Prefer bundling them into a later archive pass once imports, docs, and tests are reduced further.
