# Kanboard Operator

Use this skill when an operator asks to inspect or update Kanboard work.

Rules:
- Use only Aquarium's Kanboard adapter.
- Do not call Kanboard directly with raw credentials.
- Confirm project and task before mutating state.
- Report project, task, column, status, and requested next action.

Allowed adapters:
- `kanboard.projects`
- `kanboard.tasks`
- `kanboard.columns`
