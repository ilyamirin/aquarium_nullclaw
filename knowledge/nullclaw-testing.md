# NullClaw Testing

## Current Testing Intent

The current local stack is designed for staged testing:

1. stack and config sanity
2. OpenRouter model invocation
3. Telegram private-chat flow
4. observability verification
5. deeper tool and scheduler checks

## Smoke Tests

Minimum smoke checks:

- `docker compose config` succeeds
- runtime config exists and is valid JSON
- `gateway` starts successfully
- `curl http://127.0.0.1:3000/health` returns healthy response
- startup logs do not show config parsing failure

Current status:

- `render-config.sh` executed successfully
- generated `config.json` is valid JSON
- `docker compose config` passed
- `gateway` container started and became healthy
- host-side `/health` returned `{"status":"ok"}`

## OpenRouter / Model Tests

Required checks:

- one-shot agent invocation succeeds
- runtime uses OpenRouter
- configured model is `openrouter/qwen/qwen3.6-plus`
- LLM request and response previews appear in logs
- token usage ledger is written

Suggested manual command:

```bash
docker compose run --rm agent-cli agent -m "Say hello and confirm your model route."
```

Current status:

- verified with one-shot CLI run
- OpenRouter request succeeded
- model confirmed in response and logs as `openrouter/qwen/qwen3.6-plus`
- LLM request/response preview logs were emitted
- token metric log was emitted

## Telegram Tests

Current Telegram target:

- allowed user id: `373793732`

Private bot validation sequence:

1. ensure `gateway` is running
2. send a private message from the allowed Telegram account
3. confirm the bot responds
4. send a follow-up and confirm continuity
5. inspect logs for message receipt and outbound handling

Negative test:

- message from a non-allowlisted user should not be accepted

Current status:

- Telegram polling thread is running
- end-to-end private message test still needs a real message sent from the allowed Telegram account
- non-allowlisted rejection is not yet empirically verified

## Observability Tests

Expected signals:

- health endpoint works
- container logs are readable
- message receipt logs exist
- message payload logs exist
- tool-call logs exist when tools run
- LLM I/O logs exist
- token usage ledger exists

Audit logging:

- if confirmed in runtime output, record exact file path and example behavior
- if not yet verified, document that audit is a follow-up validation item

Current status:

- container logs and startup/runtime logs are confirmed
- tool-call logging is configured but not yet exercised by a real tool run
- message receipt/payload logging is configured but not yet exercised by a Telegram message
- LLM I/O logging is confirmed
- token usage ledger file is not yet confirmed on disk and should be treated as a follow-up check
- audit log file is not yet confirmed on disk and should be treated as a follow-up check

## Safe Capability Tests We Can Run Early

These are reasonable early tests without expanding trust boundaries:

- basic chat
- multi-turn chat continuity
- file reads and writes inside workspace
- `memory_store` and `memory_recall`
- scheduler-related checks

## Deferred Tests

Do not treat these as part of the first green path unless config is intentionally expanded:

- unrestricted shell execution
- unrestricted filesystem access
- public webhook channels
- tunnels
- external web search providers
- public/open bot access

## Known Risks / Follow-Ups

- Telegram runtime behavior must be validated against the real bot token in the actual deployed stack
- OpenRouter quota or provider-side limits may affect tool-heavy conversations
- audit logging path and exact runtime artifact location still need explicit runtime confirmation
- if the future UI layer manages secrets or config regeneration, this document must be updated with that contract
- Docker host health checks require the container bind override; do not revert to container-only `127.0.0.1` bind without re-validating host reachability
