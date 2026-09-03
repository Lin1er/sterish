.PHONY: build-contracts test-contracts coverage-contracts \
        build-wasm verify-wasm \
        deploy-registry deploy-escrow \
        install-pipeline test-pipeline run-pipeline \
        install-api run-api test-api \
        install-dashboard dev-dashboard \
        verify-spec verify-content-hash verify-soulbound

# Frozen specs (STE-10)
# verify-content-hash proves Python, TypeScript and Rust compute byte-identical
# content_hash values for every shared test vector; it exits non-zero on drift.
verify-content-hash:
	bash scripts/verify-content-hash.sh

# verify-soulbound (STE-11) reads the contract spec out of the built
# sterish_tokens.wasm and fails if any transfer/approve/burn entrypoint is
# exported. It proves the VERIFIED badge and the license token are soulbound by
# ABI shape, not by a runtime guard.
verify-soulbound:
	bash scripts/verify-soulbound.sh

# verify-spec is the umbrella gate for docs/specs/. It runs the content_hash
# cross-language proof, the soulbound ABI proof, plus the verdict-JSON schema
# runner once that lands.
verify-spec: verify-content-hash verify-soulbound
	@if [ -x scripts/verify-verdict-json.sh ]; then \
		echo ""; bash scripts/verify-verdict-json.sh; \
	else \
		echo ""; echo "note: scripts/verify-verdict-json.sh not present yet, skipping verdict schema checks"; \
	fi

# Contracts
build-contracts:
	cd contracts && cargo build --target wasm32v1-none --release

test-contracts:
	cd contracts && cargo test

# coverage-contracts (STE-12) prints the workspace line/region coverage AND
# fails when line coverage drops below 80%. Same two commands CI runs, so a red
# CI job is reproducible locally with one target.
coverage-contracts:
	cd contracts && cargo llvm-cov --workspace --summary-only
	cd contracts && cargo llvm-cov --workspace --fail-under-lines 80

# build-wasm (STE-12) is the CANONICAL wasm build: it is the only one that
# remaps $$CARGO_HOME out of the artifacts, so it is the only one whose sha256
# matches contracts/wasm-hashes.txt. Use it, not `build-contracts`, for anything
# that gets uploaded on-chain.
build-wasm:
	bash scripts/build-wasm.sh

# verify-wasm rebuilds and fails if any artifact drifted from the recorded hash.
verify-wasm:
	bash scripts/build-wasm.sh --check

deploy-registry:
	soroban-cli deploy --wasm target/wasm32v1-none/release/sterish_registry.wasm --source account --network testnet

deploy-escrow:
	soroban-cli deploy --wasm target/wasm32v1-none/release/sterish_escrow.wasm --source account --source-account-args="USDC_ADDRESS" --network testnet

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
