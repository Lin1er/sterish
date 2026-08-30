.PHONY: build-contracts test-contracts deploy-registry deploy-escrow \
        install-pipeline test-pipeline run-pipeline \
        install-api run-api test-api \
        install-dashboard dev-dashboard

# Contracts
build-contracts:
	cd contracts && cargo build --target wasm32-unknown-unknown --release

test-contracts:
	cd contracts && cargo test

deploy-registry:
	soroban-cli deploy --wasm target/wasm32-unknown-unknown/release/registry.wasm --source account --network testnet

deploy-escrow:
	soroban-cli deploy --wasm target/wasm32-unknown-unknown/release/escrow.wasm --source account --source-account-args="USDC_ADDRESS" --network testnet

# Pipeline
install-pipeline:
	cd pipeline && uv sync

test-pipeline:
	cd pipeline && uv run pytest tests/ -v

run-pipeline:
	cd pipeline && uv run python -m sterish_pipeline.cli audit --skill-id <id> --manifest <path>

# API
install-api:
	cd api && uv sync

run-api:
	cd api && uv run uvicorn sterish_api.main:app --reload --port 8000

test-api:
	cd api && uv run pytest

# Dashboard
install-dashboard:
	npm install --prefix dashboard

dev-dashboard:
	npm run dev --prefix dashboard
