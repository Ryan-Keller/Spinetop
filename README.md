# Spinetop

Spinetop is the repo for the mirror-first mission console and supporting mission-local workbench flows.

Start here:

- [Docs Index](docs/README.md)
- [Mirror Contract](docs/mirror_contract_v1.md)
- [Agent Invocation Layer](docs/agent_invocation_layer_v1.md)
- [Helper Catalog](docs/helper_catalog_v1.md)
- [Architecture](docs/architecture.md)
- [Record Schemas](docs/record_schemas.md)

Current live loop:

- direct operator `save:` writes once to the mission-local mirror lane
- mirror notes stay visible and mission-local
- concierge may retrieve from the mirror read-only
- bounded role execution runs only when explicitly activated

Legacy governance, dispatch, and collective-truth documents remain in the repo as reference material. They do not define the active interaction loop.
