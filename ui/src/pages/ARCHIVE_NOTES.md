# Archive Notes

This folder still contains hidden legacy or reference surfaces that are no longer primary navigation targets.

Reference surfaces retained for later archive review:

- `HonchoItemWorld.tsx`
- `AgentMemoryTriadPage.tsx`
- `EmissaryReturnGatePage.tsx`
- `ExpressionConsolePage.tsx`

Current status:

- These surfaces are hidden from the main nav.
- They remain present because the hash routes and imports still exist.
- They are not the primary operator-facing path for the current mirror-first system.

Archive guidance:

- Prefer archiving these pages together later instead of deleting one at a time.
- Any future rename or removal should update `ui/src/App.tsx` and verify the UI build immediately after.
