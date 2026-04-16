.PHONY: hooks-install lint security-config security-fs security stack-config stack-health infisical-up infisical-health infisical-bootstrap probe-stack-config probe-stack-health live-up probe-up orchestrator-install orchestrator-init orchestrator-list orchestrator-status-live orchestrator-status-probe orchestrator-probe-check

PRE_COMMIT_HOME ?= $(CURDIR)/.cache/pre-commit
export PRE_COMMIT_HOME

hooks-install:
	pre-commit install --hook-type pre-commit --hook-type pre-push

orchestrator-install:
	.venv/bin/pip install -e .[dev]

orchestrator-init:
	.venv/bin/orchestrator init

orchestrator-list:
	.venv/bin/orchestrator runtime list

orchestrator-status-live:
	.venv/bin/orchestrator runtime status --id test-nullclaw

orchestrator-status-probe:
	.venv/bin/orchestrator runtime status --id probe

orchestrator-probe-check:
	.venv/bin/orchestrator runtime probe-check --id probe --target test-nullclaw

lint:
	./scripts/run-lint.sh

security-config:
	./scripts/check-security.sh config

security-fs:
	./scripts/check-security.sh fs

security: security-config security-fs

stack-config:
	cd nullclaw-stack && ./scripts/render-config.sh && docker compose config

stack-health:
	curl -sS http://127.0.0.1:3000/health

probe-stack-config:
	cd nullclaw-probe-stack && ./scripts/render-config.sh && docker compose config

probe-stack-health:
	curl -sS http://127.0.0.1:3002/health

infisical-up:
	cd infisical-stack && docker compose up -d

infisical-health:
	curl -sS http://127.0.0.1:18080/api/status

infisical-bootstrap:
	./scripts/bootstrap-infisical-projects.sh

live-up:
	cd nullclaw-stack && docker compose up -d gateway

probe-up:
	cd nullclaw-probe-stack && docker compose up -d gateway
