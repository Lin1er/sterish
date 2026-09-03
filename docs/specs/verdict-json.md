# Sterish — Frozen Verdict JSON (v1)

> **STATUS: FROZEN.** This is the single document that carries an audit result from the
> pipeline to the on-chain submitter, the verification API and the dashboard. Its machine
> form is `docs/specs/verdict.schema.json` (JSON Schema draft 2020-12); the schema is
> normative, this file explains it.

| | |
|---|---|
| Spec version (`spec_version`) | `1.0.0` |
| Schema | [`verdict.schema.json`](./verdict.schema.json) |
| Examples | [`examples/`](./examples/) — 3 valid, 8 rejected, 1 profile case |
| Proof | `python3 docs/specs/examples/validate_examples.py` (exit 0) |

---

## 1. What this document is for

One verdict JSON describes **one `(skill_id, version)` pair and the exact bytes it was
computed over**. It is the hand-off boundary between three programs that must not disagree:

```
pipeline (stages 1-3)  ──verdict.json──▶  on-chain submitter  ──▶  Registry.submit_verdict
                                    │
                                    └──▶  API /check responses ──▶  dashboard / installing agent
```

The reason it is frozen: `check(skill)` is the product's core claim. If the pipeline says
`DANGEROUS` and the thing that reaches the chain says something else — or is about a different
version, or about different bytes — the claim is false. The three identity fields exist
precisely to make that impossible to get wrong silently.

## 2. The shape

```jsonc
{
  "spec_version": "1.0.0",
  "skill_id": "com.evil.token-drainer",   // reverse-domain, byte-identical to Registry
  "version": "1.0.0",                     // semver, byte-identical to Registry
  "content_hash": "<64 hex lowercase>",   // canonical content hash v1 of the audited bytes
  "verdict": "DANGEROUS",                 // SAFE | DANGEROUS | WARNING | UNAUDITED
  "risk": "critical",                     // none | low | medium | high | critical
  "score": 5,                             // integer 0..=100
  "capabilities": ["WALLET_ACCESS", "SECRET_READ", "ENV_READ",
                   "NETWORK_OUTBOUND", "FILE_READ"],
  "findings": [
    { "stage": 1, "capability": "WALLET_ACCESS", "severity": "HIGH",
      "description": "...", "evidence": "tools[0].description" }
  ],
  "recommendation": "BLOCK",              // ALLOW | REVIEW | BLOCK
  "evidence_hash": "<64 hex lowercase>"
}
```

`additionalProperties` is `false` at both levels. Anything not listed here is rejected — a
verdict document is not an extension point, and a consumer must never have to guess whether an
unknown key changes the meaning of the audit.

### 2.1 Field reference

| Field | Type | Required | Notes |
|---|---|---|---|
| `spec_version` | string, `^1\.\d+\.\d+$` | yes | Version of **this schema**, not of the skill. |
| `skill_id` | string, reverse-domain | yes | Must be byte-identical to the `skill_id` registered on-chain — the on-chain value is `ScString`, so any difference means a different record. |
| `version` | string, semver | yes | Same: byte-identical to the on-chain `version`. |
| `content_hash` | 64 lowercase hex | yes | Canonical content hash v1 (`docs/specs/content-hash.md`) of the exact bytes audited. Must equal `VersionRecord.content_hash`. |
| `verdict` | enum (4) | yes | See the mapping table in §3. |
| `risk` | enum (5) | yes | Human-facing band. **Off-chain only** — the Registry has no `risk` field (see `interfaces.md` §6, D2). |
| `score` | integer `0..=100` | yes | Passed verbatim to `submit_verdict(score)`. `> 100` is rejected by the schema *and* by the contract (`InvalidTrustScore`, error 8). |
| `capabilities` | array, unique, enum (6) | yes | May be empty. Order is not significant. |
| `findings` | array of Finding | yes | May be empty (a clean `SAFE` audit). |
| `recommendation` | enum (3) | yes | Machine-actionable, not prose. See §5. |
| `evidence_hash` | 64 lowercase hex | yes | sha256 of the full off-chain report. Anchored on-chain as `VersionRecord.evidence_hash`, so a served report can be checked against the ledger. |

**Finding object**

