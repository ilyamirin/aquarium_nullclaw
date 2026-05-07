# Secret Checker

Use this skill to check whether required runtime or integration secrets are present.

Rules:
- Read only secret metadata and coverage status.
- Never request, print, summarize, or infer raw secret values.
- Report missing, configured, verified, and error states separately.
- Link missing secrets to their owning integration or runtime where possible.

Allowed adapters:
- `secrets.coverage`
- `secrets.missing`
