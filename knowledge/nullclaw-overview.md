# NullClaw Overview In This Project

## What NullClaw Is

NullClaw is a compact Zig runtime for autonomous AI assistants.
It is not just a chat CLI. It is a pluggable agent platform with:

- model providers
- messaging channels
- tools
- memory backends
- scheduler and heartbeat
- HTTP gateway
- sandbox and security policy
- observability hooks

Upstream source lives in [nullclaw](/Users/ilyagmirin/PycharmProjects/aquarium/nullclaw).

## What We Use From Upstream

For our local stack we use upstream NullClaw as a runtime, not as an app framework we are rewriting.
The wrapper project is responsible for:

- container orchestration
- environment contract
- config generation
- operational documentation
- logs and debugging workflow
- future UI/hosting control integration

The upstream repository remains the source-of-truth for NullClaw internals.
Our stack is the source-of-truth for how we deploy and operate it locally.

## Why The Stack Uses Official Image

We use the official image first because it is the shortest path to:

- repeatable startup
- low operational friction
- fewer local toolchain dependencies
- clean separation between upstream runtime and our deployment layer

This choice is intentional.
If we later need to patch NullClaw itself, we can add a dev image based on the local clone without replacing the stable default path.

## Current Deployment Shape

The local deployment wrapper lives in [nullclaw-stack](/Users/ilyagmirin/PycharmProjects/aquarium/nullclaw-stack).

It is designed around:

- one long-running `gateway` container
- one optional `agent-cli` container for one-shot or interactive work
- a generated runtime `config.json`
- a local `data/` directory mounted into `/nullclaw-data`
- loopback-only exposure
- Telegram in private mode
- OpenRouter as the model provider

## Current Runtime Decisions

The current baseline decisions are:

- provider: OpenRouter
- model: `openrouter/qwen/qwen3.6-plus`
- Telegram mode: private allowlist
- allowed Telegram user ID: `373793732`
- gateway exposure: loopback only
- security mode: supervised, workspace-only
- shell/web expansion: not enabled by default
- logging and LLM I/O diagnostics: enabled

## Current Limitations

This is a safe starter stack, not a full-power autonomous environment.

Not enabled by default:

- open/public Telegram access
- unrestricted shell commands
- unrestricted filesystem access
- public webhooks
- tunnel exposure
- external web search providers
- broad HTTP tool usage

Those can be added later, but each one increases blast radius and should be documented in `knowledge/` when introduced.

## What We Can Use Immediately

With the starter configuration we expect to use:

- Telegram private chat with the configured user
- OpenRouter model responses
- in-session memory and persisted SQLite memory
- file operations inside workspace scope
- scheduler/heartbeat runtime features
- gateway health endpoint
- logs, token ledger, tool-call logs, message logs, and LLM I/O previews

## Why This Knowledge Matters

This project is intended to become a future UI/platform layer for hosting and managing NullClaw.
Because of that, the operational model here must stay explicit:

- how config is generated
- what secrets exist
- which services run
- how the stack is restarted
- what logs exist
- what assumptions are built into the runtime

That information must live here, not only in ad hoc chat threads.
