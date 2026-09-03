# On-chain verdict submission

How an audit result lands on-chain, and how to verify it. Implemented in
`pipeline/src/sterish_pipeline/onchain.py` and `report.py`.

## The flow

Per skill, the orchestrator runs:

```
query_skill(skill_id)                         # idempotency check
  └─ not found ─▶ register_skill(skill_id, version, content_hash)
submit_verdict(skill_id, version, verdict, score, evidence_hash)
  ├─ SAFE      ─▶ escrow.settle(request_id)    # auditor paid fee + bond
  └─ DANGEROUS ─▶ (no mint) [optional] escrow.slash(request_id)
```

`register_skill` is skipped when the skill is already recorded, so a re-run
after a mid-flight RPC failure resumes rather than duplicating work.

## Argument encoding — the corrected bug

The registry's `submit_verdict` takes an `AuditVerdict`, a Soroban unit-variant
enum. The scaffold encoded the verdict as `scval.to_uint32(2)`, which the host
rejects as a type mismatch. The correct encoding is the enum variant:

| Verdict | XDR (base64) |
|---|---|
| `to_uint32(2)` (wrong) | `AAAAAwAAAAI=` |
| `AuditVerdict::Safe` (right) | `AAAAEAAAAAEAAAABAAAADwAAAARTYWZl` |

`encode_verdict()` produces the enum form; `tests/test_onchain.py` pins the
exact bytes so the bug can't return.

Full argument types, matching `contracts/registry/src/data.rs`:

| Function | Args (frozen ABI, docs/specs/interfaces.md) |
|---|---|
| `register_skill` | `Address owner`, `String skill_id`, `String version`, `BytesN<32> content_hash` |
| `submit_verdict` | `String skill_id`, `String version`, `AuditVerdict verdict`, `u32 score`, `BytesN<32> evidence_hash` |
| `query_skill` | `String skill_id` → `Result<SkillEntry, RegistryError>` |
| `settle` / `slash` | `u32 request_id` |

`owner` signs `register_skill` (`owner.require_auth()`); the orchestrator
defaults it to the auditor's own account. `submit_verdict` now keys on
`(skill_id, version)`.

## Evidence hash

`evidence_hash` on-chain is the SHA-256 of the **published report bytes**, not of
an internal string. `report.py` writes the report and takes the hash over
exactly those bytes, so anyone can fetch the report at `report_uri` and confirm:

```bash
curl -s <report_uri> | sha256sum        # == evidence_hash on-chain
```

`verify_published_report()` performs the same check in code.

## Running it against testnet

Blocked until the contracts are deployed (STERISH-9 / STE-13). Once a contract
ID exists:

```bash
# pipeline/.env
REGISTRY_CONTRACT_ID=C...          # from `make deploy-testnet`
ESCROW_CONTRACT_ID=C...
STERISH_AUDITOR_SECRET=S...        # the auditor authorized on the registry
```

```bash
# Audit one skill and push the verdict on-chain:
uv run python -m sterish_pipeline.cli audit \
  --skill-id com.example.demo \
  --manifest path/to/manifest.json \
  --submit --secret-key "$STERISH_AUDITOR_SECRET"
```

The command prints the report URI and the register/verdict/settle transaction
hashes; each opens on `stellar.expert/testnet`.

## Test coverage

- `tests/test_onchain.py` — ABI encoding pinned to exact XDR; full orchestrator
  flow (register → verdict → settle/slash, idempotency, retry) against a fake
  `ChainClient`; no network.
- `tests/test_report.py` — evidence-hash reproducibility and tamper detection.
- `TestLiveTestnet` — real testnet round-trip, **skipped** until
  `STERISH_REGISTRY_CONTRACT_ID` is set. This is the step that produces the
  clickable stellar.expert links the ticket's done-criteria call for.
