# NullClaw Config And Environment

## Config Strategy

We do not hand-edit a tracked NullClaw runtime config in the repository.

Instead:

- secrets live in `.env`
- `.env.example` documents the contract
- the runtime `config.json` is generated into `nullclaw-stack/data/config.json`
- the generated config is not committed

This is required because upstream NullClaw does not expand `${VAR}` placeholders inside `config.json`.

## Primary Files

- env contract: [nullclaw-stack/.env.example](/Users/ilyagmirin/PycharmProjects/aquarium/nullclaw-stack/.env.example)
- generator: [nullclaw-stack/scripts/render-config.sh](/Users/ilyagmirin/PycharmProjects/aquarium/nullclaw-stack/scripts/render-config.sh)
- generated runtime config: [nullclaw-stack/data/config.json](/Users/ilyagmirin/PycharmProjects/aquarium/nullclaw-stack/data/config.json)

## Runtime Environment Variables

Required:

- `OPENROUTER_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOW_FROM`

Defaulted in `.env.example`:

- `NULLCLAW_MODEL=openrouter/qwen/qwen3.6-plus`
- `NULLCLAW_GATEWAY_PORT=3000`
- `NULLCLAW_GATEWAY_HOST=127.0.0.1`
- `NULLCLAW_REQUIRE_PAIRING=true`
- `NULLCLAW_AUTONOMY_LEVEL=supervised`
- `NULLCLAW_WORKSPACE_ONLY=true`
- `NULLCLAW_MAX_ACTIONS_PER_HOUR=20`
- `NULLCLAW_LOG_TOOL_CALLS=true`
- `NULLCLAW_LOG_MESSAGE_RECEIPTS=true`
- `NULLCLAW_LOG_MESSAGE_PAYLOADS=true`
- `NULLCLAW_LOG_LLM_IO=true`
- `NULLCLAW_TOKEN_USAGE_LEDGER_ENABLED=true`
- `NULLCLAW_OTEL_ENABLED=false`
- `NULLCLAW_OTEL_ENDPOINT=`
- `NULLCLAW_OTEL_SERVICE_NAME=nullclaw-local`

## Generated Config Blocks

The generated `config.json` includes:

- `models.providers.openrouter.api_key`
- `agents.defaults.model.primary`
- `channels.cli = true`
- `channels.telegram.accounts.main`
- `memory.backend = "sqlite"`
- `memory.auto_save = true`
- `gateway.host`
- `gateway.port`
- `gateway.require_pairing`
- `autonomy.level`
- `autonomy.workspace_only`
- `autonomy.max_actions_per_hour`
- `diagnostics.*`

## Telegram Decisions

Current Telegram decisions:

- account id: `main`
- reply mode: private replies enabled
- streaming: enabled
- draft previews: disabled
- binding commands: enabled
- allowlist is explicit and private
- allowed user id: `373793732`

Reason:

- private bot is the safest way to validate the integration
- explicit allowlist avoids accidental public bot behavior
- streaming is useful for observing incremental response behavior
- draft previews are disabled because upstream docs note that they can be visually confusing

## OpenRouter Decisions

Current provider decisions:

- provider: `openrouter`
- primary model: `openrouter/qwen/qwen3.6-plus`

Reason:

- the model exists on OpenRouter
- it matches the requested setup
- it is suitable for general assistant and coding-style workloads

## Security Defaults

The starter config intentionally keeps strong defaults:

- loopback-only gateway bind
- pairing enabled
- supervised autonomy
- workspace-only file scope
- no `allowed_commands = ["*"]`
- no `allowed_paths = ["*"]`
- `http_request.enabled = false`
- no public tunnel/webhook setup

These defaults exist to keep the first deployment easy to reason about.

## Container Bind Behavior

There is one important Docker-specific nuance:

- generated runtime config still uses `gateway.host = "127.0.0.1"`
- the `gateway` container is started with CLI bind override `--host :: --port 3000`
- Docker then publishes that container port only to `127.0.0.1` on the host

Reason:

- binding only to container loopback makes host-side published port checks unreliable
- binding wider inside the container is acceptable here because Docker still limits exposure to host loopback
- this mirrors the upstream container approach more closely than a pure config-only bind

## Diagnostics Defaults

Diagnostics are intentionally verbose because this stack is also an operational prototype.

Enabled by default:

- tool-call logs
- message receipt logs
- message payload logs
- LLM request/response preview logs
- token usage ledger

OTel is left optional behind env switches so the stack can stay simple locally while still having a path toward external observability.

## Future Expansion Points

If we later enable any of the following, this file must be updated:

- shell allowlist
- web search providers
- HTTP request tool
- tunnel provider
- public webhook channels
- multiple Telegram accounts
- multiple agent profiles and bindings
- OTel exporter