| Field | Type | Required | Notes |
|---|---|---|---|
| `stage` | integer, `1 \| 2 \| 3` | yes | 1 = description scanner, 2 = declared-vs-actual static analysis, 3 = synthesis. |
| `capability` | Capability enum | **no** | Present when the finding is attributable to one declared capability. A stage-2 behavioural finding may map to none — `BehavioralFlag` in `models.py` carries a `syscall`, not a capability. |
| `severity` | `HIGH \| MEDIUM \| LOW` | yes | |
| `description` | non-empty string | yes | One human-readable sentence. |
| `evidence` | non-empty string | yes | Pointer into the audited artifact or trace, e.g. `tools[0].description`. **Required on purpose:** a finding nobody can check is an assertion, not evidence. |

Hex is lowercase-only so that plain string equality is a valid comparison in Python, TypeScript
and Rust without a normalization step that someone will eventually forget.

### 2.2 Enum sources (do not retype these by hand)

| Enum | Authoritative source |
|---|---|
| `capabilities[]`, `findings[].capability` | `Capability` in `pipeline/src/sterish_pipeline/models.py` — `FILE_READ`, `FILE_WRITE`, `NETWORK_OUTBOUND`, `WALLET_ACCESS`, `ENV_READ`, `SECRET_READ` |
| `findings[].severity` | `Severity` in the same file — `HIGH`, `MEDIUM`, `LOW` |
| `verdict` | `AuditVerdict` in `contracts/registry/src/data.rs` |
| `risk`, `recommendation`, `findings[].stage` | Defined here; no other source exists. |

---

## 3. Verdict mapping: JSON ⇄ contract

`AuditVerdict` unit variants encode as `ScVec[ScSymbol("<Variant>")]` (see `interfaces.md`
§2.5), so the mapping is a string rename, not a number.

| JSON `verdict` | Contract `AuditVerdict` | Variant index | XDR | May be submitted? | Mints VERIFIED? |
|---|---|---|---|---|---|
| `"SAFE"` | `AuditVerdict::Safe` | 1 | `ScVec[ScSymbol("Safe")]` | yes | **yes — the only one** |
| `"DANGEROUS"` | `AuditVerdict::Dangerous` | 2 | `ScVec[ScSymbol("Dangerous")]` | yes | no |
| `"WARNING"` | `AuditVerdict::Warning` | 3 | `ScVec[ScSymbol("Warning")]` | yes | no |
| `"UNAUDITED"` | `AuditVerdict::Unaudited` | 0 | `ScVec[ScSymbol("Unaudited")]` | **no — rejected with `InvalidVerdict` (error 9)** | no |

Reverse direction (chain → JSON) is the same table read right-to-left. A `VersionRecord` read
back with `Unaudited` renders as `"UNAUDITED"`, which is exactly the state of a version that
has been registered but never audited.

---

## 4. Frozen invariants

These are the FINAL decisions recorded in `CLAUDE.md`, stated here in the form a reviewer can
check.

| # | Invariant | Enforced where |
|---|---|---|
| V1 | **The poisoned fixture MUST come out `DANGEROUS`.** A pipeline run over `pipeline/tests/poisoned_skill/` that produces anything else is a failing build, not a judgement call. | pipeline tests (STE-13); example `examples/valid-poisoned-dangerous.json` pins the expected document |
| V2 | **Only `SAFE` may mint a VERIFIED token.** Nothing else — not `WARNING`, not a high `score`. | `SkillRegistry::is_verified` (`verdict == Safe`); mint path gated on it |
| V3 | **`UNAUDITED` must never be sent to `submit_verdict`.** It exists only as the initial state written by `register_skill`. | Schema profile `$defs/SubmittableVerdict`; contract `InvalidVerdict` (9). Proven by `examples/submittable-invalid-unaudited.json`, which is *valid* as a document and *rejected* as a submission. |
| V4 | **`score` is never clamped.** A score above 100 is a bug in the producer and must surface as a rejection, not as a quietly corrected 100. | Schema `maximum: 100`; contract `InvalidTrustScore` (8) |
| V5 | **`content_hash` binds the verdict to bytes.** The verdict is meaningless without it: a one-byte change produces a different hash, which the Registry resolves to nothing. | `content-hash.md`; `lookup_by_hash` returning `None` on a miss |
| V6 | **`(skill_id, version)` identifies the record.** A verdict never applies to "the skill"; it applies to one version of it. | `interfaces.md` R4 |
| V7 | **Every finding carries `evidence`.** | Schema `required: [..., "evidence"]` |

