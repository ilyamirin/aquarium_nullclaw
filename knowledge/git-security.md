# Git, Hooks, and Security Baseline

## Git Layout

The project root `aquarium/` is its own standalone git repository.

The local upstream checkout in `nullclaw/` is intentionally ignored.
We do not version-control upstream NullClaw here and we do not plan to modify it in this wrapper repository.

## Ignore Rules

The root `.gitignore` intentionally excludes:

- `nullclaw/`
- `nullclaw-stack/.env`
- `nullclaw-stack/data/`
- editor junk and temp files
- scan artifacts and caches

Tracked wrapper assets include:

- `knowledge/`
- `nullclaw-stack/.env.example`
- `nullclaw-stack/docker-compose.yml`
- `nullclaw-stack/scripts/`

## Hook Runner

We use `pre-commit` as the single hook orchestrator.

Installed hook types:

- `pre-commit`
- `pre-push`

This keeps local quality and security checks consistent without handwritten shell hooks.

For daily use, prefer the root [Makefile](/Users/ilyagmirin/PycharmProjects/aquarium/Makefile) instead of memorizing individual commands.

The root `Makefile` sets `PRE_COMMIT_HOME` to a repo-local cache under `.cache/pre-commit`.
That keeps hook environments reproducible inside this project and avoids depending on global user cache state.
Its `lint` target also checks tracked and untracked non-ignored files, so the workflow still works before the first commit exists.

## Mandatory Local Secret Blocking

`gitleaks` is the hard blocker in local hooks.

Reason:

- this repo handles provider keys, bot tokens, generated config, and operational docs
- accidental secret commits are a concrete risk here
- `gitleaks` is fast and appropriate for staged-content protection

## Linting Baseline

Current practical linting baseline:

- shell scripts: `shellcheck`, `shfmt`
- YAML / Compose: `yamllint`, `check-yaml`
- JSON: `check-json`
- repo hygiene: EOF fixer, trailing whitespace, line ending normalization, merge conflict detection, private key detection, large file checks
- generated runtime config validation when `nullclaw-stack/data/config.json` exists

This matches the current wrapper repo shape: docs, shell, YAML, and generated config.

Shell linting uses locally installed binaries instead of the `shellcheck-py` wrapper.
Reason: the wrapper proved less reliable in this environment than direct system tools.

Current CI implication:

- GitHub Actions on `ubuntu-latest` must install `shellcheck` and `shfmt` before running `make lint`
- otherwise the local `language: system` pre-commit hooks fail even when the Python environment is correct

## Security Scanner Recommendation

Recommended now:

- `gitleaks` for secret leakage prevention
- `Trivy` for filesystem, config, and container-oriented security scanning

Why Trivy is the balanced default:

- this repo is infrastructure-heavy rather than application-heavy
- Trivy is good at config and deployment misconfiguration scanning
- it fits Docker Compose and operational wrapper projects well

In this repository, Trivy is intentionally scoped to the wrapper project only.
It skips:

- `.cache/`
- `.git/`
- `nullclaw/`
- `nullclaw-stack/data/`

Reason:

- `nullclaw/` is an ignored upstream checkout, not part of this wrapper repo
- `.cache/` and generated runtime state create noisy findings that do not represent versioned project risk

For misconfiguration scanning specifically, the primary target is `nullclaw-stack/`, because that is where the actual deployable Compose and runtime wrapper config lives.
Compose syntax and renderability are also enforced separately by `scripts/check-compose-config.sh`, because that gives more reliable signal for this stack than Trivy misconfig detection alone.

Recommended next:

- `Semgrep`

Why Semgrep is next-layer, not first mandatory local gate:

- the current repo has very little app code
- the highest-value local problem right now is secrets plus config/container hygiene
- Semgrep becomes more valuable once this wrapper grows into a UI/platform codebase

## Manual Security Commands

Before pushing significant changes, run:

```bash
make lint
make security
```

Equivalent low-level commands still work:

```bash
pre-commit run --all-files
./scripts/check-security.sh config
./scripts/check-security.sh fs
```

For this repository specifically, `make lint` is preferred over raw `pre-commit run --all-files` during early bootstrap because the repo may still contain only untracked files.

If `trivy` is not installed yet, install it first.

On macOS with Homebrew:

```bash
brew install trivy
brew install shellcheck shfmt
```

Then run:

```bash
trivy config /Users/ilyagmirin/PycharmProjects/aquarium
trivy fs /Users/ilyagmirin/PycharmProjects/aquarium
```

If we decide to add the next security layer later, install Semgrep like this:

```bash
brew install semgrep
```

Recommended later usage:

```bash
semgrep scan --config auto /Users/ilyagmirin/PycharmProjects/aquarium
```

Semgrep is intentionally not a mandatory local blocker yet.
At the moment, the Homebrew `semgrep` binary on this machine fails immediately with a trust-anchor initialization error, so it is installed but not wired into the default local workflow yet.

## Preferred Developer Commands

Install git hooks:

```bash
make hooks-install
```

Run all local lint and hook-backed checks:

```bash
make lint
```

Run security scans:

```bash
make security
```

## Future Direction

When this repository grows into a real hosting/UI platform, revisit the baseline and likely add:

- Semgrep as pre-push or CI gate
- language-specific linters for the app stack
- CI enforcement for the same hook/security policy
