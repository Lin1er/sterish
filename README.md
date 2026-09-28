<!--
  Sterish — Audited Skill Marketplace for AI Agents
  SPDX-License-Identifier: MIT
-->

# Sterish

[![Contracts](https://github.com/Lin1er/sterish/actions/workflows/contracts.yml/badge.svg)](https://github.com/Lin1er/sterish/actions/workflows/contracts.yml)
[![Pipeline & API](https://github.com/Lin1er/sterish/actions/workflows/pipeline.yml/badge.svg)](https://github.com/Lin1er/sterish/actions/workflows/pipeline.yml)
[![Frontend](https://github.com/Lin1er/sterish/actions/workflows/frontend.yml/badge.svg)](https://github.com/Lin1er/sterish/actions/workflows/frontend.yml)
[![Landing](https://github.com/Lin1er/sterish/actions/workflows/landing.yml/badge.svg)](https://github.com/Lin1er/sterish/actions/workflows/landing.yml)
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

## Deliverable 3 evidence — the demo video and the flow screenshots

> **Both exist and are published.** They were produced on **28 September 2026**, after the Instawards
> report had already been submitted, so that submission still lists them as outstanding. This section
> is the record that they are not.

| Evidence | Where to check it |
|---|---|
| **Demo video** — 2 min 52 s, narrated, the whole loop | **<https://sterish.xyz/demo.mp4>** (also [`docs/evidence/demo/sterish-demo.mp4`](docs/evidence/demo/sterish-demo.mp4)) |
| **Screenshots of the full flow** — nine full-page captures | [`docs/evidence/demo/screenshots`](docs/evidence/demo/screenshots) |
| **Evidence map** — every chapter tied to its transaction or endpoint | [`docs/evidence/demo/README.md`](docs/evidence/demo/README.md) |
| **Raw terminal recordings** — replayable with `asciinema play` | [`docs/evidence/demo/terminal-session.cast`](docs/evidence/demo/terminal-session.cast) |
| **Narration script**, word for word | [`docs/evidence/demo/narration.json`](docs/evidence/demo/narration.json) |

The video was recorded live against production: a skill registered, audited, and bought while
recording, then a poisoned one refused. The seven transactions it shows were re-checked against
Horizon afterwards — **7 of 7 successful**, ledgers 4916394 to 4916409, every one linked in the
evidence map.

Stated there rather than left to be noticed: the narration is synthetic, submission is still
operator-run, every wallet in the video belongs to the team, the model never decides a verdict, and
all of it is testnet.

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
│   │   ├── config.py                # settings read from the environment
│   │   ├── chain.py                 # registry reads over Stellar RPC
│   │   ├── indexer.py               # event tail -> SQLite cache, /feed
│   │   ├── models.py                # response schemas (api-spec v1.0.0)
│   │   ├── errors.py                # one error shape for every failure
│   │   ├── ratelimit.py             # per-IP fixed window
│   │   └── routes/check.py          # /check/by-hash, /check, /skills, /feed
│   └── tests/
├── frontend/                        # Next.js + TypeScript
│   ├── package.json
│   └── src/{app,components}/
├── docs/
│   ├── architecture.md
│   ├── api-spec.md                  # frozen v1.0.0 (STE-10)
│   ├── deployments.md               # testnet contract ids + tx evidence
│   ├── delivery-plan.md
│   └── specs/                       # frozen interfaces, events, verdict schema
├── scripts/                         # deploy-testnet.sh, verify-*.sh
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
| Node.js | 20+ (22 recommended) | `nvm install 22` | frontend |
| pnpm | 10+ (12 recommended) | `corepack enable pnpm` | frontend |
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
| `make install-frontend` | `pnpm install --frozen-lockfile` in `frontend/` |
| `make dev-frontend` | Next.js dev server on `:3000` |
| `make build-frontend` | `next build` (production build) |
| `make lint-frontend` | `next lint` |
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

### Contract WASM hashes

The three contracts are built and hash-pinned via `make build-wasm`
(`contracts/wasm-hashes.txt`). A Soroban contract is stored under `sha256(wasm)`,
so these are exactly the bytes that were uploaded:

| Contract | WASM sha256 (= Soroban wasm hash) |
|---|---|
| `sterish_registry` | `8c438004591f65d84f8087738c4ff327bc016b38e443b2661bb36f6cd3852489` |
| `sterish_escrow` | `cb241f74d20146b9d4895160e68d0c337f68317c3b6c1f272b0505cdb84d0ad0` |
| `sterish_tokens` | `318f44583ae3144a65c3992b163f91795b8f28a95d4bc59b4c2147ad00b83206` |

Re-verify with `make verify-wasm`.

Those hashes are the **`aarch64-apple-darwin`** build — the host that produced what is live on
testnet. A Soroban wasm build is byte-reproducible for a given host triple and *not* across host
triples, so `contracts/wasm-hashes.txt` records a row per host and `make verify-wasm` checks the
row for the host it runs on. On Linux it verifies the Linux row: real drift detection, but not a
reproduction of the deployed bytes. See
[`docs/deployments.md`](docs/deployments.md#what-a-third-party-can-verify-and-what-they-must-pin-ste-12)
for what a third party can check from any machine.

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
| `frontend.yml` | `pnpm install --frozen-lockfile` + `tsc --noEmit` + `next lint` + `next build` |

All three must be green before a PR is merged. Dependency caches (cargo
registry, uv cache, pnpm store) are enabled so a warm run is a few minutes.

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
- [x] Registry contract deployed to testnet (contract ID recorded) — Registry v2 `CCZJN366…` and Tokens v2 `CB6VK4EX…`, upgradeable behind a timelock ([`docs/deployments.md`](docs/deployments.md))
- [x] USDC escrow contract deployed to testnet — `CCVCNFXK…`, non-upgradeable by design ([`docs/deployments.md`](docs/deployments.md))
- [x] Unit tests passing — the `Contracts` CI workflow is green on `main`
- [x] Transaction links on stellar.expert — per deploy and per verdict ([`docs/deployments.md`](docs/deployments.md), [`docs/audit-evidence.md`](docs/audit-evidence.md))

### Deliverable 2: Audit Pipeline + Verification API
- [x] 10+ real skills audited end-to-end — all 13 `skills.stellar.org` catalogue skills, SAFE on chain ([`docs/audit-evidence.md`](docs/audit-evidence.md))
- [x] Poisoned/demo skill correctly flagged as DANGEROUS — 4/4 poisoned fixtures; measured false positives 0/16, false negatives 0/4
- [x] Audit verdicts posted on-chain — Registry v2 `CCZJN366…`, transaction per verdict ([`docs/audit-evidence.md`](docs/audit-evidence.md))
- [x] REST API serving `/check/{skill_id}/{version}` (and `/check/by-hash/{content_hash}`) and `/skills` — live at `https://api.sterish.xyz` ([`docs/api-spec.md`](docs/api-spec.md))
- [x] Audit reports with evidence hashes — `GET /reports/{skill_id}/{version}`; `sha256(report) == evidence_hash` verified for all **36** reports on 28 Sep 2026, reproducible from a clean clone with `uv run python pipeline/scripts/verify_onchain.py reports`

### Deliverable 3: Dashboard + x402 Licensing Demo
- [x] Live x402 pay-per-use payment on testnet — 402 → USDC payment → soulbound licence → 200, recorded against production with every tx linked ([`docs/evidence/d3-flow-transcript-2026-09-17.md`](docs/evidence/d3-flow-transcript-2026-09-17.md))
- [x] Working verification API — same transcript; `deploy/verify.sh` passes against production ([`docs/deployments.md`](docs/deployments.md))
- [x] Dashboard deployed on a public URL — [`app.sterish.xyz`](https://app.sterish.xyz), public since 24 Sep 2026 (STE-26); the landing page has its own deployment at [`sterish.xyz`](https://sterish.xyz) (STE-23)
- [x] Demo video of the full loop — 2 min 54 s recorded live on 28 Sep 2026, [`sterish.xyz/demo.mp4`](https://sterish.xyz/demo.mp4); the seven transactions in it were re-checked on Horizon, 7 of 7 successful ([`docs/evidence/demo/`](docs/evidence/demo/README.md))
- [x] Screenshots of the full flow — nine full-page captures of the live product ([`docs/evidence/demo/screenshots`](docs/evidence/demo/screenshots)), with the API side also recorded step by step in the transcript above

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