### 4.1 What the schema can and cannot enforce

The schema enforces V3 (via the `SubmittableVerdict` profile), V4 and V7 mechanically.

V1, V2, V5 and V6 are **cross-system** invariants — they involve the pipeline corpus, the
contract and the bytes on disk, so no JSON Schema can check them. They are enforced by the
pipeline tests, the contract tests, and the cross-language content-hash runner respectively.
This file states them so that a reviewer knows which tests are load-bearing.

Relations the schema deliberately does **not** enforce, because a rigid coupling would force
producers to lie rather than report honestly:

- `verdict` ⇄ `recommendation` (e.g. `DANGEROUS` ⇒ `BLOCK`)
- `verdict` ⇄ `risk` or `score` thresholds
- `capabilities` ⊇ the set of `findings[].capability`

These are conventions (§5), checked by the pipeline's own tests, not by the schema.

---

## 5. `risk`, `recommendation` and `score` — how they relate

`score` is the machine number that goes on-chain. `risk` and `recommendation` are the
human/agent-facing summary and stay off-chain.

Conventional mapping used by the pipeline (a convention, not a schema rule):

| `verdict` | typical `risk` | `recommendation` | Meaning for an installing agent |
|---|---|---|---|
| `SAFE` | `none` / `low` | `ALLOW` | Install. Eligible for a VERIFIED badge. |
| `WARNING` | `medium` / `high` | `REVIEW` | A human must look before this runs with real credentials. |
| `DANGEROUS` | `high` / `critical` | `BLOCK` | Do not install. No badge, and the DANGEROUS verdict is published on-chain anyway so the finding is public. |
| `UNAUDITED` | `none` | `REVIEW` | Not audited at all. Absence of evidence, not evidence of safety — never render this as "safe". |

> `recommendation` is an **enum**, not prose. Note that
> `pipeline/.../stage3_verdict_synthesis.py` currently builds `recommendation` as a free-text
> sentence; that string belongs in the off-chain report, not in this field. See §7.

---

## 6. On-chain vs off-chain split

| Verdict JSON field | Lands on-chain? | Where |
|---|---|---|
| `skill_id` | yes | `submit_verdict(skill_id, ...)`, event topic |
| `version` | yes | `submit_verdict(..., version, ...)`, event topic |
| `content_hash` | yes | written by `register_skill`; echoed in the `version_recorded` event |
| `verdict` | yes | `VersionRecord.verdict` |
| `score` | yes | `VersionRecord.trust_score` |
| `evidence_hash` | yes | `VersionRecord.evidence_hash` |
| `risk` | **no** | off-chain only |
| `capabilities` | **no** | off-chain only |
| `findings` | **no** | off-chain only; anchored by `evidence_hash` |
| `recommendation` | **no** | off-chain only |
| `spec_version` | **no** | off-chain only |

Rationale: ledger space is expensive and permanent, and a list of findings is the part most
likely to be revised. Hashing it and publishing only the anchor gives the same tamper-evidence
at a fraction of the cost. A consumer that wants the findings fetches the report from the API
and checks `sha256(report) == evidence_hash` from the chain.

The submitter call is therefore exactly:

```
submit_verdict(
  skill_id      = json.skill_id,
  version       = json.version,
  verdict       = map(json.verdict),        # §3, as ScVec[ScSymbol]
  score         = json.score,               # u32
  evidence_hash = bytes.fromhex(json.evidence_hash),  # BytesN<32>
)
```

---

## 7. Known gaps between this schema and the current pipeline code

The schema is the target. `pipeline/src/sterish_pipeline/models.py` does **not** produce this
document yet. Recorded here so the gap is a tracked task and not a surprise:

