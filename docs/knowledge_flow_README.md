# Manual Knowledge Promotion Workflow

This project uses a manual, file-based promotion pipeline for knowledge flow:

`memory/inbox -> memory/promotion -> memory/collective OR memory/archive`

Key rules:
- No auto-promotion
- No direct writes from inbox to collective
- Human review at each step

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

Optional timestamp fields are added by scripts:
- `promotion_timestamp`
- `approval_timestamp`
- `archive_timestamp`
- `archive_reason` (when provided)

## Scripts
All scripts are in `scripts/` and require Python 3.

1. Validate inbox items:
```
python scripts/validate_inbox.py
python scripts/validate_inbox.py memory/inbox/example.json
```

2. Promote a reviewed inbox item to promotion:
```
python scripts/promote_to_promotion.py memory/inbox/example.json
```

3. Approve a promotion item to collective:
```
python scripts/approve_to_collective.py memory/promotion/example.json
```

4. Reject/archive an item from inbox or promotion:
```
python scripts/reject_to_archive.py memory/inbox/example.json
python scripts/reject_to_archive.py memory/promotion/example.json --reason "Not relevant"
```

## Expected Workflow
1. Drop JSON files into `memory/inbox`.
2. Run validation to ensure required fields and types.
3. Human review. If suitable and `promotion_candidate` is true, promote to `memory/promotion`.
4. Human review in promotion. If approved, move to `memory/collective`.
5. If rejected at any stage, archive to `memory/archive`.
