# Spinetop Docs

This index is organized around the active mirror-first system, not the older governance-heavy loop.

Start here:

- [Mirror Contract](mirror_contract_v1.md)
- [Agent Invocation Layer](agent_invocation_layer_v1.md)
- [Helper Catalog](helper_catalog_v1.md)
- [Architecture](architecture.md)
- [Record Schemas](record_schemas.md)
- [Artifact Kind Convention](artifact_kind_convention_v1.md)
- [Mission Artifact Manifest Schema](mission_artifact_manifest_schema_v1.md)
- [Archive Notes](ARCHIVE_NOTES.md)

Current live doctrine:

- operator `save:` goes directly to the mission-local mirror
- mirror reflection is visible and read-only outside its local lane
- concierge reads from the mirror but does not gain authority from it
- role execution is bounded and explicit

Legacy governance, dispatch, Honcho-bridge, and collective-truth documents remain available for compatibility and historical reference:

- [World Contract](doctrine.md)
- [State Machine](state_machine_v1.md)
- [Knowledge Flow](knowledge_flow_README.md)
- [Tool Use Governance](tool_use_governance_v1.md)
- [Autonomy Phase Plan](autonomy_phase_plan_v1.md)
