# Gitea Operator

Use this skill when an operator asks to inspect or update work in the configured Gitea instance.

Rules:
- Use only Aquarium's Gitea adapter.
- Do not run `git`, call arbitrary URLs, or use raw tokens.
- Confirm repository and target issue or pull request before mutating state.
- Summarize repository, issue, pull request, branch, and requested action.

Allowed adapters:
- `gitea.repositories`
- `gitea.issues`
- `gitea.pull_requests`
