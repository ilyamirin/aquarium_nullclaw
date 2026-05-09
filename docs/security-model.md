# Security Model

Aquarium is strict about where secrets are allowed to exist.

## Core rule

Hosted NullClaw runtimes must never receive provider master keys.

That rule drives the whole platform design:

- Infisical stores secret material.
- LiteLLM holds provider access.
- NullClaw gets only a per-runtime LiteLLM key and non-LLM runtime secrets.

## Secret scopes

### LiteLLM core scope

The LiteLLM core secret scope stores:

- `LITELLM_MASTER_KEY`
- `OPENROUTER_API_KEY`
- future provider master credentials

Only LiteLLM and operator automation should need access to that scope.

### Runtime scopes

Each runtime gets its own secret scope in Infisical.

Examples:

- `test-nullclaw`
- `probe`
- `limit-probe`

Runtime scopes store:

- `LITELLM_API_KEY`
- Telegram secrets when enabled
- runtime-specific integration secrets

Runtime scopes do not store provider master credentials.

## Isolation model

The isolation boundary is project-per-runtime plus key-per-runtime.

That gives Aquarium a clean story for:

- tenant or runtime isolation
- per-runtime revocation
- per-runtime spend limits
- per-runtime model access

## LiteLLM boundary

LiteLLM is the mandatory gateway between hosted runtimes and model providers.

It owns:

- provider routing
- virtual/runtime keys
- budgets
- RPM and TPM limits

NullClaw sees LiteLLM as its model endpoint. It does not talk to OpenRouter directly in the hosted path.

## Known integration gap

The current wrapper deliberately does not patch upstream NullClaw.

That means error mapping depends on the payloads returned by the upstream provider boundary:

- LiteLLM RPM exhaustion maps cleanly to a user-visible `RateLimited` experience in NullClaw.
- LiteLLM budget exhaustion currently reaches NullClaw as a generic `ApiError`.

This is documented, not hidden.

## Practical public-demo posture

The repository is a real-only demo. It is not a zero-secret template.

To run the full path, evaluators need real:

- Infisical bootstrap secrets
- provider credentials
- optionally Telegram credentials

That tradeoff is intentional. The goal of the repository is to demonstrate the platform shape, not to ship a fake local mock of hosted agent infrastructure.
