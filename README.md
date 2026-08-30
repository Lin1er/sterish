<!--
  Sterish — Audited Skill Marketplace for AI Agents on Stellar
  SPDX-License-Identifier: MIT
-->

# Sterish

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)
![Stellar](https://img.shields.io/badge/network-Stellar%20Testnet-6b21a8)
![Grant](https://img.shields.io/badge/Instawards-%245k%20Grant-orange)

**Audited skill marketplace for AI agents on Stellar.**

Sterish provides an on-chain skill registry with multi-stage LLM-powered auditing,
x402 pay-per-use licensing, and trust scoring — so agents can discover, verify,
and pay for skills with cryptographic guarantees.

> **On-chain registry → Multi-stage LLM audit → x402 pay-per-use licensing → Trust scoring**

📖 Full architecture: [`docs/architecture.md`](docs/architecture.md)

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

```
sterish/
├── contracts/
│   ├── registry/          # Soroban skill registry contract
│   ├── escrow/            # USDC escrow for audit bonding
│   └── licenses/          # x402 license minting
├── pipeline/
│   ├── stage1_scanner/    # Tool description risk scanner
│   ├── stage2_sandbox/    # Sandboxed behavior analysis
│   ├── stage3_verdict/    # Verdict synthesis + trust scoring
│   └── shared/            # Common types and config
├── api/
│   ├── app.py             # FastAPI application
│   ├── routers/           # Endpoint routers
│   ├── models/            # Pydantic schemas
│   └── tests/             # API tests
├── dashboard/
│   ├── src/               # Next.js 14 + TypeScript source
│   ├── components/        # React components
│   └── public/            # Static assets
├── docs/
│   ├── architecture.md    # This document
│   ├── delivery-plan.md   # Instawards delivery plan
│   └── api-spec.md        # REST API specification
├── Makefile
└── README.md
```

---

## Quickstart

### Prerequisites

| Tool | Version | Install |
|---|---|---|
| Rust (stable) | 1.75+ | `rustup default stable` |
| soroban-cli | 22.x | `cargo install soroban-cli --version "^22"` |
| Python | 3.12+ | `pyenv install 3.12` or system package |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | 18+ | `nvm install 18` |
| Docker | latest | System package manager |

### Setup

```bash
git clone https://github.com/nousresearch/sterish.git
cd sterish

# Build and test contracts
make build-contracts
make test-contracts

# Install and test the audit pipeline
make install-pipeline
make test-pipeline

# Start the API
cp api/.env.example api/.env
make run-api

# Start the dashboard (separate terminal)
make dev-dashboard
```

---

## Make Commands

| Command | Description |
|---|---|
| `make build-contracts` | Compile all Soroban contracts to WASM |
| `make test-contracts` | Run contract unit tests (`cargo test`) |
| `make deploy-testnet` | Deploy contracts to Stellar Testnet |
| `make install-pipeline` | Install pipeline dependencies via `uv sync` |
| `make test-pipeline` | Run pipeline unit + integration tests |
| `make run-pipeline` | Execute full 3-stage audit on a skill |
| `make run-api` | Start FastAPI server on `:8000` |
| `make dev-dashboard` | Start Next.js dev server on `:3000` |
| `make test-api` | Run API test suite |
| `make test-e2e` | Run end-to-end integration tests |
| `make lint` | Lint all projects (Rust + Python + TypeScript) |

---

## Instawards Deliverables

### Deliverable 1: Soroban Registry + Escrow Contracts
- [ ] Public GitHub repository
- [ ] Registry contract deployed to testnet (contract ID recorded)
- [ ] USDC escrow contract deployed to testnet
- [ ] Unit tests passing (>90% coverage)
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
| Smart Contracts | Soroban / Rust |
| Data Validation | Python / Pydantic |
| REST API | FastAPI |
| Dashboard | Next.js 14 + React + TypeScript |
| Payments | x402 + USDC (Stellar Asset Contract) |
| Blockchain | Stellar Testnet |
| LLM Audit | Claude / GPT (stages 1 & 3) |
| Sandbox | Docker |
| Trust Scoring | Weighted composite score engine |

---

## License

[MIT](LICENSE)
