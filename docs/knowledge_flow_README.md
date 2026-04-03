# Knowledge Flow

This is the operational playbook for knowledge movement. The canonical world contract lives in [`docs/doctrine.md`](./doctrine.md).

Current flow:

`memory/inbox -> memory/promotion -> memory/dispatch/pending -> memory/dispatch/approved -> memory/collective -> honcho`

Key rules:

- No direct writes from inbox to collective
- Promotion is candidate status only
- Dispatch approval is the governed gate into collective
- Collective writes require a governance trail
- Honcho is storage-only
- Ambiguous states defer rather than fail destructively

Canonical record contracts live in [`docs/record_schemas.md`](./record_schemas.md). The practical transition contract lives in [`docs/state_machine_v1.md`](./state_machine_v1.md).

## Minimal Inbox JSON Schema

Every inbox JSON item must include these fields:

- `source` (string)
- `expert_name` (string)
- `task` (string)
- `summary` (string)
- `key_findings` (array of non-empty strings)
- `confidence` (number)
- `recommended_action` (string)
- `promotion_candidate` (boolean)

Optional governance and timestamp fields are added by scripts:

- `promotion_timestamp`
- `validated_by`
- `validation_result`
- `approved_at`
- `approved_by`
- `approval_reason`
- `governance_decision_ref`
- `admitted_at`
- `candidate_id`
- `admission_actor`
- `durability_class`
- `archive_timestamp`
- `archive_reason` when provided
- `related_petition_id`
- `governance_decision_id`
- `governance_review_state`
- `governance_review_reason`
- `governance_approval_ref`

## Scripts

All scripts are in `scripts/` and require Python 3.

1. Validate inbox items:
```bash
python scripts/validate_inbox.py
python scripts/validate_inbox.py memory/inbox/example.json
```

2. Promote a reviewed inbox item to promotion and create a dispatch petition:
```bash
python scripts/promote_to_promotion.py memory/inbox/example.json
```

3. Move a promotion item through dispatch review and governed admission only if governance allows:
```bash
python scripts/approve_to_collective.py memory/promotion/example.json
```

4. Reject/archive an item from inbox or promotion:
```bash
python scripts/reject_to_archive.py memory/inbox/example.json
python scripts/reject_to_archive.py memory/promotion/example.json --reason "Not relevant"
```

5. Check which promotion and collective files are still legacy or out of contract:
```bash
python scripts/check_memory_schema_migration.py
```

## Expected Workflow

1. Drop JSON files into `memory/inbox`.
2. Run validation to ensure required fields and types.
3. If suitable and `promotion_candidate` is true, promote to `memory/promotion` and open a dispatch petition in `memory/dispatch/pending`.
4. Governance review decides whether the petition may move to `memory/dispatch/approved`.
5. Governed admission moves the approved record into `memory/collective`.
6. If rejected at any stage, archive to `memory/archive`.
