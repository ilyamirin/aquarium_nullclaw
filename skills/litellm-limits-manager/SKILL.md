# LiteLLM Limits Manager

Use this skill when an operator asks about LiteLLM key state, budgets, RPM/TPM limits, or limit-related failures.

Rules:
- Use only the LiteLLM admin adapters exposed by Aquarium.
- Never ask for or reveal provider master keys.
- Distinguish configured runtime limits from observed limit failures.
- Recommend limit changes only with the affected runtime, model alias, and current values.

Allowed adapters:
- `litellm.key.inspect`
- `litellm.limits.read`
- `litellm.failures`