| # | Gap | Detail |
|---|---|---|
| P1 | `AuditReport` has no `version`, no `content_hash` | It carries `skill_id` only, so a report cannot be tied to a version or to bytes. These are the three identity fields added by this spec. |
| P2 | `AuditReport.final_verdict` is named differently and has 3 variants | `FinalVerdict` = `SAFE \| DANGEROUS \| WARNING`. No `UNAUDITED` — which is correct, since the pipeline can never legitimately emit it. The schema still lists it because the field also renders chain state. |
| P3 | No `risk` field | Must be derived at report-assembly time. |
| P4 | No flat `capabilities` list | Currently only per-tool, inside `SkillManifest.tools[].capabilities`. The union has to be computed. |
| P5 | No `findings` list | `Stage1Result.risk_flags` (`RiskFlag`: capability, severity, description) and `Stage2Result.behavioral_flags` (`BehavioralFlag`: syscall, expected, severity, description) must be flattened into `findings[]` with a `stage` and an `evidence` pointer. Neither current type carries an `evidence` field — **that is the main piece of new work**. |
| P6 | `recommendation` is free text | `_build_recommendation` returns a sentence; the schema wants `ALLOW \| REVIEW \| BLOCK`. Keep the sentence in the off-chain report. |
| P7 | `trust_score` vs `score` | Rename at the boundary. |
| P8 | `evidence_hash` is computed over a summary string | `sha256(f"{skill_id}|{verdict}|{trust}|{s1}|{s2}")`, not over the full report. That is weak — it anchors five numbers, not the findings. Should become the hash of the serialized report. |

Closing P1–P8 belongs to the pipeline/indexer ticket (STE-13), not to this freeze.

---

## 8. Examples and how to prove them

```bash
python3 docs/specs/examples/validate_examples.py     # exit 0 == every expectation held
```

The runner uses the `jsonschema` library when it is installed and falls back to a built-in
checker covering exactly the keywords this schema uses, so it runs on a bare `python3` with no
network. Both paths were exercised and agree.

| File | Expectation | Why |
|---|---|---|
| `valid-safe.json` | accepted | Baseline `SAFE` document; the mint-eligible case. |
| `valid-poisoned-dangerous.json` | accepted | The `com.evil.token-drainer` fixture. `content_hash` is the canonical hash v1 of the real `pipeline/tests/poisoned_skill/manifest.json`, so the spec is bound to the corpus rather than to an invented string. Includes a stage-2 finding with **no** `capability`, exercising the optional field. |
| `valid-warning-no-findings-edge.json` | accepted | Edge case: `findings: []` is legal. |
| `invalid-verdict-enum.json` | rejected | `"MALICIOUS"` is not an `AuditVerdict`. |
| `invalid-score-101.json` | rejected | `score: 101` — mirrors `InvalidTrustScore`. |
| `invalid-content-hash-not-64-hex.json` | rejected | 63 chars and uppercase. |
| `invalid-missing-content-hash.json` | rejected | Proves the added identity field is genuinely required. |
| `invalid-unknown-capability.json` | rejected | `"GPU_ACCESS"` is not in `models.Capability`. |
| `invalid-finding-missing-evidence.json` | rejected | Untraceable finding (V7). |
| `invalid-extra-property.json` | rejected | `report_uri` — `additionalProperties: false`. |
| `invalid-stage-4.json` | rejected | There is no stage 4. |
| `submittable-invalid-unaudited.json` | **accepted** by the base schema, **rejected** by `$defs/SubmittableVerdict` | Proves V3: the document is legal, the submission is not. |

Result at freeze time: **12/12 expectations held, exit 0**, identically under `jsonschema`
4.26 and the built-in fallback.

---

## 9. Changelog / deviations from the original ticket wording

| Change | Reason |
|---|---|
| **Added `skill_id`, `version`, `content_hash`** to the ticket's field list | Without them the hand-off to the on-chain submitter cannot know which record to write. `content_hash` is what makes the verdict about *bytes* rather than about a name. (PM decision, recorded in the STE-10 spec.) |
| **Added `spec_version`** | So a consumer can reject a v2 document instead of silently misreading it. |
| `findings[].capability` is **optional** | A stage-2 behavioural finding maps to a `syscall`, not to a declared capability; requiring it would force producers to invent an attribution. Every example that has one still carries it. |
| `findings[].evidence` is **required** | The project's whole claim is checkable evidence. An unsourced finding is the one thing this schema should not allow. **Flagged for Axel** in case a looser rule is wanted for stage-3 synthesis findings. |
| `UNAUDITED` kept in the base enum, restricted via a profile | The value is needed when rendering chain state (a registered-but-unaudited version), but must be impossible to submit. One enum with two profiles beats two near-identical schemas. |

## 10. Change process

Same gate as `docs/specs/interfaces.md` §7. Additionally: any change to a field's type or to an
enum requires bumping `spec_version` and adding a row to the table in §9, and every example in
`examples/` must be re-run to exit 0 in the same commit.
