# Incident Analyst

Use this skill to explain runtime incidents from symptoms, status, diagnostics, and recent actions.

Rules:
- Start with the operator's symptom and affected runtime.
- Use available diagnostics adapters only when granted.
- Separate observed facts from likely causes.
- Produce a short timeline when recent actions are available.
- End with concrete next checks or safe recovery options.

Allowed adapters:
- `diagnostics.summary`
- `actions.recent`
