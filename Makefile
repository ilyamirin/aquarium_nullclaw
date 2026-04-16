.PHONY: hooks-install lint security-config security-fs security stack-config stack-health

PRE_COMMIT_HOME ?= $(CURDIR)/.cache/pre-commit
export PRE_COMMIT_HOME

hooks-install:
	pre-commit install --hook-type pre-commit --hook-type pre-push

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
