# Log Trace Investigator

Use this skill to investigate failures through Aquarium monitoring adapters.

Rules:
- Query only approved diagnostics adapters.
- Do not connect directly to Loki, Tempo, Mimir, Docker, or host files.
- Keep queries scoped to the requested runtime and time window.
- Summarize signal, noise, and likely cause separately.
- If monitoring is unavailable, return a degraded-mode explanation.

Allowed adapters:
- `diagnostics.logs`
- `diagnostics.traces`
- `diagnostics.metrics`
