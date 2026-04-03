# Expert Templates

This folder contains file-based templates used by the expert scaffolding script.

## Templates
- `expert_template/`: Base files for `experts/<expert_name>/`.
- `memory_instance_template/`: Base files for `memory/instances/<expert_name>/`.

## Metadata Format (profile.json)
The `profile.json` file is the canonical metadata record for an expert.

Fields:
- `name`: snake_case identifier (matches the folder name).
- `display_name`: human-friendly name.
- `role`: short role label (e.g., `specialist`).
- `description`: short summary.
- `created_at`: ISO 8601 timestamp.
- `version`: schema version (string).
- `status`: `active` or `inactive`.
- `tags`: list of strings.
