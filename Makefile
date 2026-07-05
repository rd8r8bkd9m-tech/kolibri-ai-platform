SHELL := /bin/bash
CARGO := cargo
PNPM := pnpm

WORKSPACE := .
SERVICES_DIR := services
CRATES_DIR := crates

help:
	@printf "Kolibri Foundation make targets:\n"
	@printf "  make help             - Show this help\n"
	@printf "  make dev-up           - Start local dev infra\n"
	@printf "  make dev-down         - Stop local dev infra\n"
	@printf "  make migrate          - Run migration helper scripts\n"
	@printf "  make locald           - Run kolibri-locald\n"
	@printf "  make control-plane    - Run control-plane stub\n"
	@printf "  make agent            - Run kolibri-agent stub\n"
	@printf "  make scheduler        - Run scheduler stub\n"
	@printf "  make station          - Run station UI build (if exists)\n"
	@printf "  make test             - Run Rust + frontend checks\n"
	@printf "  make fmt              - cargo fmt --all\n"
	@printf "  make clippy           - cargo clippy --workspace\n"
	@printf "  make release          - Build release artifacts manifest\n"

dev-up:
	@if [ -f infra/docker-compose.dev.yml ]; then \
		docker compose -f infra/docker-compose.dev.yml up -d; \
	else \
		echo "Missing infra/docker-compose.dev.yml"; \
		exit 1; \
	fi

dev-down:
	@if [ -f infra/docker-compose.dev.yml ]; then \
		docker compose -f infra/docker-compose.dev.yml down; \
	else \
		echo "Missing infra/docker-compose.dev.yml"; \
		exit 1; \
	fi

migrate:
	@echo "Migration orchestration is repository-specific and implemented per service."

locald:
	$(CARGO) run -p kolibri-locald

control-plane:
	@if [ -d services/control-plane ]; then \
		$(CARGO) run -p kolibri-control-plane; \
	else \
		echo "control-plane service not bootstrapped yet"; exit 1; \
	fi

agent:
	@if [ -d services/agent ]; then \
		$(CARGO) run -p kolibri-agent; \
	else \
		echo "agent service not bootstrapped yet"; exit 1; \
	fi

scheduler:
	@if [ -d services/scheduler ]; then \
		$(CARGO) run -p kolibri-scheduler; \
	else \
		echo "scheduler service not bootstrapped yet"; exit 1; \
	fi

station:
	@if [ -d apps/station ]; then \
		$(PNPM) --filter @kolibri/station dev; \
	else \
		echo "Tauri/React station not bootstrapped yet"; exit 1; \
	fi

fmt:
	$(CARGO) fmt --all

clippy:
	$(CARGO) clippy --workspace -- -D warnings

test:
	$(CARGO) test --workspace
	$(PNPM) install --ignore-scripts
	@if [ -d apps/station ]; then \
		$(PNPM) --filter @kolibri/station build; \
	else \
		echo "skip ui build: apps/station not ready"; \
	fi

release:
	@mkdir -p release/artifacts
	@$(CARGO) build --workspace --release
	@echo "Release binaries built (if services are available)." > release/artifacts/release-notes.txt
