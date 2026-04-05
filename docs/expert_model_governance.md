# Expert Model Governance

## Why Sentinel And Hermes Agent Must Stay Distinct

- Sentinel-Spinetop is the internal steward focused on operational stability, validation, and petitioning.
- Hermes-Spinelab is an external controller/scout that gathers signals and writes petitions, but does not define canonical truth.
- Hermes Agent is the external Nous framework/runtime and is not the same role as Sentinel-Spinetop.
- The separation prevents cross-contamination of exploratory work with truth-pipeline operations and reduces operator confusion.

## Why Local-First Matters

- Local models keep routine work fast, private, and bounded.
- API use is reserved for explicit, high-stakes escalation only.

## Why Linguist Is Advisory Only

- Linguist evaluates model performance and proposes changes.
- Production model changes require operator approval.

## Why Experts Must Stay In Lane

- Lanes prevent autonomy creep and role confusion.
- Each expert has defined allowed and forbidden actions.
- Lanes are enforced by runtime policy, not just documentation.

## Why Registry and Policy Are Separate

- Model registry lists available models.
- Expert policy defines which experts can use which models.
- This keeps execution decisions policy-driven and auditable.
