# NullClaw Operations

## Stack Location

Our deployment wrapper lives in [nullclaw-stack](/Users/ilyagmirin/PycharmProjects/aquarium/nullclaw-stack).

Key files:

- compose file: [nullclaw-stack/docker-compose.yml](/Users/ilyagmirin/PycharmProjects/aquarium/nullclaw-stack/docker-compose.yml)
- env template: [nullclaw-stack/.env.example](/Users/ilyagmirin/PycharmProjects/aquarium/nullclaw-stack/.env.example)
- config generator: [nullclaw-stack/scripts/render-config.sh](/Users/ilyagmirin/PycharmProjects/aquarium/nullclaw-stack/scripts/render-config.sh)

## First-Time Setup

1. Copy `.env.example` to `.env`.
2. Fill in real secrets and confirm defaults.
3. Generate runtime config.
4. Start the `gateway` service.

Expected working directory:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium/nullclaw-stack
```

Wrapper-level helper commands also exist at the project root in [Makefile](/Users/ilyagmirin/PycharmProjects/aquarium/Makefile).

## Generate Runtime Config

Run:

```bash
./scripts/render-config.sh
```

This should create:

- `data/config.json`
- `data/workspace/`

If generation fails, do not start the stack before fixing the env contract.

## Start The Stack

Long-running runtime:

```bash
docker compose up -d gateway
```

Note:

- inside Docker, the gateway command overrides the bind host to `::`
- exposure is still restricted because the published host port is `127.0.0.1:3000`

Interactive or one-shot CLI:

```bash
docker compose run --rm agent-cli
```

One-shot command example:

```bash
docker compose run --rm agent-cli agent -m "hello"
```

## Stop The Stack

Stop the long-running runtime:

```bash
docker compose stop gateway
```

Remove stopped containers:

```bash
docker compose down
```

## Health Checks

Primary local health check:

```bash
curl http://127.0.0.1:3000/health
```

Current observed result in this project:

```json
{"status":"ok"}
```

Compose health should also reflect the same endpoint.

## Logs

Container logs:

```bash
docker compose logs -f gateway
```

NullClaw runtime logs inside mounted data should also be inspected if needed, depending on runtime behavior and service mode.

The important expected log categories are:

- startup/config parsing
- Telegram message receipt
- tool execution logs
- LLM I/O previews
- token usage ledger activity

Current observed startup log highlights:

- runtime starts successfully
- model resolves as `openrouter/qwen/qwen3.6-plus`
- provider resolves as `openrouter`
- gateway listens on `:::3000` inside the container
- Telegram polling thread starts

## Entering The CLI Container

Interactive CLI session:

```bash
docker compose run --rm agent-cli
```

Interactive shell for debugging the image environment:

```bash
docker compose run --rm --entrypoint sh agent-cli
```

## Safe Restart Procedure

When env or generated config changes:

1. regenerate `data/config.json`
2. run `docker compose config`
3. restart `gateway`

Suggested flow:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium
make stack-config
cd nullclaw-stack && docker compose up -d gateway
```

If only the long-running process needs a restart:

```bash
docker compose restart gateway
```

## Operational Notes

- The stack is intentionally loopback-only at startup.
- Telegram is intended to work without public webhook exposure in the starter setup.
- Public exposure, tunnels, or webhook-first flows must be documented before adoption.
- Any operational changes must also update `knowledge/`.
