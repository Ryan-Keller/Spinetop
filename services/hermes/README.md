# Hermes Bootstrap

This folder holds the repo-local bootstrap surface for external Hermes Agent profiles used with Spinetop.

What lives here:

- `roles/<profile>/`: tracked role templates, including `SOUL.md`
- `runtime/profiles/<profile>/home/`: optional bootstrapped Hermes homes created by `scripts/bootstrap_hermes_profiles.py`

What does not happen here:

- no background loop is started
- no governance state is changed unless the operator explicitly uses the activation command
- no hidden bridge or Honcho writes are added

Recommended environment:

- WSL2 or Linux
- run Hermes from a WSL/Linux checkout of this repo so generated paths stay native to that environment
