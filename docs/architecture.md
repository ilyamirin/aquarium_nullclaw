# Aquarium Architecture

Aquarium is a platform wrapper around an imported upstream NullClaw runtime. The point of the project is not to rewrite the runtime. The point is to show how to operate hosted agent runtimes with a proper control plane, a proper secrets boundary, and a proper LLM gateway.

## Component roles

```mermaid
flowchart TD
    ui["Operator UI / future tenant UI"] --> cp["Aquarium control plane"]
    cp --> inf["Infisical"]
    cp --> meta["Control-plane metadata DB"]
    cp --> runtimes["NullClaw runtimes"]
    runtimes --> litellm["LiteLLM proxy"]
    litellm --> providers["Model providers"]
```

### `orchestrator/`

The Python 3.12 orchestrator is the shared control-plane layer. It owns:

- runtime lifecycle
- local runtime inventory
- generated Docker Compose for hosted runtimes
- Infisical project and secret wiring
- LiteLLM virtual key provisioning
- budget and limit updates

### `controlplane/`

The Django + Unfold surface is the human operator UI. It exposes:

- runtime inventory
- runtime detail pages
- limits and key actions
- diagnostics and chat surfaces
- provider, integration, and secret management

### `infisical-stack/`

Infisical is the source of truth for secrets. Runtime projects store:

- per-runtime LiteLLM keys
- Telegram credentials
- other runtime-scoped secrets

The LiteLLM core secret scope stores provider master credentials. Runtimes never receive those credentials.

### `litellm-stack/`

LiteLLM is the mandatory LLM gateway for hosted runtimes. It owns:

- per-runtime keys
- budgets and rate limits
- provider routing
- a small internal admin UI/API

### `nullclaw/`

The upstream NullClaw checkout is intentionally treated as imported source. Aquarium wraps it. It does not casually modify it.

## Compose topology

The primary compose project names are part of the repo contract:

- `aquarium-infisical`
- `aquarium-litellm`
- `aquarium-nullclaw-runtimes`

Legacy/manual compose projects still exist as references only:

- `aquarium-nullclaw`
- `aquarium-nullclaw-probe`

Those legacy stacks are not the primary demo path.

## Default demo path

The minimal visible demo path is:

1. Infisical
2. LiteLLM
3. Django control plane
4. `test-nullclaw`

Monitoring stays in the repository but out of the default demo path so the public story stays small and readable.
