# Archive Notes

The `upstream/` subtree is a vendored Honcho service bundle retained for compatibility, reference, and local service experiments.

Current repo posture:

- The active operator loop is direct `save:` to mission-local mirror.
- Visible mirror rendering does not require this vendored subtree.
- Concierge mirror retrieval in the current spine is mission-local and read-only.

Why this bundle stays for now:

- Service scripts and older docs still reference Honcho-related paths.
- Mirror and helper contracts still mention Honcho-backed inspection in legacy wording.
- Removing the vendored subtree would be a medium/high-risk repo surgery, not a cleanup-only pass.

Archive guidance:

- Treat this folder as a historical service bundle unless a task explicitly targets Honcho service work.
- Review it later as one archive candidate rather than deleting files piecemeal.
