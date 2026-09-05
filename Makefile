.DEFAULT_GOAL := help

.PHONY: help \
        build-contracts test-contracts coverage-contracts fmt-contracts lint-contracts \
        build-wasm verify-wasm \
        deploy-registry deploy-escrow deploy-tokens deploy-testnet \
        install-pipeline test-pipeline lint-pipeline run-pipeline \
        install-api run-api test-api lint-api \
        install-dashboard dev-dashboard build-dashboard lint-dashboard \
        verify-spec verify-content-hash verify-soulbound \
        lint verify

# Stellar identity + network for deploy targets. Override: make deploy-testnet SOURCE=me
SOURCE   ?= sterish-admin
NETWORK  ?= testnet
WASM_DIR := contracts/target/wasm32v1-none/release

# Official USDC Stellar Asset Contract on testnet (a contract address, C...).
# NOT the classic issuer account (G...) — they are different and not interchangeable.
USDC_SAC_TESTNET ?= CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Frozen specs (STE-10) ---------------------------------------------------
verify-content-hash: ## Cross-language content_hash proof (Python/TS/Rust)
	bash scripts/verify-content-hash.sh

verify-soulbound: ## Prove the VERIFIED/license token is soulbound by ABI
	bash scripts/verify-soulbound.sh

verify-spec: verify-content-hash verify-soulbound ## Run every docs/specs/ gate
	@if [ -x scripts/verify-verdict-json.sh ]; then \
		echo ""; bash scripts/verify-verdict-json.sh; \
	else \
		echo ""; echo "note: scripts/verify-verdict-json.sh not present yet, skipping verdict schema checks"; \
	fi

# --- Contracts ---------------------------------------------------------------
build-contracts: ## Compile contracts to wasm (dev build)
	cd contracts && cargo build --target wasm32v1-none --release

test-contracts: ## Run contract unit + integration tests
	cd contracts && cargo test

fmt-contracts: ## Check Rust formatting
	cd contracts && cargo fmt --all -- --check

lint-contracts: ## Clippy over the contracts workspace
	cd contracts && cargo clippy --all-targets -- -D warnings

coverage-contracts: ## Contract coverage, fails under 80% lines
	cd contracts && cargo llvm-cov --workspace --summary-only
	cd contracts && cargo llvm-cov --workspace --fail-under-lines 80

# build-wasm (STE-12) is the CANONICAL, hash-stable wasm build. Use it, not
# build-contracts, for anything uploaded on-chain.
build-wasm: ## Canonical, reproducible wasm build (hash-stable)
	bash scripts/build-wasm.sh

verify-wasm: ## Rebuild and fail if any wasm drifted from wasm-hashes.txt
	bash scripts/build-wasm.sh --check

# Deploy targets use the modern Stellar CLI (`stellar contract deploy`).
# soroban-cli was renamed to stellar-cli in the 21.x line; `soroban-cli deploy`
# no longer exists.
deploy-registry: build-wasm ## Deploy the registry contract to testnet
	stellar contract deploy \
	  --wasm $(WASM_DIR)/sterish_registry.wasm \
	  --source-account $(SOURCE) \
	  --network $(NETWORK)

deploy-escrow: build-wasm ## Deploy the escrow contract to testnet
	stellar contract deploy \
	  --wasm $(WASM_DIR)/sterish_escrow.wasm \
	  --source-account $(SOURCE) \
	  --network $(NETWORK)

deploy-tokens: build-wasm ## Deploy the soulbound token contract to testnet
	stellar contract deploy \
	  --wasm $(WASM_DIR)/sterish_tokens.wasm \
	  --source-account $(SOURCE) \
	  --network $(NETWORK)

deploy-testnet: deploy-registry deploy-escrow deploy-tokens ## Deploy all three contracts
	@echo ""
	@echo "Record the contract IDs above in api/.env, pipeline/.env, and docs/deployments.md."
	@echo "USDC SAC (testnet, a C... contract address): $(USDC_SAC_TESTNET)"

# --- Pipeline ----------------------------------------------------------------
install-pipeline: ## Install pipeline dependencies
	cd pipeline && uv sync

test-pipeline: ## Run pipeline tests
	cd pipeline && uv run pytest tests/ -v

# Lint only. `ruff format --check` is deliberately not enforced: the tree predates
# any formatter run, and reformatting 15 files owned by other tickets from an infra
# ticket would bury real changes in noise. Adopt it in its own change if wanted.
lint-pipeline: ## Lint the pipeline
	cd pipeline && uv run ruff check src tests

run-pipeline: ## Audit one skill: make run-pipeline SKILL_ID=... MANIFEST=...
	cd pipeline && uv run python -m sterish_pipeline.cli audit \
	  --skill-id "$(SKILL_ID)" --manifest "$(MANIFEST)"

# --- API ---------------------------------------------------------------------
install-api: ## Install API dependencies
	cd api && uv sync

run-api: ## Start the verification API on :8000
	cd api && uv run uvicorn sterish_api.main:app --reload --port 8000

test-api: ## Run API tests
	cd api && uv run --extra dev pytest -v

lint-api: ## Lint the API
	cd api && uv run --extra dev ruff check src tests

# --- Dashboard ---------------------------------------------------------------
install-dashboard: ## Install dashboard dependencies (locked)
	npm ci --prefix dashboard

dev-dashboard: ## Dashboard dev server on :3000
	npm run dev --prefix dashboard

build-dashboard: ## Production build of the dashboard
	npm run build --prefix dashboard

lint-dashboard: ## Lint the dashboard
	npm run lint --prefix dashboard

# --- Rollups -----------------------------------------------------------------
lint: lint-pipeline lint-api lint-dashboard ## Lint pipeline + api + dashboard
	@echo "Rust lint runs via: make fmt-contracts lint-contracts"

verify: ## Run the CI sequence for pipeline + api + dashboard
	$(MAKE) install-pipeline
	$(MAKE) lint-pipeline
	$(MAKE) test-pipeline
	$(MAKE) install-api
	$(MAKE) lint-api
	$(MAKE) test-api
	$(MAKE) install-dashboard
	$(MAKE) lint-dashboard
	$(MAKE) build-dashboard
