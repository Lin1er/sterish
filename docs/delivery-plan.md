# Sterish — Instawards Delivery Plan

> $5,000 grant · 30 days · Stellar Testnet

---

## Deliverable 1: Soroban Registry + Escrow Contracts

**Timeline:** Week 1

### Scope

- Skill Registry contract: register skills, store verdicts, query
- USDC Escrow contract: audit bonding, settlement, slashing
- Unit tests with >90% branch coverage
- Deployment to Stellar Testnet with funded accounts

### Success Criteria

- [ ] Public GitHub repository with CI passing
- [ ] Registry contract deployed to testnet (contract ID recorded)
- [ ] USDC escrow contract deployed to testnet
- [ ] All unit tests passing
- [ ] Transaction links documented on stellar.expert
- [ ] Integration test: register → audit → query end-to-end

### Evidence

- GitHub repo URL
- Contract IDs on testnet
- stellar.expert transaction hashes
- CI badge in README

---

## Deliverable 2: Audit Pipeline + Verification API

**Timeline:** Week 2

### Scope

- 3-stage audit pipeline (description scanner → sandbox → verdict synthesis)
- On-chain verdict submission via Soroban RPC
- Verification REST API (FastAPI)
- Seed 10+ real skills and audit them
- Include 1 poisoned / dangerous demo skill that must be caught

### Success Criteria

- [ ] 10+ real skills audited end-to-end
- [ ] Poisoned demo skill correctly flagged as `DANGEROUS`
- [ ] Audit verdicts posted on-chain (verifiable via RPC)
- [ ] REST API responding at `/check/{skill_id}` and `/skills`
- [ ] Audit reports with SHA-256 evidence hashes
- [ ] Pipeline runs in <5 minutes per skill

### Evidence

- On-chain records (queryable via API)
- Individual audit reports with evidence hashes
- Transaction hashes for each verdict submission
- API response screenshots

---

## Deliverable 3: Dashboard + x402 Demo

**Timeline:** Weeks 3–4

### Scope

- Next.js dashboard showing all registered skills, verdicts, and trust scores
- x402 pay-per-use flow: 402 → pay USDC → get license → 200
- Demo video walking through the full flow
- End-to-end integration tests

### Success Criteria

- [ ] Live x402 pay-per-use payment on Stellar Testnet
- [ ] Working verification API serving dashboard data
- [ ] Dashboard deployed and accessible on dev URL
- [ ] 3-minute demo video (screen recording with narration)
- [ ] Screenshots of full flow (register → audit → license → use)

### Evidence

- Live demo link (dashboard URL)
- Demo video (YouTube or Loom)
- Screenshots at each step
- Transaction hash of x402 payment

---

## Weekly Breakdown

| Week | Dates | Focus | Milestone |
|---|---|---|---|
| 1 | Aug 13–19 | Contracts: registry + escrow, unit tests, testnet deploy | D1 complete |
| 2 | Aug 20–26 | Pipeline: 3-stage audit, verdicts on-chain, seed 10+ skills | D2 complete |
| 3 | Aug 27–Sep 2 | API + Dashboard + x402 flow | Dashboard live |
| 4 | Sep 3–12 | Hardening, E2E testing, demo video | D3 complete |

---

## Budget

| Item | Amount |
|---|---|
| Primary builder (30 days) | $3,600 |
| Soroban expert review | $900 |
| Integration testing + demo | $500 |
| **Total** | **$5,000** |

---

## Out of Scope

These are explicitly **not** part of this 30-day delivery:

- **Multi-auditor marketplace** — single trusted auditor for the MVP
- **TEE-attested execution** — sandbox Docker is sufficient for the demo
- **Mainnet deployment** — testnet only
- **Token launch** — no STERISH token; payments in USDC via SAC
- **Skill execution runtime** — Sterish audits skills; it does not run them
- **Identity / KYC** — auditors are admin-designated, not a public marketplace
- **Mobile app** — web dashboard only

---

## Risk Mitigation

| Risk | Likelihood | Mitigation |
|---|---|---|
| Soroban contract bugs | Medium | Expert review (budgeted), comprehensive tests |
| LLM audit inconsistency | Medium | Structured prompts + deterministic scoring for stages 1 & 2 |
| Testnet congestion | Low | Use dedicated RPC endpoints, retry logic |
| Scope creep | Medium | Strict out-of-scope list, weekly scope reviews |
| USDC testnet availability | Low | Use SacSandbox USDC on Futurenet/testnet |