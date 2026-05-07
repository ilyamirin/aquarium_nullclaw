# Telegram Operator

Use this skill for Telegram-facing Aquarium runtimes.

Rules:
- Diagnose channel behavior from configured integration state and diagnostics.
- Do not request or reveal Telegram bot tokens.
- Separate bot setup issues, allow-list issues, runtime health, and model failures.
- Suggest safe next steps for operators to test the channel.

Allowed adapters:
- `telegram.status`
- `telegram.test`
- `diagnostics.summary`
