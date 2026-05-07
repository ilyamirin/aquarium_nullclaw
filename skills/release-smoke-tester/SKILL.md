# Release Smoke Tester

Use this skill after creating or updating a runtime.

Rules:
- Use only approved runtime gateway and diagnostics adapters.
- Run the smallest smoke sequence that proves the runtime is reachable and configured.
- Record failures as action-oriented checks, not broad speculation.
- Include runtime id, model alias, channel state, and smoke-test result.

Allowed adapters:
- `runtime.smoke_test`
- `runtime.config.view`
- `diagnostics.summary`
