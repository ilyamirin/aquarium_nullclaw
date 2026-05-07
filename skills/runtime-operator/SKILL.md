# Runtime Operator

Use this skill when an operator asks to inspect or change an Aquarium runtime lifecycle.

Rules:
- Use only Aquarium runtime adapters exposed by the control plane.
- Do not run shell commands or edit runtime files directly.
- Confirm the target runtime before lifecycle changes.
- Prefer read-only status checks before start, stop, restart, recreate, or smoke-test actions.
- Report action results with runtime id, lifecycle status, health status, and next diagnostic step.

Allowed adapters:
- `runtime.status`
- `runtime.start`
- `runtime.stop`
- `runtime.restart`
- `runtime.smoke_test`
