.PHONY: hooks-install lint security-config security-fs security stack-config stack-health infisical-up infisical-health infisical-bootstrap litellm-up litellm-health litellm-status monitoring-bootstrap monitoring-up monitoring-health monitoring-logs monitoring-down probe-stack-config probe-stack-health live-up probe-up orchestrator-install orchestrator-init orchestrator-list orchestrator-status-live orchestrator-status-probe orchestrator-status-limit orchestrator-probe-check orchestrator-litellm-bootstrap controlplane-migrate controlplane-import-state controlplane-bootstrap-operator controlplane-run controlplane-start controlplane-stop controlplane-status controlplane-check demo-up demo-check demo-down

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

orchestrator-litellm-bootstrap:
	.venv/bin/orchestrator litellm bootstrap

orchestrator-status-live:
	.venv/bin/orchestrator runtime status --id test-nullclaw

orchestrator-status-probe:
	.venv/bin/orchestrator runtime status --id probe

orchestrator-status-limit:
	.venv/bin/orchestrator runtime status --id limit-probe

litellm-status:
	.venv/bin/orchestrator litellm status

orchestrator-probe-check:
	.venv/bin/orchestrator runtime probe-check --id probe --target test-nullclaw

controlplane-migrate:
	.venv/bin/python manage.py migrate

controlplane-import-state:
	.venv/bin/python manage.py import_runtime_state

controlplane-bootstrap-operator:
	.venv/bin/python manage.py bootstrap_operator --username admin --password admin --email admin@aquarium.local

controlplane-run:
	.venv/bin/python manage.py runserver 127.0.0.1:15000

controlplane-start:
	./scripts/controlplane-dev-server.sh start

controlplane-stop:
	./scripts/controlplane-dev-server.sh stop

controlplane-status:
	./scripts/controlplane-dev-server.sh status

controlplane-check:
	.venv/bin/python manage.py check

demo-up:
	./scripts/demo-up.sh

demo-check:
	./scripts/demo-check.sh

demo-down:
	./scripts/demo-down.sh

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

litellm-up:
	cd litellm-stack && docker compose up -d

litellm-health:
	curl -sS http://127.0.0.1:14000/health/liveliness

monitoring-bootstrap:
	./scripts/bootstrap-monitoring-stack.sh

monitoring-up:
	cd monitoring-stack && docker compose up -d

monitoring-health:
	curl -fsS http://127.0.0.1:13000/api/health
	curl -fsS http://127.0.0.1:13100/ready
	curl -fsS http://127.0.0.1:13200/ready
	curl -fsS http://127.0.0.1:13300/ready
	curl -fsS http://127.0.0.1:12345/

monitoring-logs:
	cd monitoring-stack && docker compose logs -f

monitoring-down:
	cd monitoring-stack && docker compose down

live-up:
	cd nullclaw-stack && docker compose up -d gateway

probe-up:
	cd nullclaw-probe-stack && docker compose up -d gateway
