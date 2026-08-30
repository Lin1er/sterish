# Sterish — Technical Architecture

> On-chain skill registry, multi-stage LLM audit, x402 pay-per-use licensing,
> and trust scoring for AI agents on Stellar.

---

## Table of Contents

1. [Soroban Registry Contract](#1-soroban-registry-contract)
2. [USDC Escrow Contract](#2-usdc-escrow-contract)
3. [Audit Pipeline](#3-audit-pipeline-3-stages)
4. [x402 Pay-Per-Use Licensing](#4-x402-pay-per-use-licensing)
5. [Trust Score](#5-trust-score)
6. [Verification REST API](#6-verification-rest-api)
7. [Tech Stack](#tech-stack)
8. [Open Questions](#open-questions)

---

## 1. Soroban Registry Contract

The registry contract is the single source of truth for all skill metadata,
audit verdicts, and trust scores. It is deployed once on Stellar Testnet and
referenced by the escrow contract and API.

### Data Model

```rust
/// Semantic version of a registered skill.
struct SkillVersion {
    major: u32,
    minor: u32,
    patch: u32,
}

/// Outcome of an audit — stored immutably on-chain.
enum AuditVerdict {
    Unaudited,   // Default state before any audit runs
    Safe,        // Passed all audit stages
    Dangerous,   // Caught malicious or exfiltrating behavior
    Warning,     // Suspicious but not definitively malicious
}

/// Complete on-chain record for a skill.
struct SkillEntry {
    skill_id: String,           // Unique identifier (e.g. "web-search-tool")
    owner: Address,             // Developer's Stellar address
    manifest_uri: String,       // IPFS/HTTP URI to skill manifest
    version: SkillVersion,      // Semantic version
    verdict: AuditVerdict,      // Latest audit result
    trust_score: u32,           // 0-100 composite score
    evidence_hash: BytesN<32>,  // SHA-256 of audit evidence
    auditor: Address,           // Auditor who submitted the verdict
    audit_timestamp: u64,       // Ledger close time of last audit
}

/// Configurable weights for trust score calculation.
struct TrustScoreConfig {
    verdict_weight: u32,        // Weight of audit verdict
    capability_weight: u32,     // Weight of capability risk profile
    behavioral_weight: u32,     // Weight of sandbox behavior analysis
    decay_rate: u32,            // Time-decay rate (basis points per day)
}

/// Storage keys — all on-chain state is keyed through this enum.
enum DataKey {
    Skill(String),              // skill_id → SkillEntry
    SkillsList,                 // Vec<String> of all registered skill_ids
    Auditor(Address),           // auditor address → bool (authorized?)
    TrustConfig,                // Singleton TrustScoreConfig
}
```

### Contract Operations

| Function | Auth | Description |
|---|---|---|
| `register_skill(skill_id, manifest_uri, version)` | Owner | Register a new skill (verdict defaults to `Unaudited`) |
| `submit_verdict(skill_id, verdict, evidence_hash)` | Auditor | Record audit result; updates `verdict`, `trust_score`, `evidence_hash` |
| `query_skill(skill_id) → SkillEntry` | None | Read a single skill's full record |
| `query_all_skills() → Vec<SkillEntry>` | None | Return all registered skills |
| `set_auditor(address, authorized)` | Admin | Grant or revoke auditor privileges |

### Data Flow

```
  Developer                    Auditor                     Consumer
      │                          │                            │
      │  register_skill()        │                            │
      ▼                          │                            │
 ┌─────────┐                     │                            │
 │ Registry │──▶ Unaudited       │                            │
 │ Contract │                    │                            │
 └─────────┘                     │                            │
      │                          │                            │
      │       submit_verdict()   │                            │
      │◀─────────────────────────│                            │
      ▼                          ▼                            │
 ┌─────────┐              ┌───────────┐                       │
 │ Registry │──▶ Safe /   │  Evidence │                       │
 │ Contract │    Dangerous │  Hash     │                       │
 │          │    Warning   │  (SHA256) │                       │
 └─────────┘              └───────────┘                       │
      │                                                     │
      │              query_skill()                           │
      │◀─────────────────────────────────────────────────────│
      ▼
 SkillEntry { verdict, trust_score, evidence_hash, ... }
```

---

## 2. USDC Escrow Contract

The escrow contract ensures economic accountability in the audit process:
requestors fund audits, auditors post bonds, and misbehavior results in slashing.

### Audit Status Lifecycle

```rust
enum AuditStatus {
    Open,     // Request created, awaiting auditor bond
    Bonded,   // Auditor posted bond, audit in progress
    Settled,  // Audit completed honestly — bond returned + fee paid
    Slashed,  // Auditor acted maliciously — bond forfeited to requestor
}
```

### Contract Operations

| Function | Auth | Description |
|---|---|---|
| `create_audit_request(skill_id, fee)` | Requestor | Lock USDC fee in escrow; status → `Open` |
| `post_bond(request_id, bond_amount)` | Auditor | Lock USDC bond; status → `Bonded` |
| `settle(request_id, verdict)` | Anyone (after proof) | Release bond + fee to auditor; status → `Settled` |
| `slash(request_id, evidence)` | Anyone (with proof) | Forfeit auditor bond to requestor; status → `Slashed` |

### Escrow Flow

```
 Requestor                Escrow Contract              Auditor
    │                         │                          │
    │  create_audit_request   │                          │
    │  (locks USDC fee)       │                          │
    │────────────────────────▶│                          │
    │                         │  Status: Open            │
    │                         │                          │
    │                         │  post_bond               │
    │                         │  (locks USDC bond)       │
    │                         │◀─────────────────────────│
    │                         │  Status: Bonded          │
    │                         │                          │
    │                         │      ┌──────────┐        │
    │                         │      │  Audit    │        │
    │                         │      │  Runs     │        │
    │                         │      └─────┬────┘        │
    │                         │            │              │
    │                         │   ┌───────┴────────┐      │
    │                         │   │                │      │
    │                         │   ▼                ▼      │
    │                         │  Honest?        Malicious?│
    │                         │   │                │      │
    │                         │   ▼                ▼      │
    │  (fee goes to           │ settle          slash     │
    │   auditor, bond         │ (bond returned  (bond     │
    │   returned)             │  to auditor)    forfeited)│
    │◀────────────────────────│  Status:        Status:  │
    │                         │  Settled        Slashed   │
```

---

## 3. Audit Pipeline (3 Stages)

The pipeline is a Python-based system that runs sequentially through three
stages, each producing structured evidence that feeds into the next.

### Stage 1: Tool Description Scanner

Parses the skill manifest (YAML/JSON) and flags risk-related capabilities
by mapping them to a risk taxonomy.

**Risk Capability Map:**

| Capability | Risk Level | Rationale |
|---|---|---|
| `WALLET_ACCESS` | HIGH | Direct access to user funds |
| `SECRET_READ` | HIGH | Can read API keys, passwords, tokens |
| `NETWORK_OUTBOUND` | HIGH | Potential data exfiltration channel |
| `FILE_WRITE` | MEDIUM | Can modify local filesystem |
| `ENV_READ` | MEDIUM | Can read environment variables (may contain secrets) |

**Output:** Structured risk profile with capability → risk-level mappings,
flagged items, and a stage-1 risk summary score.

### Stage 2: Sandboxed Behavior Check

Runs the skill inside an isolated Docker container with strict resource limits
and monitoring:

- **Syscall monitoring:** Trace system calls (open, connect, write, exec)
- **Network monitoring:** Capture outbound connections (DNS, TCP, UDP)
- **Filesystem monitoring:** Watch for reads outside allowed dirs, writes anywhere
- **Exfiltration detection:** Flag large outbound data transfers, encoded payloads

**Container constraints:**
- No host network access (bridge mode with explicit outbound rules)
- Read-only root filesystem
- No privileged capabilities
- CPU/memory limits enforced

**Output:** Behavioral report with observed syscalls, network attempts,
file accesses, and any flagged exfiltration events.

### Stage 3: Verdict Synthesis

Combines outputs from stages 1 and 2 through an LLM-assisted analysis:

1. Merge stage-1 risk profile with stage-2 behavioral report
2. Cross-reference declared capabilities with observed behaviors
3. Detect mismatches (e.g., declares no `NETWORK_OUTBOUND` but makes HTTP calls)
4. Calculate weighted trust score using `TrustScoreConfig` from registry
5. Generate SHA-256 evidence hash over all stage outputs
6. Produce final `AuditVerdict` and trust score

**Output:** Complete verdict record — `AuditVerdict`, trust score (0–100),
evidence hash, and human-readable summary.

### Pipeline Flow

```
           Skill Manifest
                │
                ▼
  ┌──────────────────────────┐
  │  Stage 1: Description    │
  │  Scanner                 │
  │                          │
  │  • Parse manifest        │
  │  • Map capabilities      │
  │  • Flag risk levels      │
  │                          │
  │  Output: RiskProfile     │
  └───────────┬──────────────┘
              │
              ▼
  ┌──────────────────────────┐
  │  Stage 2: Sandboxed      │
  │  Behavior Check          │
  │                          │
  │  • Docker isolation      │
  │  • Syscall monitoring    │
  │  • Network monitoring    │
  │  • Exfiltration detect   │
  │                          │
  │  Output: BehaviorReport  │
  └───────────┬──────────────┘
              │
              ▼
  ┌──────────────────────────┐
  │  Stage 3: Verdict        │
  │  Synthesis               │
  │                          │
  │  • Merge stage 1 + 2    │
  │  • Cross-reference       │
  │  • LLM analysis          │
  │  • Trust score calc      │
  │  • Evidence hash         │
  │                          │
  │  Output: AuditVerdict    │
  │          + trust_score   │
  │          + evidence_hash │
  └───────────┬──────────────┘
              │
              ▼
      submit_verdict()
      (on-chain)
```

---

## 4. x402 Pay-Per-Use Licensing

Sterish uses the [x402 protocol](https://x402.dev) for HTTP 402 pay-per-use
access to audited skills. Consumers who lack a valid license token receive a
`402 Payment Required` response with a payment header; after paying USDC
on Stellar, they receive a license token and retry the request.

### Flow

```
 Agent                API Server              Stellar (USDC/SAC)
  │                      │                          │
  │  GET /invoke/skill   │                          │
  │  (no license token)  │                          │
  │─────────────────────▶│                          │
  │                      │                          │
  │  402 Payment         │                          │
  │  Required            │                          │
  │  + payment-required  │                          │
  │    header            │                          │
  │◀─────────────────────│                          │
  │                      │                          │
  │  Pay USDC            │                          │
  │────────────────────────────────────────────────▶│
  │                      │                          │
  │  USDC transfer       │                          │
  │  confirmed           │                          │
  │◀────────────────────────────────────────────────│
  │                      │                          │
  │  Mint license token  │                          │
  │  (on-chain or JWT)   │                          │
  │                      │                          │
  │  GET /invoke/skill   │                          │
  │  + license token     │                          │
  │─────────────────────▶│                          │
  │                      │                          │
  │  200 OK + skill      │                          │
  │  response            │                          │
  │◀─────────────────────│                          │
```

### Key Details

- **Payment asset:** USDC via Stellar Asset Contract (SAC) on testnet
- **License format:** Short-lived JWT or on-chain NFT (configurable)
- **Retry:** Client retries the original request with `Authorization: Bearer <token>`
- **Price:** Set per-skill by the developer at registration time

---

## 5. Trust Score

The trust score is a composite metric (0–100) that gives consumers a single
number to evaluate skill safety.

### Components

| Component | Source | Description |
|---|---|---|
| Audit verdict | Stage 3 | Base score from verdict (Safe=80, Warning=50, Dangerous=0, Unaudited=20) |
| Capability risk | Stage 1 | Deductions for HIGH/MEDIUM risk capabilities |
| Behavioral analysis | Stage 2 | Bonuses for clean sandbox run; deductions for flagged events |
| Time decay | Clock | Score decays over time if not re-audited |

### Formula

```
trust_score = base_score
            - risk_deductions       # sum of capability risk penalties
            + behavioral_bonuses    # bonus for clean runs, penalty for flags
            - time_decay            # (days_since_audit × decay_rate) / 10000

# Clamped to [0, 100]
trust_score = max(0, min(100, trust_score))
```

**Example:**

```
base_score      = 80  (Safe verdict)
risk_deductions = 15  (NETWORK_OUTBOUND=HIGH + ENV_READ=MEDIUM)
behavioral      = +10 (clean sandbox, no exfiltration)
time_decay      = 2   (20 days since audit, decay_rate=1000)

trust_score = 80 - 15 + 10 - 2 = 73
```

### Configurable Weights

Weights are stored on-chain in `TrustScoreConfig` and can be updated by
the contract admin:

| Parameter | Default | Description |
|---|---|---|
| `verdict_weight` | 50 | How much the verdict drives the base score |
| `capability_weight` | 30 | Impact of declared capabilities |
| `behavioral_weight` | 20 | Impact of sandbox observations |
| `decay_rate` | 1000 | Basis points per day of score decay |

---

## 6. Verification REST API

A FastAPI service that reads from the on-chain registry and exposes audit
status to consumers and the dashboard.

Full specification: [`api-spec.md`](api-spec.md)

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/check/{skill_id}` | Query audit status of a single skill |
| `GET` | `/skills?start=0&limit=20` | List registered skills with pagination |
| `GET` | `/health` | Health check |

### Response Schemas

**`GET /check/{skill_id}` → 200**

```json
{
  "skill_id": "web-search-tool",
  "verdict": "SAFE",
  "trust_score": 92,
  "evidence": "https://stellar.expert/testnet/tx/abc123",
  "audit_timestamp": "2026-08-20T14:30:00Z",
  "auditor": "GCBYXEE..."
}
```

**`GET /skills` → 200**

```json
[
  {
    "skill_id": "web-search-tool",
    "verdict": "SAFE",
    "trust_score": 92,
    "versions": ["1.0.0"]
  }
]
```

**`GET /health` → 200**

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Smart Contracts | Soroban (Rust) |
| Audit Pipeline | Python 3.12+ |
| API | FastAPI |
| Dashboard | Next.js 14 + TypeScript |
| Payments | x402 + USDC (Stellar Asset Contract) |
| Blockchain | Stellar Testnet |
| LLM | Claude / GPT (audit stages 1 & 3) |
| Sandbox | Docker |

---

## Open Questions

1. **Trust score formula weights** — Current defaults are guesses; need
   empirical calibration from real audit data.

2. **False positive / negative rate targets** — What acceptable error rates
   should the pipeline target? Affects sandbox strictness and LLM prompts.

3. **License token transferability** — Should x402 license tokens be
   transferable between agents, or bound to the paying identity?

4. **Auditor rotation / multi-auditor** — Current design has a single auditor;
   should we require N-of-M auditor consensus for a verdict?

5. **Re-audit trigger on version update** — When a developer updates a skill
   version, should it automatically reset the verdict to `Unaudited` and
   trigger a re-audit, or carry forward the previous verdict with a warning?
