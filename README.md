<!--
  Sterish — Audited Skill Marketplace for AI Agents
  SPDX-License-Identifier: MIT
-->

# Sterish

[![Contracts](https://github.com/Lin1er/sterish/actions/workflows/contracts.yml/badge.svg)](https://github.com/Lin1er/sterish/actions/workflows/contracts.yml)
[![Pipeline & API](https://github.com/Lin1er/sterish/actions/workflows/pipeline.yml/badge.svg)](https://github.com/Lin1er/sterish/actions/workflows/pipeline.yml)
[![Dashboard](https://github.com/Lin1er/sterish/actions/workflows/dashboard.yml/badge.svg)](https://github.com/Lin1er/sterish/actions/workflows/dashboard.yml)
![License](https://img.shields.io/badge/license-MIT-blue)
![Stellar](https://img.shields.io/badge/network-Stellar%20Testnet-6b21a8)

**Audited skill marketplace for AI agents on Stellar.**

Sterish provides an on-chain skill registry with multi-stage auditing,
x402 pay-per-use licensing, and trust scoring — so agents can discover, verify,
and pay for skills with cryptographic guarantees.

> **On-chain registry → Multi-stage audit → x402 pay-per-use licensing → Trust scoring**

📖 Full architecture: [`docs/architecture.md`](docs/architecture.md) ·
API spec: [`docs/api-spec.md`](docs/api-spec.md) ·
Delivery plan: [`docs/delivery-plan.md`](docs/delivery-plan.md)

---

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌────────────┐
│  Skill       │────▶│  Audit        │────▶│  Soroban    │
│  Developer   │     │  Pipeline     │     │  Registry    │
│              │     │  (3 stages)   │     │  Contract    │
└─────────────┘     └──────┬───────┘     └──────┬─────┘
                           │                     │
                           ▼                     ▼
                    ┌──────────────┐      ┌────────────┐
                    │  Trust Score │      │  USDC       │
                    │  Engine      │      │  Escrow     │
                    └──────────────┘      └──────┬─────┘
                                                 │
                                                 ▼
                                          ┌────────────┐
                                          │  x402       │
                                          │  Licensing  │
                                          └──────┬─────┘
                                                 │
                                                 ▼
                                          ┌────────────┐
                                          │  Agent /    │
                                          │  Consumer   │
                                          └────────────┘
```

---

## Project Structure

This is the layout that actually exists in the repository:

```
sterish/
├── contracts/                       # Cargo workspace (Soroban / Rust)
│   ├── Cargo.toml                   # workspace: members = registry, escrow
│   ├── registry/src/{lib,data,test}.rs
│   ├── escrow/src/{lib,data,test}.rs
│   ├── tokens/src/{lib,data,test}.rs   # soulbound VERIFIED badge + license (STE-11)
│   └── tests/                          # cross-contract integration tests
├── pipeline/                        # Audit pipeline (Python, uv)
│   ├── pyproject.toml
│   ├── src/sterish_pipeline/
│   │   ├── cli.py                   # `python -m sterish_pipeline.cli audit ...`
│   │   ├── config.py                # PipelineConfig
│   │   ├── models.py                # SkillManifest, AuditReport, ...
│   │   ├── onchain.py               # Soroban submission (see STERISH-12)
│   │   ├── sandbox.py               # Docker sandbox runner
│   │   └── stages/
│   │       ├── stage1_desc_scanner.py
│   │       ├── stage2_sandbox_check.py
│   │       └── stage3_verdict_synthesis.py
│   └── tests/
├── api/                             # Verification REST API (FastAPI, uv)
│   ├── pyproject.toml
│   ├── src/sterish_api/
│   │   ├── main.py                  # FastAPI app + /health
│   │   ├── models.py                # response schemas
│   │   ├── client.py                # registry reads
│   │   └── routes/check.py          # /check/{skill_id}, /skills
│   └── tests/
├── dashboard/                       # Next.js 14 + TypeScript
│   ├── package.json
│   └── src/{app,components}/
├── docs/
│   ├── architecture.md
│   ├── api-spec.md
│   └── delivery-plan.md
├── .github/workflows/               # contracts.yml, pipeline.yml, dashboard.yml
├── Makefile
└── README.md
```

Anything named in `docs/` that is not in the tree above is a design target, not
shipped code.

---

## Quickstart

### Prerequisites

| Tool | Version | Install | Needed for |
|---|---|---|---|
| Rust (stable) | 1.85+ | `rustup default stable` | contracts |
| `wasm32v1-none` target | — | `rustup target add wasm32v1-none` | contracts |
| `cargo-llvm-cov` | latest | `cargo install cargo-llvm-cov` | contract coverage |
| Stellar CLI | 22.x | `cargo install --locked stellar-cli --version "^22"` | contract deploy |
| Python | 3.12+ | `uv python install 3.12` | pipeline, api |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | pipeline, api |
| Node.js | 18+ (20 recommended) | `nvm install 20` | dashboard |
| Docker | latest | system package manager | pipeline stage 2 (optional) |

> The binary is `stellar`, not `soroban`. `soroban-cli` was renamed to
> `stellar-cli` in the 21.x line; every deploy command in this repo uses
> `stellar contract ...`.
>
> Docker is optional: with no Docker on `PATH`, pipeline stage 2 falls back to
> static capability analysis and the test suite still passes.

### Setup from a clean machine

```bash
git clone https://github.com/Lin1er/sterish.git
cd sterish

# 1. Contracts (needs Rust + wasm target)
make build-contracts
make test-contracts

# 2. Audit pipeline (needs uv)
make install-pipeline
make test-pipeline

# 3. Verification API — copy env template first
cp api/.env.example api/.env
make install-api
make test-api
make run-api                 # http://127.0.0.1:8000/health -> {"status":"ok",...}

# 4. Dashboard (separate terminal)
make install-dashboard
make dev-dashboard           # http://localhost:3000
```

Everything above is expected to complete in well under 30 minutes on a clean
machine; the bulk of that is the Rust toolchain download.

### Verify the install

```bash
make verify                  # contracts + pipeline + api + dashboard build
```

`make verify` is exactly what CI runs, so a green `make verify` locally means a
green PR.

---

## Environment configuration

Both Python services read configuration from a `.env` file that is **never**
committed. Templates live next to each service:

```bash
cp api/.env.example api/.env
cp pipeline/.env.example pipeline/.env
```

Fill in the contract IDs after a testnet deploy (see `make deploy-testnet`) and
your own secret keys.

**Secrets policy**

- `*.env` and `.env.*` are git-ignored; only `*.env.example` is tracked.
- Never paste a Stellar **secret key** (`S...`) into a ticket, PR, commit, log,
  or screenshot. Only public keys (`G...`) and contract IDs (`C...`) are safe to
  share.
- CI reads secrets from GitHub Actions secrets, never from the repo.
- If a secret is ever committed, rotate the key first, then rewrite history.

---

## Make Commands

| Command | Description |
|---|---|
| `make build-contracts` | Compile all contracts to WASM (`wasm32v1-none`, release) |
| `make build-wasm` | Canonical, hash-stable WASM build (matches `wasm-hashes.txt`) |
| `make verify-spec` | Cross-language `content_hash` proof + soulbound ABI proof |
| `make test-contracts` | Run contract unit tests (`cargo test`) |
| `make fmt-contracts` | `cargo fmt --check` over the contracts workspace |
| `make lint-contracts` | `cargo clippy` over the contracts workspace |
| `make deploy-testnet` | Deploy registry + escrow to Stellar Testnet via `stellar contract deploy` |
| `make install-pipeline` | `uv sync` the pipeline |
| `make test-pipeline` | Run pipeline tests |
| `make lint-pipeline` | `ruff check` + `ruff format --check` the pipeline |
| `make run-pipeline` | Audit one skill: `make run-pipeline SKILL_ID=... MANIFEST=...` |
| `make install-api` | `uv sync` the API |
| `make run-api` | Start FastAPI on `:8000` with reload |
| `make test-api` | Run API tests |
| `make lint-api` | `ruff check` + `ruff format --check` the API |
| `make install-dashboard` | `npm ci` in `dashboard/` |
| `make dev-dashboard` | Next.js dev server on `:3000` |
| `make build-dashboard` | `next build` (production build) |
| `make lint-dashboard` | `next lint` |
| `make lint` | All linters (Rust + Python + TypeScript) |
| `make verify` | Everything CI runs, in order |
| `make clean` | Remove build artifacts and virtualenvs |

Run `make help` for the same list generated from the Makefile itself.

---

## Addresses & deployment

### Fixed testnet address (constant)

| What | Address | Notes |
|---|---|---|
| USDC Stellar Asset Contract (testnet) | `CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA` | A **contract** address (`C...`) — the `@x402/stellar` USDC SAC. Not the classic issuer account (`G...`); the two are different and not interchangeable. |
| Network passphrase | `Test SDF Network ; September 2015` | |
| Soroban RPC | `https://soroban-testnet.stellar.org` | |

### Contract WASM hashes (built, pending deploy)

The three contracts are built and hash-pinned via `make build-wasm`
(`contracts/wasm-hashes.txt`). A Soroban contract is stored under `sha256(wasm)`,
so these are exactly what will be uploaded:

| Contract | WASM sha256 (= Soroban wasm hash) |
|---|---|
| `sterish_registry` | `8c438004591f65d84f8087738c4ff327bc016b38e443b2661bb36f6cd3852489` |
| `sterish_escrow` | `cb241f74d20146b9d4895160e68d0c337f68317c3b6c1f272b0505cdb84d0ad0` |
| `sterish_tokens` | `318f44583ae3144a65c3992b163f91795b8f28a95d4bc59b4c2147ad00b83206` |

Re-verify with `make verify-wasm`.

### Deployed contract IDs

> **Not deployed to testnet yet.** These land with STE-13; once deployed, the
> contract IDs are recorded here and in `docs/deployments.md`, and wired into
> `api/.env` and `pipeline/.env`.

| Contract | Testnet contract ID | stellar.expert |
|---|---|---|
| Registry | `C…` (pending STE-13) | — |
| Escrow | `C…` (pending STE-13) | — |
| Tokens (VERIFIED badge + license) | `C…` (pending STE-13) | — |

### Deploying

```bash
# One-time: create and fund an identity
stellar keys generate --global sterish-admin --network testnet --fund
stellar keys address sterish-admin

make build-wasm                       # canonical, hash-stable build
make deploy-testnet SOURCE=sterish-admin
```

`deploy-testnet` deploys registry + escrow + tokens and prints the contract IDs;
record them in `api/.env`, `pipeline/.env`, `docs/deployments.md`, and the table
above. Initialize escrow against the USDC SAC listed at the top of this section.

---

## Continuous Integration

Three workflows run on every pull request to `main`:

| Workflow | Jobs |
|---|---|
| `contracts.yml` | `cargo fmt --check` + `cargo clippy` (advisory), `cargo test`, release WASM build |
| `pipeline.yml` | `uv sync` + `ruff` + `pytest` for both `pipeline/` and `api/` |
| `dashboard.yml` | `npm ci` + `next lint` + `next build` |

All three must be green before a PR is merged. Dependency caches (cargo
registry, uv cache, npm cache) are enabled so a warm run is a few minutes.

`cargo fmt`/`cargo clippy` are advisory (`continue-on-error`) while the contract
interfaces are still being frozen in STERISH-1/5 — they report but do not block.
Tighten them to blocking, with `-D warnings`, once those tickets land.

**Branch protection on `main`** — enable in *Settings → Branches → Add rule*:
require the three status checks above, require 1 approving review, and disallow
force pushes. Until that is switched on, the same rules are honoured by
convention.

---

## Instawards Deliverables

### Deliverable 1: Soroban Registry + Escrow Contracts
- [x] Public GitHub repository with CI passing
- [ ] Registry contract deployed to testnet (contract ID recorded)
- [ ] USDC escrow contract deployed to testnet
- [ ] Unit tests passing
- [ ] Transaction links on stellar.expert

### Deliverable 2: Audit Pipeline + Verification API
- [ ] 10+ real skills audited end-to-end
- [ ] Poisoned/demo skill correctly flagged as DANGEROUS
- [ ] Audit verdicts posted on-chain
- [ ] REST API serving `/check/{skill_id}` and `/skills`
- [ ] Audit reports with evidence hashes

### Deliverable 3: Dashboard + x402 Licensing Demo
- [ ] Live x402 pay-per-use payment on testnet
- [ ] Working verification API
- [ ] Dashboard deployed on dev URL
- [ ] 3-minute demo video
- [ ] Screenshots of full flow

---

## Tech Stack

| Component | Technology |
|---|---|
| Smart Contracts | Soroban / Rust (`soroban-sdk` 22) |
| Data Validation | Python 3.12 / Pydantic 2 |
| REST API | FastAPI + Uvicorn |
| Dashboard | Next.js 14 + React 18 + TypeScript |
| Payments | x402 + USDC (Stellar Asset Contract) |
| Blockchain | Stellar Testnet (`stellar-sdk` for Python and JS) |
| Sandbox | Docker (optional; static fallback without it) |
| Trust Scoring | Weighted composite score engine |

---

## License

[MIT](LICENSE)
