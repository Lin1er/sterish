# Sterish — Deployments

Deployment evidence, per point 8 of the working agreement. Every address below is **live on
Stellar testnet** and clickable. No secrets in this document — only public addresses (`G…`) and
contract addresses (`C…`); keys live in a git-ignored `.env` (see `CLAUDE.md`).

---

## Current addresses (start here)

| Contract | Address | Upgradeable | Since |
|---|---|---|---|
| **Registry** | [`CCZJN366SV57JEBZVXGYY3ZBLJNFV4IR5ILCAI3EMX2WDNQPEPQ4BRL2`](https://stellar.expert/explorer/testnet/contract/CCZJN366SV57JEBZVXGYY3ZBLJNFV4IR5ILCAI3EMX2WDNQPEPQ4BRL2) | yes, 300s timelock | 2026-09-15 (STE-44) |
| **Tokens** | [`CB6VK4EXEN7V6MXLOFUI2ECMLSDUXAUV5EZICWBICKJDL3WPPU3CTP3T`](https://stellar.expert/explorer/testnet/contract/CB6VK4EXEN7V6MXLOFUI2ECMLSDUXAUV5EZICWBICKJDL3WPPU3CTP3T) | yes, 300s timelock | 2026-09-15 (STE-44) |
| **Escrow** | [`CCVCNFXK4YHY3ECPWCXLAMEXT4MI457ZREAZBR57CEJ3GQXONW7HVVDE`](https://stellar.expert/explorer/testnet/contract/CCVCNFXK4YHY3ECPWCXLAMEXT4MI457ZREAZBR57CEJ3GQXONW7HVVDE) | **no, by design** | 2026-09-03 (STE-13), **never replaced** |

The Registry and Tokens addresses from STE-13 are **superseded, not deleted**: they are still on
chain, still readable, and every transaction recorded against them below remains valid history.
They are simply not what the API, the pipeline or the dashboard point at any more. The Escrow
address has not changed and is the same contract it always was — see
[STE-44](#redeploy-2026-09-15--ste-44-upgradeable-v2) for why it was deliberately left alone.

---

## Public URLs (checked 24 September 2026)

| What | URL | Served by | Notes |
|---|---|---|---|
| **API** | **https://api.sterish.xyz** | VPS `187.53.142.100` via Cloudflare Tunnel (STE-54) | Canonical. `REPORT_BASE_URL`, the x402 `resource.url` and the STE-48 `challenge_url` all use it |
| API (alias) | https://api-sterish.jameshub.fun | same stack, same tunnel | Kept so anything already pointing at it keeps working |
| **Dashboard** | **https://app.sterish.xyz** | Vercel | Public since 24 September; renders live registry data and calls the API at `api.sterish.xyz` |
| Landing | https://sterish.xyz | — | Reserved for the landing page (STE-23); currently 404 |

The API allows any origin (`api-spec.md` §6): everything it serves is public ledger data, so the
dashboard moving hostnames needs no change on the API side.

---

## Testnet — 2026-09-03 (STE-13)

> **Superseded for Registry and Tokens** by the STE-44 redeploy below. Escrow is unchanged.
> Everything in this section is still true of the addresses it names; they are just no longer
> the ones in use.

| | |
|---|---|
| Network | Stellar **testnet** (`Test SDF Network ; September 2015`), protocol 28 |
| RPC | `https://soroban-testnet.stellar.org` |
| Deploy script | [`scripts/deploy-testnet.sh`](../scripts/deploy-testnet.sh) — deterministic, repeatable |
| WASM | final STE-12 build, hashes verified before deploying ([`contracts/wasm-hashes.txt`](../contracts/wasm-hashes.txt)) |

### Contract addresses

| Contract | Contract address | WASM sha256 | stellar.expert |
|---|---|---|---|
| **Registry** | `CAPDQW2XWTOCFQEP3AUCRRQHVJ5IOUZ45DWPNPVG7USNPE6RZQ3BUXND` | `8c438004591f65d84f8087738c4ff327bc016b38e443b2661bb36f6cd3852489` | [open](https://stellar.expert/explorer/testnet/contract/CAPDQW2XWTOCFQEP3AUCRRQHVJ5IOUZ45DWPNPVG7USNPE6RZQ3BUXND) |
| **Escrow** | `CCVCNFXK4YHY3ECPWCXLAMEXT4MI457ZREAZBR57CEJ3GQXONW7HVVDE` | `cb241f74d20146b9d4895160e68d0c337f68317c3b6c1f272b0505cdb84d0ad0` | [open](https://stellar.expert/explorer/testnet/contract/CCVCNFXK4YHY3ECPWCXLAMEXT4MI457ZREAZBR57CEJ3GQXONW7HVVDE) |
| **Tokens** (VERIFIED + license, soulbound) | `CCHVZRLOFGZ5IAYQUSHIPQOTVFABOX6SK5MHNZZUKAOT333KZNVW4EJX` | `318f44583ae3144a65c3992b163f91795b8f28a95d4bc59b4c2147ad00b83206` | [open](https://stellar.expert/explorer/testnet/contract/CCHVZRLOFGZ5IAYQUSHIPQOTVFABOX6SK5MHNZZUKAOT333KZNVW4EJX) |

The WASM sha256 **is** the Soroban wasm hash (`stellar contract upload` stores a contract under
`sha256(file)`), so the values above pin exactly the bytes that were deployed.

### What a third party can verify, and what they must pin (STE-12)

These three hashes are reproducible from source, and CI reproduces them on every run — but
**only on `aarch64-apple-darwin`**, which is the host that built them. That is not a caveat about
this repo; it is how Rust works. Rust promises byte-identical output across builds on the same
host, not across host platforms.

Measured in STE-12 on four independent machines, with the commit, `rustc 1.93.0`, `Cargo.lock`,
the release profile and the `$CARGO_HOME` path remapping all held equal:

| Host triple | `sterish_registry` | `sterish_escrow` | `sterish_tokens` | |
|---|---|---|---|---|
| `aarch64-apple-darwin` | `8c438004…` | `cb241f74…` | `318f4458…` | **was live on testnet** |
| `x86_64-unknown-linux-gnu` | `48305dba…` | `611f6eae…` | `f13c9ee6…` | |
| `aarch64-unknown-linux-gnu` | `dde6631a…` | `f3294593…` | `401571b9…` | |

> These are the **v1** hashes. The Registry and Tokens rows were replaced by STE-44; the escrow
> rows were not, on any host. The current manifest is
> [`contracts/wasm-hashes.txt`](../contracts/wasm-hashes.txt).

Byte-identical within a host triple, different across them. All three files keep identical
**sizes** on every host; what moves is the order the linker lays out the read-only data symbols,
which shifts the pointer constants in the code section. All three builds are equally valid
compilations of the same source — only the darwin one is the one that was uploaded.

**To verify the deployed contracts yourself**, on an Apple-silicon Mac:

```bash
git checkout <this commit>
bash scripts/build-wasm.sh --check     # rebuilds and compares against contracts/wasm-hashes.txt
```

**From any machine**, without building at all, compare against the chain directly — this is the
strongest check and needs no toolchain:

```bash
stellar contract fetch --id CAPDQW2XWTOCFQEP3AUCRRQHVJ5IOUZ45DWPNPVG7USNPE6RZQ3BUXND \
  --network testnet --out-file registry.wasm
sha256sum registry.wasm   # 8c438004591f65d84f8087738c4ff327bc016b38e443b2661bb36f6cd3852489
```

**On Linux**, `bash scripts/build-wasm.sh --check` verifies your own host's row in
`contracts/wasm-hashes.txt` — real drift detection for source, `Cargo.lock`, profile or
toolchain changes, but it cannot reproduce the deployed bytes. The script says so explicitly
rather than failing with an unexplained hash mismatch.

The `Contracts` workflow runs `--check` on **both** `macos-15` and `ubuntu-latest`, so the claim
above is re-proved on every pull request rather than asserted once.

One more thing worth pinning: these bytes came from a bare
`cargo build --target wasm32v1-none --release`, **not** from `stellar contract build`, which runs
the wasm optimizer by default and would produce different bytes.

### Payment asset

| | |
|---|---|
| USDC SAC on testnet (used by Escrow) | `CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA` · [open](https://stellar.expert/explorer/testnet/contract/CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA) |
| USDC classic issuer (for the trustline) | `GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5` (`home_domain: centre.io`) |

Both were verified through MCP Stellar Raven (the `USDC_TESTNET_ADDRESS` constant from
`@x402/stellar`) **and** read directly from chain. Do not confuse them: the SAC is the `C…` the
contract invokes `transfer` on; the classic issuer is the `G…` used for `changeTrust`.

### Test accounts

| Role | Address | Notes |
|---|---|---|
| Deployer / admin | `GAGU7Z5RZZJZI2TINQD2E2WAA4JEYB5LRXBBQ23JN6OHV4YUJJCJJ3FB` | admin of all three contracts + minter role |
| Auditor | `GCFCURTZ7XHMTKZR7QN2MXRRAIWKGVOOVQV4KCP5EIQ62HGG4S3Y2XPL` | auditor role on Registry + Tokens, posts the bond |
| Developer | `GD73M4F7RN74KBLFGJP4WKBMCBJWBOA4SFNOP5HG4NBCDQUQCC2ARSZU` | skill owner + audit requestor |
| Reporter | `GADNHGAFXH3BE2PY2QYY5NAH3A6PWKQKK2YMF4HAF5BDOVHKI2GC5JFJ` | receives the bond on slash |

All funded with XLM through Friendbot. The auditor is deliberately **separate** from the
developer because Escrow rejects `requestor == auditor` (`EscrowError::SelfAudit = 9`).

The USDC trustline (`USDC:GBBD47IF…`) is established on all four:

| Akun | tx |
|---|---|
| deployer | [`3a86fe976cf972e6…`](https://stellar.expert/explorer/testnet/tx/3a86fe976cf972e6a7c42c5d5b6700856fa7c85b6a30702039ac278e9ddddefa) |
| auditor | [`c96324050f717d0f…`](https://stellar.expert/explorer/testnet/tx/c96324050f717d0fc36c43568e6680301c7a6c01f2b5ea7edbcf2b66f9650b41) |
| developer | [`4aaf24b61a20cbf0…`](https://stellar.expert/explorer/testnet/tx/4aaf24b61a20cbf0f525b3e47403a0be263a22647427e659a67b11610be5b009) |
| reporter | [`c147d3c4b7deb4b2…`](https://stellar.expert/explorer/testnet/tx/c147d3c4b7deb4b28ad12d722f90fe775ed7debdb39b91065abe074780fb30a2) |

---

## On-chain evidence — the audit path (Registry + Tokens)

Two skills were used. Both `content_hash` values were computed with the frozen reference
implementation [`docs/specs/reference/content_hash.py`](specs/reference/content_hash.py)
(STE-10), not invented.

| Skill | `content_hash` | Verdict |
|---|---|---|
| `com.sterish.weather-lookup` v1.0.0 | `4bf3f90c4047ca2b6c950e127296da95b2ace4f99c8d777eac921358811e42dd` | **Safe**, score 92 |
| `com.evil.token-drainer` v1.0.0 | `c2bd4a316415b4919e3f1f40d9925f4052d020cf3dc2ecabe0e7c9dd28cc87f0` | **Dangerous**, score 5 |

The poisoned hash is identical to the `poisoned-token-drainer` vector in
[`docs/specs/vectors/content-hash-vectors.json`](specs/vectors/content-hash-vectors.json) — the
spec, the corpus and the chain are all bound to the same number.

| Step | tx |
|---|---|
| `register_skill` (weather-lookup) | [`589a0c31c6d4b14d…`](https://stellar.expert/explorer/testnet/tx/589a0c31c6d4b14d3807e1373f80b99bc2679b749b3b9f0af6b63897cc32b7dc) |
| `submit_verdict` Safe 92 | [`499883165894078a…`](https://stellar.expert/explorer/testnet/tx/499883165894078ad8b5be199b4dcb079e8980a024fa93d42a62512b4a2da41b) |
| `mint_verified` → token #1 | [`d554c547f28677e6…`](https://stellar.expert/explorer/testnet/tx/d554c547f28677e60891444a1cc4a77189b9eb3f1cc2f3e4e2b63ed0a92909eb) |
| `register_skill` (token-drainer) | [`853a3d9b0d6c0971…`](https://stellar.expert/explorer/testnet/tx/853a3d9b0d6c097164ec3bcf56349bdd0083fba70fa65dd39afa5ac022675313) |
| `submit_verdict` Dangerous 5 | [`563b021bba4b4c44…`](https://stellar.expert/explorer/testnet/tx/563b021bba4b4c44a95d2cbe3b7057b6d71b7cb7fb2920b33fe02cf277c69a87) |
| `mint_verified` (token-drainer) | **refused on chain** — `Error(Contract, #4)` = `TokenError::NotSafeVerdict`. There is no successful tx, and that absence is the evidence. |

### Reads anyone can reproduce

```bash
R=CAPDQW2XWTOCFQEP3AUCRRQHVJ5IOUZ45DWPNPVG7USNPE6RZQ3BUXND
T=CCHVZRLOFGZ5IAYQUSHIPQOTVFABOX6SK5MHNZZUKAOT333KZNVW4EJX

stellar contract invoke --id $R --network testnet --send=no -- query_all_skills --start 0 --limit 10
stellar contract invoke --id $R --network testnet --send=no -- \
  lookup_by_hash --content_hash 4bf3f90c4047ca2b6c950e127296da95b2ace4f99c8d777eac921358811e42dd
stellar contract invoke --id $T --network testnet --send=no -- \
  is_verified_token --skill_id com.evil.token-drainer --version 1.0.0
```

Results verified at deploy time:

| Query | Result |
|---|---|
| `lookup_by_hash(4bf3f90c…)` | record for `com.sterish.weather-lookup` v1.0.0, verdict `Safe`, score 92 |
| `lookup_by_hash(<same hash, one bit flipped>)` | **`null`** — the skill reads as *unaudited*. This is the proposal's central claim, live. |
| `lookup_by_hash(c2bd4a31…)` | record for `com.evil.token-drainer`, verdict `Dangerous`, score 5 |
| `is_verified` safe / poisoned | `true` / `false` |
| `is_verified_token` safe / poisoned | `true` / `false` |
| `get_skill_count` · `total_supply` | `2` · `1` |

---

## On-chain evidence — the economic path (settle & slash)

⚠️ **Read this first.** The canonical Escrow above is wired to the **official USDC SAC**, and
testnet USDC is only obtainable from the [Circle faucet](https://faucet.circle.com/), which is
**web-only and Captcha-gated — it cannot be scripted**. So both economic paths were executed on
chain against a **second rehearsal escrow** wired to a test-asset SAC we control, so the
mechanics are proven live with real transactions. The contract code, the scripts and the actors
are **identical**; only the asset address differs.

| | |
|---|---|
| Rehearsal escrow | `CAZUICCUXUCDN2V6QPWY3TM7KLUE6U7PDAIGQYIH65QIQWJCZYU6WV3G` · [open](https://stellar.expert/explorer/testnet/contract/CAZUICCUXUCDN2V6QPWY3TM7KLUE6U7PDAIGQYIH65QIQWJCZYU6WV3G) |
| Rehearsal asset | `TUSDC` SAC `CDAYXDIDIINSVQVQRFCH7JSHTFZN4KIZKMNUZRVACHHFLTYGZEZV4OF2`, issuer `GAYCOQ5AMBT3FCIDU5DVIHEGN2QJND5HJOVXSRNT7OKRYETNU5V6MQGI` |
| Amounts | fee 5.0000000 · bond 10.0000000 |

✅ **The canonical path has since been run (STE-16, 2026-09-06).** Testnet USDC was topped up
through the Circle faucet and the whole flow executed against the canonical escrow with **real
USDC** — evidence in the "orchestrator pipeline (STE-16)" section below. What follows is kept as
a record of the situation at STE-13, and as the procedure to repeat if balances run out again.

**To repeat it:** fund `GD73M4F7RN74KBLF…` (developer) and `GCFCURTZ7XHMTKZR…` (auditor) with
USDC from the Circle faucet, then run one command:

```bash
ESCROW=CCVCNFXK4YHY3ECPWCXLAMEXT4MI457ZREAZBR57CEJ3GQXONW7HVVDE \
ASSET=CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA \
bash scripts/testnet-economic-flows.sh
```

That same script produced the table below, so the canonical path is a single command away.

### The SETTLE path — an honest auditor is paid

Balances (stroops): developer `1000000000 → 950000000` (−fee), auditor `1000000000 → 1050000000`
(+fee, bond returned), escrow `0 → 0`.

| Step | tx |
|---|---|
| `create_audit_request` #1 | [`67aa12227fe06062…`](https://stellar.expert/explorer/testnet/tx/67aa12227fe060625383b8dd0081aec20062cbfd41008c6f502a3d71e096d3e6) |
| `post_bond` #1 | [`353125251c2aae32…`](https://stellar.expert/explorer/testnet/tx/353125251c2aae3202868236284247302175e135b6ab9f9150891c1e5ece2d53) |
| **`settle` #1** | [`eae8eb123e7f5fc5…`](https://stellar.expert/explorer/testnet/tx/eae8eb123e7f5fc57beb0de90ff443c12dc1c09d09276b78c40d8b443816eeac) |

### The SLASH path — the bond moves to the reporter

Balances (stroops): reporter `0 → 100000000` (+bond), developer `950000000 → 950000000`
(fee fully refunded), auditor `1050000000 → 950000000` (−bond), escrow `0 → 0`.

| Step | tx |
|---|---|
| `create_audit_request` #2 | [`6535bd3debc9b8d0…`](https://stellar.expert/explorer/testnet/tx/6535bd3debc9b8d06d3ea9332374ca4221b9cb93ddc892b798d190f21cae4cbe) |
| `post_bond` #2 | [`56ab1c9072718d7f…`](https://stellar.expert/explorer/testnet/tx/56ab1c9072718d7f66a1223d458cd6a899c8056484a46127d2b67ff811f83556) |
| **`slash` #2 → reporter** | [`c8bfb19a248b7287…`](https://stellar.expert/explorer/testnet/tx/c8bfb19a248b728784e5782b24444b2a2a8b14ac59fcbab85b4d5566adba923c) |

The script `assert`s every balance delta rather than merely printing it, and all four assertions
pass on each path. The bond really does move to a third party who is neither the payer nor the
auditor.

---

## Handoff

| Consumer | What it needs |
|---|---|
| Pipeline / orchestrator (STE-16) | `REGISTRY_CA`, `TOKENS_CA`, the **auditor** secret (`AUDITOR_SECRET` in `.env`) |
| API (STE-17) | `REGISTRY_CA`, `TOKENS_CA` — read-only, no key needed |
| x402 seller (STE-19) | `TOKENS_CA` plus the **minter** secret (currently the deployer; rotate via `set_minter_role`) |
| Deploy env (STE-21/22) | the whole contract-address block above |

⚠️ **STE-16 has to fix `pipeline/src/sterish_pipeline/onchain.py` first.** That submitter calls
`submit_verdict` with 4 arguments, omitting `version`, and encodes the verdict as `u32`; the frozen
ABI takes 5 arguments with the verdict as an enum. Against the contract that is live now, that
submitter **cannot succeed**.

## On-chain evidence — the orchestrator pipeline (STE-16)

The full flow, run from `sterish_pipeline.orchestrator` against the canonical contracts above,
with **real testnet USDC** in the canonical escrow. The test skills use timestamped ids so that
`register_skill` genuinely executes rather than being skipped.

**Skill SAFE — `com.sterish.canon-safe-1788685783`** (score 90)
`evidence_hash` `c99ed231df7b42bf…`

| Step | tx |
|---|---|
| `register_skill` | [`ed6bf00bed0c72fb…`](https://stellar.expert/explorer/testnet/tx/ed6bf00bed0c72fbeee86dd3726b74a467b0f688fcffeb087625f6d5d1abbd96) |
| `submit_verdict` | [`a04fdefac6b41297…`](https://stellar.expert/explorer/testnet/tx/a04fdefac6b41297f53258c0d9ea06626070cde79db786588f4c93da36603c96) |
| `mint_verified` | [`7feb228ac6e49065…`](https://stellar.expert/explorer/testnet/tx/7feb228ac6e49065fcd24811d766812cf2355399dff44af1f26c23f834e137c0) |
| `create_audit_request` | [`d3e1650c9821e685…`](https://stellar.expert/explorer/testnet/tx/d3e1650c9821e685314e1b832cce8e989f8b10558c7ff7d41d65712d6f0ba8ee) |
| `post_bond` | [`16452fb9441a4aa3…`](https://stellar.expert/explorer/testnet/tx/16452fb9441a4aa3009a959fab881e511b76b256d349c77c1b3e60fab14f4c5f) |
| **`settle`** | [`55ba337ed2ab8d15…`](https://stellar.expert/explorer/testnet/tx/55ba337ed2ab8d15955737331ab44fbfe44bc63e8e3c1dd0398ea63f003b43db) |

**Skill DANGEROUS — `com.sterish.canon-poisoned-1788685812`** (score 10)
`evidence_hash` `a818b83de04c1190…`

| Step | tx |
|---|---|
| `register_skill` | [`b7840228becdecd5…`](https://stellar.expert/explorer/testnet/tx/b7840228becdecd5648f842d59519821aa8aeabb217e7247c3e0764c7d0361a9) |
| `submit_verdict` | [`58eb78df233aaa94…`](https://stellar.expert/explorer/testnet/tx/58eb78df233aaa947f24aba0632395aa57cd539380516d47da4bc1a7adad9432) |
| `mint_verified` | **skipped** — DANGEROUS verdict, no badge |
| `create_audit_request` | [`b90851bd81a5297e…`](https://stellar.expert/explorer/testnet/tx/b90851bd81a5297e96462ce5c89bcd20cce24de72866ce0a48fa1e73bcf0b209) |
| `post_bond` | [`5195684ee23236a7…`](https://stellar.expert/explorer/testnet/tx/5195684ee23236a7263cc885cfbd9d42ccb2ef262c0007fe3b22e80f4cf54baf) |
| **`slash`** | [`4518657fdc161a8c…`](https://stellar.expert/explorer/testnet/tx/4518657fdc161a8cc5b7669e1a6de67cc303f2bcfed1d980375c4c2c2e12abd8) |

Verified by reading back from chain rather than from the orchestrator's own result object:
`lookup_by_hash` returns the same verdict and score as the report, `registry.is_verified` and
`tokens.is_verified_token` are both `true` for the SAFE skill and `false` for the DANGEROUS one,
and the on-chain `evidence_hash` matches the `sha256` of the published report bytes exactly.

The amounts in the live suite are deliberately small (fee 0.1 · bond 0.2 USDC) rather than 5/10.
Money only flows one way — the developer pays every fee, the auditor and admin receive every
settle and slash — so a suite sized at 5 USDC per request drains the payer in three runs and then
fails for lack of balance instead of for the thing under test. Refilling needs the Captcha-gated
Circle faucet.

### Four behaviours found by running it, not by reading documentation

1. **Transaction meta is `v4` now, not `v3`.** Reading `meta.v3.soroban_meta.return_value`
   silently yields `None`. The `request_id` from `create_audit_request` arrives that way, and the
   guessing fallback (`get_request_count() - 1`) once pointed at a request **belonging to STE-13**,
   so `post_bond` came close to locking a bond into someone else's job. The orchestrator now
   **refuses to guess** when the id is missing.
2. **`prepare_transaction` raises a generic message** ("Simulation transaction failed…") and keeps
   the detail on the response attached to it. Without digging that out, a contract rejection looks
   like a network glitch and gets retried three times for nothing.
3. **Enum unit variants encode as `vec[symbol]`.** Established by simulation: `vec[symbol]` ->
   `Error(Contract, #3)` (accepted, rejected by business logic); `u32` and a bare symbol ->
   `Error(WasmVm, InvalidAction)`; 4 arguments -> `UnexpectedSize`.
4. **Error numbers collide across contracts.** Escrow `#3` is `NotOpen`, registry `#3` is
   `SkillNotFound`, and `#10` comes from the **USDC SAC** — a third party's contract — surfacing
   through escrow when the payer cannot cover the transfer. A single registry-owned error table
   makes a real escrow failure read as `Unknown (#10)`.

## On-chain evidence — the x402 payment (STE-19)

The full paid loop, run on testnet with a **fresh agent** carrying no history at all:
402 → pay USDC → licence minted → 200, and a second call returns **200 without paying again**.

| | |
|---|---|
| Agent | `GBFXMHA77OLBYF3JJB43O6CKZ4QR35AAQALJK72MUIHTZNBVAQGTTZWY` |
| Facilitator | OZ Channels `https://channels.openzeppelin.com/x402/testnet` |
| Asset | USDC SAC `CBIELTK6…` · `payTo` classic account `GD73M4F7…` |
| Price | `1000000` base units = **0.10 USDC** |
| Licence mint | [`5768516f156b74e7…`](https://stellar.expert/explorer/testnet/tx/5768516f156b74e7e97ac733c45261f59ec38d550a990159743d5fb6720a9ef9) |

Verified by reading back from chain rather than from the API response:

- the agent's USDC balance went **2.0000000 → 1.9000000** — exactly 0.10 paid, no more
- `tokens.has_license(agent, skill, version)` → **true**
- the token `total_supply` increased

A DANGEROUS skill is **never offered for sale**: `/use` returns `403 NOT_VERIFIED` with no payment
challenge at all, and the token contract refuses it independently through the VERIFIED badge
gate.

### Notes that will save time next round

- **The testnet facilitator key needs no authentication.** `curl https://channels.openzeppelin.com/testnet/gen`
  returns `{"apiKey": "..."}` directly — no Captcha, no OAuth (those are mainnet only). So the paid
  path is not blocked behind a manual step the way the Circle faucet is.
- **The 402 shape was captured from the reference server**, not guessed: the requirements travel in
  the `PAYMENT-REQUIRED` header as base64 JSON with an empty body. `amount` is 7-decimal.
- **`/supported` reports `areFeesSponsored: true`**, which means the buying agent needs no XLM at
  all — it signs an auth entry and the facilitator assembles and pays for the transaction.

## On-chain evidence — nothing undeliverable is sold (STE-42)

**The bug.** `/use` settled the USDC and minted the licence *before* it looked for the artifact.
Only `com.sterish.weather-lookup@1.0.0` had one, so every other SAFE version — including all
12 catalogue skills seeded in STE-18 — offered a 402, took 0.10 USDC, minted, and then answered
`404 ARTIFACT_NOT_FOUND`. The STE-19 proof passed only because it happened to buy that one skill.
A second hole in the same path: the payer was read from `X-AGENT-ADDRESS`, because the Stellar
exact payload carries no payer, so a client that omitted the header was settled and then told
`400 UNKNOWN_PAYER` with no licence.

**Fixed and proven on testnet, 15 September 2026**, API running locally against the deployed
contracts and the live OZ Channels facilitator, driven by `api/scripts/e2e_paid_path.py` with the
real x402 client (`demo/x402-buyer/buy.js`). Every claim was checked against the ledger, not
against what the API answered. Full record: [`evidence/ste-42-e2e-paid-path-2026-09-15.json`](evidence/ste-42-e2e-paid-path-2026-09-15.json).

| | |
|---|---|
| Artifacts published | 14 by `intake publish-artifacts` (12 catalogue + 2 safe fixtures), each written only after bytes, corpus index and on-chain `content_hash` agreed and the on-chain verdict was SAFE |
| Every SAFE row in the registry | **15 for sale (402), 33 not offered (404, no challenge), 0 anything else** |
| DANGEROUS `com.fixtures.poisoned.token-drainer@1.0.0` | 403, no challenge |
| Agent (fresh, no history) | `GAUJNTTBOZ4YONBUHLMKQOJGQNIHBN423ID26AKQ62BVK3HKKTJDMD4V` |
| Funding (create + trustline + 0.2 USDC, one tx) | [`18cf690533f75618…`](https://stellar.expert/explorer/testnet/tx/18cf690533f756183fe7fcfc8af9cec6a54734a8b23b154ffe936aca613d5777) |
| Bought `org.stellar.skills.agentic-payments.x402@2026.8.31` **with no `X-AGENT-ADDRESS`** | settlement [`73a5124de3b85434…`](https://stellar.expert/explorer/testnet/tx/73a5124de3b854341f3bbeacf45ff6304ee6b59fa8072d16c43c3a16d6320221) · mint [`858c136e206a3a03…`](https://stellar.expert/explorer/testnet/tx/858c136e206a3a037baa81dd68c54e3a6ab6b619adca392e0337f5ef6173fdb2) |

Verified from outside the API:

- the agent's USDC balance dropped by **exactly 0.1**, and `payTo` received at least 0.1
- `has_license(agent, skill, version)` read **true** from the tokens contract
- `content_hash` of the served bytes = the on-chain `a1728e0400eb3bc9…`
- the same agent then **signed a second payment** for the licence it already held, again without
  the header: served `held`, **no settlement**, balance unchanged

The failure paths that cannot be forced on a live network — a mint that fails after settlement, a
mint whose confirmation times out but lands, concurrent payments from one payer, a facilitator
that verifies without naming a payer — are covered offline in `api/tests/test_use_x402.py`, each
asserting how many times settle ran.

### Re-verified against Registry v2 (16 September 2026)

STE-44 moved the Registry and Tokens to new addresses, and STE-18 added demo skills. After rebasing
onto that `main`, the same e2e was run again with the API pointed at **Registry v2**
`CCZJN366…` and **Tokens v2** `CB6VK4EX…`. Record:
[`evidence/ste-42-e2e-paid-path-v2-2026-09-16.json`](evidence/ste-42-e2e-paid-path-v2-2026-09-16.json).

| | |
|---|---|
| Artifacts published against v2 | 16 skill versions: 12 catalogue (`cctp` is DANGEROUS on chain), 2 safe fixtures, and the SAFE demo versions `release-notes` 1.0.0 and `changelog-writer` 1.0.0. 6 refused as not SAFE on chain |
| SAFE rows in `/skills` | **15 for sale, 0 not offered**, nothing else |
| Agent (no `X-AGENT-ADDRESS`) | `GCF76SG6QUBTJHK6AEFPS22TOB6JO5TKXXR5FW3QSDFOFLNXNLCJTXSC` |
| Settlement · mint | [`ea78a0348640629a…`](https://stellar.expert/explorer/testnet/tx/ea78a0348640629ae8e96a4de8afdf6fab57b8f4414e240064995ab07b43bea4) · [`f73dfdfc46b35d62…`](https://stellar.expert/explorer/testnet/tx/f73dfdfc46b35d6235294736b51004a946d740b2ead0b29d5a6fe244036bd126) |

Same results as on v1: exactly 0.1 USDC paid, `has_license` true on Tokens v2, served bytes hash to
the on-chain `content_hash`, and a second signed payment for the held licence settles nothing.

`publish-artifacts` now includes the `demo` label by default, because the demo set contains SAFE
versions that are for sale too.

`deploy/artifacts/` is operator-supplied and gitignored (STE-25), so merging does not put artifacts
on the server. **The redeploy for this ticket must run, on CT 204:**

```bash
cd /opt/sterish/deploy
docker compose --env-file .env --profile tools run --rm publish-artifacts
```

(On 16 September the v2-verified artifacts were already copied to CT 204 as a mitigation, STE-45;
the command above is idempotent and leaves matching artifacts untouched.)

`verify.sh` sends its own User-Agent for that check. Cloudflare answers the default
`Python-urllib/3.x` agent with `403 error code: 1010`, an HTML page that is not an answer about
`/use` at all.

## Backend deployment (STE-25)

A Docker Compose stack in `deploy/`: the API (with the indexer running inside its process) plus
Caddy as a reverse proxy with automatic TLS. Full procedure in `deploy/README.md`.

**Verified end to end locally**, not merely written down: the image was built, the stack brought
up, and the whole surface exercised **through the reverse proxy** — `/health`, `/check`,
`/skills`, `/use` (402 with a challenge), and `/use` on a DANGEROUS skill (403, never offered).
Then a **fresh agent actually bought a licence through the containerised stack**: mint tx
[`739428bf85f92386…`](https://stellar.expert/explorer/testnet/tx/739428bf85f92386981a5858273b013956456238b8c7ee1c639e680b0939275f).

`deploy/verify.sh <base-url>` runs the same checks against any host, error paths included —
those are the ones that rot silently.

### Three things that only surfaced by actually running it

1. **A 3.8 GB build context.** The context is the repository root, so without a
   `.dockerignore` every build shipped `contracts/target` (3.3 GB) plus two
   virtualenvs and `node_modules`. After adding one: **340 kB**.
2. **`docs/` is a runtime dependency, not documentation.** `sterish_pipeline.specs`
   locates the repository through `docs/specs/verdict.schema.json` and loads the
   reference `content_hash` implementation from `docs/specs/reference/`; `/use`
   hashes artifacts through that module before serving them. Excluding `docs/`
   makes the paid path raise `SpecsNotFound` **in production** while every offline
   test stays green.
3. **An empty volume and an empty Caddy directive.** The container runs as uid
   10001 but a named volume arrives owned by root (`unable to open database
   file`), and an empty `STERISH_ACME_EMAIL` produces an `email` directive with no
   argument, which makes Caddy **refuse to start at all** — `{$VAR:default}` only
   applies when the variable is unset, not when it is empty.

### Live — deployed

| | |
|---|---|
| **Public URL** | **https://api-sterish.jameshub.fun** (Cloudflare Tunnel) |
| Alternate URL | https://pve02.tail4d50d6.ts.net (Tailscale) |
| Host | Proxmox `pve02`, LXC **204 `ct-sterish`**, `192.168.18.43/24` |
| Spec | 2 cores · 2 GB RAM · 20 GB `local-lvm` · unprivileged · `nesting=1,keyctl=1` · `onboot=1` |
| TLS | Genuine Let's Encrypt via Tailscale (`ssl_verify_result: 0`), valid until 5 Dec 2026 |
| Public exposure | Tailscale Funnel on pve02 |

Verified **through the public URL**, not from inside the host: all of `deploy/verify.sh`
passes (`/health`, `/skills`, 404/400 on the error paths, `/use` 402 with a challenge,
`/use` on a DANGEROUS skill 403), and a **fresh agent really did buy a licence over
public HTTPS** — mint tx
[`9e59297638174ee3…`](https://stellar.expert/explorer/testnet/tx/9e59297638174ee3a063877e815cb78362ad46dbf276e6454dbee0232b0ad4df).

**Through Cloudflare** (`server: cloudflare`, `via: 1.1 Caddy`): all of `verify.sh`
passes and **a fresh agent bought a licence over that domain** — mint tx
[`7d01568dd1ccebf4…`](https://stellar.expert/explorer/testnet/tx/7d01568dd1ccebf4c9bc5fc10aa9f91e92bcf3faae5b4ae33705f14e8a9af9ad).
The tunnel is *locally managed*: routing comes from `deploy/cloudflared-config.yml`, not the
dashboard. One subdomain level only, because Universal SSL covers `*.jameshub.fun` and no
deeper — a lesson Sterun had already recorded.

**The trap that cost real time:** the tunnel credentials file must be owned by **uid 65532**, not
root. The official cloudflared image runs as nonroot, so a root-owned 0600 file gives
`permission denied` and a container that restarts forever while every other service looks
healthy. The answer had been visible in Sterun's deployment all along (`-rw------- 1 65532
65532`).

**Automatic restart is proven:** the CT was rebooted and the services came back on their own in
about 20 seconds with no intervention (`onboot=1` plus `restart: unless-stopped`).

pve02 was chosen because **pve01's Funnel is already taken by `ct-sterun`** (proxying to
`192.168.18.42:3001`); claiming the root path there would have killed that service. The CT
conventions — naming pattern, nameserver, bridge, unprivileged, onboot — were copied from
`ct-sterun` rather than invented.

### A production bug that only appeared once deployed

Two requests came back **503 without ever reaching the application**, one of them right after
`mint_license`. Easy to mistake for a network glitch, because retrying worked.

The cause: every handler was `async def` while **every call inside them was blocking** — the
Soroban simulations, the facilitator round trips, and the mint. All of it ran on the event loop,
so a single mint polling the ledger for a few seconds froze the entire API. With one client this
is invisible; behind a public URL it looks like a service that is merely temperamental.

Fixed by dropping `async` (FastAPI runs sync handlers in a threadpool). Demonstrated on the
deployment: 12 parallel requests, slowest 4.07 seconds, total wall time **4.17 seconds** — still
blocked, the wall time would have been roughly 12×.

### Redeploy 2026-09-09 — STE-33 reaches production

Until today CT 204 was still running `84df2d7`, twenty commits behind `main`. The STE-33 fix had
merged but was running nowhere: Ancung measured the live API after PR #21 landed and got numbers
practically identical to the pre-fix ones. **Merging is not deploying** — nothing on this stack
pulls `main` on its own, `ctredeploy` has to be run.

After `bash /usr/local/bin/ctredeploy`, the commit running is `1af75fd`.

| `GET /skills` | sebelum redeploy | sesudah redeploy |
|---|---|---|
| `limit=3` | 2.3s | 1.5s |
| `limit=20` | 10.3s | **2.8s** (median of 8 samples; 2.3–6.9s) |
| `limit=50` | 31.6s | 4.6s |

The public numbers are higher and much noisier than the 1.9s measured at the application while
developing STE-33. The difference is not the tunnel — measured from inside the container,
`limit=20` came back at 3.7s. What remains is RPC latency from the CT's network to
soroban-testnet, which is higher and more variable than from a developer machine. The "under two
seconds" requirement is met at the application; over the public internet it is 2–3 seconds and
occasionally misses.

**Verified after redeploying, not assumed:**

* `deploy/verify.sh https://api-sterish.jameshub.fun` passes in full — `/health` 200 with
  `rpc_reachable`, `/skills`, 404/400 on the error paths, `/use` 402 with a challenge, `/use` on
  a DANGEROUS skill 403.
* **All 47 rows** of `/skills?limit=100` were cross-checked one by one against
  `/check/{skill_id}/{version}` — verdict, `trust_score` and `is_verified` all match, zero
  discrepancies. That is what proves the concurrent fan-out does not shift a verdict onto a
  neighbouring row.
* Two pages of pagination do not overlap and their order matches the full listing.
* `STERISH_CHAIN_CONCURRENCY=20` really is present in the container's environment.

**On the CORS errors that occasionally appeared in the dashboard** (reported by Ancung): the
application's headers are correct, and that is now confirmed through the public URL — the
`OPTIONS` preflight, a 200 response and a 404 response all carry `access-control-allow-origin`.
Ancung's hypothesis that what looked like CORS was really a Cloudflare error page for a stalled
request is consistent with that: a Cloudflare error page does not carry the application's CORS
headers. A `/skills` request that used to hold the connection for a dozen seconds now finishes in
2–3, so the opportunity is much reduced — but this is a causal argument, not a direct observation
of the error disappearing.

### Redeploy 2026-09-10 (second) — catalogue seeded, reports live (STE-18, STE-32)

The registry went from 47 synthetic test entries to **66**, twelve of them real
skills.stellar.org catalogue skills. The verification chain, which had been broken at its last
link, is now closed.

| | |
|---|---|
| Commit running | `af03eba` |
| Registry | 47 → **66** entries |
| Real catalogue skills on chain | **12**, all `SAFE` + VERIFIED |
| Poisoned fixtures on chain | **4**, all `DANGEROUS`, none VERIFIED |
| `report_uri` populated and bytes matching `evidence_hash` | **19 / 19** |
| Mismatches | **0** |

The 47 older versions still report `report_uri: null`, and that is correct — they predate report
publishing, and the endpoint deliberately advertises a link only for a report that exists.

New environment in `/opt/sterish/deploy/.env`: `REPORT_BASE_URL` (the API root, not a `/reports`
prefix — the route supplies that), `STERISH_REPORTS_DIR` through compose, plus
`EVIDENCE_SKILL_ID` and `EVIDENCE_VERSION` so `verify.sh` can check the hash chain itself.

`verify.sh` no longer merely asks "did it return 200":

```
/reports missing -> 404                        OK (404)
/reports served                                OK (200)
  sha256(report) == evidence_hash              OK (2620c159de75f4dc…)
```

Full audit evidence with the transaction tables: [`audit-evidence.md`](audit-evidence.md).

### Seed run 2026-09-15 — cctp published, four demo skills, junk filtered (STE-18)

No redeploy: this is a registry change plus an API behaviour change waiting on the next one.

| | |
|---|---|
| Registry | 66 → **71** entries |
| Real catalogue skills on chain | **13**, nothing held back |
| Demo skills lighting all four registry states | **4** (6 versions) |
| `sha256(report)` matching the on-chain `evidence_hash` | **25 / 25** |
| Time per skill | median **5.6 s**, slowest **14.7 s** |

New on chain, all under Registry `CAPDQW2XWTOCFQEP3AUCRRQHVJ5IOUZ45DWPNPVG7USNPE6RZQ3BUXND`:

| skill_id | version | verdict |
|---|---|---|
| `org.stellar.skills.cross-chain.cctp` | 2026.8.31 | **DANGEROUS** — re-audited after the STE-36 fix, published rather than held back a second time |
| `com.fixtures.demo.release-notes` | 1.0.0 / 2.0.0 | **SAFE** / **DANGEROUS** — the rug pull, invariant R4 |
| `com.fixtures.demo.changelog-writer` | 1.0.0 / 2.0.0 | **SAFE** / **UNAUDITED** — the stale-version warning |
| `com.fixtures.demo.ledger-inspector` | 1.0.0 | **WARNING** via policy row 8 |
| `com.fixtures.demo.table-formatter` | 1.0.0 | **WARNING** via policy row 6 |

Every transaction hash, the findings behind the `cctp` verdict, and the full hash table are in
[`audit-evidence.md`](audit-evidence.md). Verify the whole set against the contract with
`pipeline/scripts/verify_onchain.py`.

The 12 pre-existing catalogue entries also received a fresh `submit_verdict` with an unchanged
verdict and score: the internal report model changed after 10 September (STE-38, STE-40), which
moves the document-level `evidence_hash`, and the ledger must point at a hash the served report
reproduces. Superseded transactions are listed in `audit-evidence.md`.

**Needs a redeploy to take effect in production:** `/skills` and `/feed` now hide test namespaces
by default and report `chain_total` / `hidden_test_entries`. 47 of the 71 entries are test
scaffolding that no contract call can remove. No new environment variables.

### Operations

```bash
# inside CT 204
bash /usr/local/bin/ctredeploy          # fetch origin/main, rebuild, restart
cd /opt/sterish/deploy && docker compose logs -f api
```

The CT's `deploy/.env` is mode 600 and was delivered over stdin, so `MINTER_SECRET` and
`OZ_API_KEY` never entered the host's process list or an SSH log.

**Funnel means exposed to the public internet**, which is what the ticket asked for ("a public
URL with TLS"). To restrict it to the tailnet: `tailscale funnel --https=443 off` on pve02.

### Redeploy 2026-09-15 — STE-44, upgradeable v2

No Sterish contract was upgradeable: there was no `update_current_contract_wasm` anywhere in
`contracts/`. And upgradeability **cannot be added to a live contract** — in Soroban a contract
replaces its own wasm, so the capability has to be in the bytes that were already deployed.
Making the Registry upgradeable therefore always meant a fresh address. Since the redeploy was
unavoidable, it was done properly once.

**Two contracts, not three.**

| Contract | Action | Why |
|---|---|---|
| Registry | redeployed, upgradeable | the one that will actually grow features |
| Tokens | redeployed, upgradeable | its `__constructor` stores `registry` with **no setter, on purpose**, so it cannot be repointed at a new Registry — it had to move alongside |
| Escrow | **untouched** | its constructor takes only `usdc_token` + `admin`; it holds no Registry reference (verdicts are read off-chain by the operator). It keeps `CCVCNFXK…` |

Escrow stays immutable **and** stays deployed. It is the only contract holding real USDC, and an
admin who can swap the logic of a fund-holding contract can drain it.

#### Addresses

| Contract | Address | WASM sha256 (`aarch64-apple-darwin`) | Entrypoints |
|---|---|---|---|
| **Registry v2** | [`CCZJN366SV57JEBZVXGYY3ZBLJNFV4IR5ILCAI3EMX2WDNQPEPQ4BRL2`](https://stellar.expert/explorer/testnet/contract/CCZJN366SV57JEBZVXGYY3ZBLJNFV4IR5ILCAI3EMX2WDNQPEPQ4BRL2) | `ba740db865b23834b795a8a985cc22ae996605c06e776f46780575e52f56839f` | 22 (was 15) |
| **Tokens v2** | [`CB6VK4EXEN7V6MXLOFUI2ECMLSDUXAUV5EZICWBICKJDL3WPPU3CTP3T`](https://stellar.expert/explorer/testnet/contract/CB6VK4EXEN7V6MXLOFUI2ECMLSDUXAUV5EZICWBICKJDL3WPPU3CTP3T) | `719f93beab52ace8d1cecf9b5ef1a1c987798fd2c6230f83a0e3d258490d5825` | 21 (was 14) |
| Escrow (unchanged) | [`CCVCNFXK4YHY3ECPWCXLAMEXT4MI457ZREAZBR57CEJ3GQXONW7HVVDE`](https://stellar.expert/explorer/testnet/contract/CCVCNFXK4YHY3ECPWCXLAMEXT4MI457ZREAZBR57CEJ3GQXONW7HVVDE) | `cb241f74d20146b9d4895160e68d0c337f68317c3b6c1f272b0505cdb84d0ad0` | 10 |

Superseded, still on chain, still readable:
[Registry v1 `CAPDQW2X…`](https://stellar.expert/explorer/testnet/contract/CAPDQW2XWTOCFQEP3AUCRRQHVJ5IOUZ45DWPNPVG7USNPE6RZQ3BUXND),
[Tokens v1 `CCHVZRLO…`](https://stellar.expert/explorer/testnet/contract/CCHVZRLOFGZ5IAYQUSHIPQOTVFABOX6SK5MHNZZUKAOT333KZNVW4EJX).
Every transaction recorded against them earlier in this document is unaffected.

The escrow row is the strongest single piece of evidence that it was left alone: its sha256 is
**byte for byte the one recorded on 2026-09-03**, a full ticket and several contract changes
later. `git diff origin/main -- contracts/escrow/` is likewise empty.

Deploy transactions (all four from `sterish-deployer`, 2026-09-15 15:50–15:51 UTC):

| Step | Transaction |
|---|---|
| upload Registry v2 wasm | [`80616f163aa41f436fe3193482a0201445990e5a2a845c6ec693d42e08673c12`](https://stellar.expert/explorer/testnet/tx/80616f163aa41f436fe3193482a0201445990e5a2a845c6ec693d42e08673c12) |
| deploy Registry v2 | [`0d95dd3d52352a656cf05244c5e82fc3514248a5e004ef8a61f78a05b8c64195`](https://stellar.expert/explorer/testnet/tx/0d95dd3d52352a656cf05244c5e82fc3514248a5e004ef8a61f78a05b8c64195) |
| upload Tokens v2 wasm | [`0859b7bd0777b7a9c012d23bdf837e4f6cd73feb19c2ce53fb10791d143e7c0b`](https://stellar.expert/explorer/testnet/tx/0859b7bd0777b7a9c012d23bdf837e4f6cd73feb19c2ce53fb10791d143e7c0b) |
| deploy Tokens v2 | [`e02f67449ae5d713d689539d389e3a78c86bee5c33c795f3bcfe10c47dced7da`](https://stellar.expert/explorer/testnet/tx/e02f67449ae5d713d689539d389e3a78c86bee5c33c795f3bcfe10c47dced7da) |

#### Verify the deployed bytes without a toolchain

```bash
stellar contract fetch --id CCZJN366SV57JEBZVXGYY3ZBLJNFV4IR5ILCAI3EMX2WDNQPEPQ4BRL2 \
  --network testnet --out-file registry.wasm
sha256sum registry.wasm   # ba740db865b23834b795a8a985cc22ae996605c06e776f46780575e52f56839f
```

Done for all three contracts at deploy time; all three matched the manifest rows exactly.

#### The upgrade mechanism, as deployed

```
propose_upgrade(wasm_hash) -> ready_at   admin only; emits UpgradeProposed
execute_upgrade()                        admin only; rejected before ready_at; emits UpgradeExecuted
cancel_upgrade()                         admin only; emits UpgradeCancelled
renounce_upgradeability()                admin only; PERMANENT; emits UpgradeabilityRenounced
get_pending_upgrade() / get_upgrade_delay() / is_upgradeable()   reads, never panic
```

Read back from chain immediately after deploy:

```
registry.upgradeable = true    registry.delay_secs = 300    registry.pending = null
tokens.upgradeable   = true    tokens.delay_secs   = 300    tokens.pending   = null
```

**300 seconds** is the testnet delay: long enough that the timelock is real and demonstrable in a
demo, short enough not to block the team. It is a **constructor parameter stored in state**, not
a constant, so mainnet would differ by configuration rather than by code — and it has no setter,
because an admin who can shorten the delay does not have a timelock. A delay of `0` is rejected
by the constructor outright.

The admin is a **single Stellar account** (`GAGU7Z5R…`) for now. Going 2-of-3 later costs nothing
and needs **no contract change**: multisig on Stellar is a property of the *account*, so the
contract keeps storing one `Address` and calling `require_auth()`, and the change is a
`Set Options` transaction on that account.

#### The trap nothing on chain can close

`update_current_contract_wasm` takes a hash, and there is no host function that can read a wasm's
exports. So a contract **cannot** refuse to upgrade into a replacement that has no upgrade
function — and the moment it does, it is frozen at that code forever.
`contracts/tests/tests/upgrade.rs` demonstrates exactly that on real artifacts.

The guard that *can* exist runs before the bytes are ever published:
[`scripts/verify-upgrade-target.sh`](../scripts/verify-upgrade-target.sh), in the `Contracts`
workflow on every change, fails if `sterish_registry.wasm` or `sterish_tokens.wasm` has lost any
of the seven upgrade entrypoints — and fails equally if `sterish_escrow.wasm` ever gains one.
That is a narrower promise than an on-chain guard and is stated as such: it protects the
artifacts this repository builds, not an operator who uploads a wasm from somewhere else. What
bounds *that* is the timelock, which makes the proposed hash public for its whole duration, and
`renounce_upgradeability()`, which ends the question permanently.

#### The timelock, exercised on chain

The mechanism was run against the live Registry immediately after deploying, before any of the
above was written down. The target was the **identical** wasm hash already deployed, so the swap
was a no-op and nothing about the contract changed — what is being proved is the path, not a new
version.

| Step | Ledger time | Result |
|---|---|---|
| `propose_upgrade(ba740db8…)` | `proposed_at 1789488092` | ok, `ready_at 1789488392` (= +300s exactly). Event `UpgradeProposed` — [`17b09809…`](https://stellar.expert/explorer/testnet/tx/17b0980977d56d4eb17bd4e6a05f00c9ce2c8eabacfd8b1abc7e90b482eab8fd) |
| `execute_upgrade()` **during** the window | — | **rejected**, `Error(Contract, #13)` = `UpgradeNotReady`. The proposal was not consumed: `get_pending_upgrade` still returned it |
| `execute_upgrade()` after `ready_at` | `executed_at 1789488407` | ok. Event `UpgradeExecuted` — [`604dab0d…`](https://stellar.expert/explorer/testnet/tx/604dab0de14ee28abf2d1c6958f45d5f2338ff188b8994330fb0855c75849312) |

Read back from chain afterwards:

```
skill_count    = 24                       <- every migrated skill survived a real wasm swap
admin          = GAGU7Z5R…                <- instance storage intact
auditor        = GCFCURTZ…
upgrade_delay  = 300
is_upgradeable = true                     <- upgradeability came across with the new bytes
pending        = null                     <- the executed proposal was cleared, not left behind
cctp@2026.8.31 = Dangerous, score 10      <- a persistent VersionRecord, unchanged
wasm sha256    = ba740db8…                <- the same bytes, as intended for a no-op swap
```

So the 300-second delay is not a claim about what the code would do; it is a measured wait, with
an on-chain rejection in the middle of it that anyone can look up.

#### Migration

`scripts/migrate-registry.py` replayed the meaningful entries onto the v2 pair, reading them off
the **old contract** rather than from a list in the script, so nothing could be silently left out
by a stale constant:

| | |
|---|---|
| Skills migrated | **24** |
| Versions migrated | **26** (`com.fixtures.demo.release-notes` and `…changelog-writer` each carry v1 and v2) |
| VERIFIED badges re-minted | **16** — exactly the `Safe` versions, no more |
| Skipped | the 47 `com.sterish.it-*` / `e2e-*` / `canon-*` entries, by `namespaces.is_test_skill_id` |

`com.fixtures.*` is **not** test residue and was migrated: it is demo data that is meant to be
visible. Entries were replayed in the old registry's `SkillIndex` order, which is registration
order, so `query_all_skills` pages identically and the dashboard's ordering did not change.

Verification reads back from the **new chain state**, never from what the script had just sent:
content hash, verdict, trust score, evidence hash and owner per version, plus the badge, plus the
cross-check that a badge exists if and only if the registry says the version is `Safe`.

Two things did **not** survive, and could not have:

* `registered_at` / `audited_at` are stamped by the contract from the ledger clock, so the v2
  records carry 2026-09-15 timestamps. The originals stay readable on the v1 contracts. A
  migrated record is a faithful copy of the **claim**, not of when the claim was first made.
* The v1 badges are soulbound and cannot be burned, so they still exist on Tokens v1. Nothing
  reads Tokens v1 any more, but it is not empty and this document does not pretend otherwise.

#### Wiring

| Where | Change |
|---|---|
| `.env` (root, gitignored) | `REGISTRY_CA` / `TOKENS_CA` repointed; `OLD_REGISTRY_CA` / `OLD_TOKENS_CA` recorded |
| `api/tests/conftest.py` | default `REGISTRY_CONTRACT_ID` / `TOKENS_CONTRACT_ID` |
| `.github/workflows/deploy.yml` | stack-boot env |
| `frontend/src/lib/fixtures.ts` | the offline-mock constant |
| the deployed API (CT 204) | `deploy/.env` — needs a redeploy to take effect |

**The frontend needs no code change, and that was checked rather than assumed.** The only
literal contract id anywhere under `frontend/src` is the one in `fixtures.ts`, which feeds the
offline mock. The real UI renders `evidence.contract_url` and `evidence.registry_contract_id`
straight from the API response — `frontend/src/modules/skill-detail/component/EvidenceLinks.tsx`
takes `evidence` as a prop and has no contract id of its own.

### Redeploy 2026-09-16 — production reads v2 (STE-45)

STE-44 moved the repo to Registry v2 and Tokens v2 on 15 September, but the running service on CT 204
still read v1 and still ran `c13ac21` (10 September), so neither the v2 addresses nor the STE-18
test-namespace filter had reached production.

**What was done, in this order:**

1. Checked on chain, not assumed, that the account behind the production `MINTER_SECRET`
   (`GAGU7Z5R…`, the deployer) **holds the minter role on Tokens v2**, and that Tokens v2 points at
   Registry v2. Switching first would have let `/use` settle payments it could not mint for.
2. `deploy/.env` on the CT: backed up as `.env.bak-20260916-v1`, then `REGISTRY_CONTRACT_ID` and
   `TOKENS_CONTRACT_ID` set to the v2 pair. Mode stays 600.
3. The index volume removed. It is a cache (see STE-25), and it held v1 events that must not
   decorate v2 records.
4. `ctredeploy` → running `dc0a0c6` (`main`, including STE-18, STE-44 and STE-39).
5. The repo `.env` moved to v2 as well (v1 kept as `REGISTRY_V1_CA` / `TOKENS_V1_CA`), so the
   pipeline and the API write and read the same registry.

**Verified through the public URL:**

| | |
|---|---|
| `/health` | `ok`, registry `CCZJN366…`, RPC and facilitator reachable |
| `/skills` | `total 24`, `chain_total 24`, no test namespace shown; SAFE 15, DANGEROUS 7, WARNING 2 |
| `/check` | `token-drainer` DANGEROUS/10, `release-notes` 1.0.0 SAFE/100 → 2.0.0 DANGEROUS/10, `cctp` DANGEROUS/10 |
| `/reports` | served, `sha256(report) == evidence_hash` |
| `verify.sh` | everything passes except `/use unpaid -> 402`, which fails for a script reason: on `main` it still hardcodes version `1.0.0`. A direct request answers 402 with the challenge. The fix (`SAFE_SKILL_VERSION`) is in STE-42 |

**A live risk found while verifying, and mitigated the same hour.** Production runs the pre-STE-42
`/use`, which settles and mints *before* it looks for the artifact. The artifact directory held only
`com.sterish.weather-lookup`, which is not on v2 — so all 15 SAFE skills were priced with nothing to
hand over, and a buyer would have paid 0.10 USDC for a 404. The artifacts for v2 were published with
STE-42's `intake publish-artifacts` (written only where bytes, corpus and the v2 `content_hash` agree
and the v2 verdict is SAFE: 16 versions, 6 refused) and copied to `deploy/artifacts` on the CT,
755/644, readable by the API's uid 10001. That is data, not code; no unmerged code runs in
production.

Proven with a real purchase through the public URL, fresh agent
`GCGV7KHNO5G6MSRTJHIXDYROGOFR2VF5Y4CS5ADS2ZW4SPIU6HVON36R`
([funding](https://stellar.expert/explorer/testnet/tx/8f430cac722c19058d3084566bfb5bb69ecaa422d64faa4d1200bcf4c50c15be)),
buying `dapp.data-fetching`: exactly 0.1 USDC paid, licence minted
([`3e6fcf757baad2e2…`](https://stellar.expert/explorer/testnet/tx/3e6fcf757baad2e2a93529721657b924f9f00800250669fa0dfec12a0aa19371)),
`/license` held, served bytes hash to the on-chain `content_hash`. Record:
[`evidence/ste-45-prod-purchase-2026-09-16.json`](evidence/ste-45-prod-purchase-2026-09-16.json).

**Still open until STE-42 merges:** the old code takes the payer from `X-AGENT-ADDRESS`, so a buyer
that omits the header is still settled and then refused. The purchase above sent the header for that
reason. *Closed on 17 September — see the STE-42 redeploy below.*

### Redeploy 2026-09-17 — `/use` never charges for what it cannot deliver (STE-42)

PR [#41](https://github.com/Lin1er/sterish/pull/41) merged as `03e7e5d`, deployed to CT 204 on
pve02 (now on NVMe, reached at `root@100.78.70.40`) with `ctredeploy`, then:

```bash
cd /opt/sterish/deploy
docker compose --env-file .env --profile tools run --rm publish-artifacts
```

→ **16 for sale (0 newly published — the STE-45 copies already matched), 0 not on chain, 6 not SAFE,
0 failed.** The new `deploy_payments` volume was created by compose.

**Verified through the public URL:**

| | |
|---|---|
| `deploy/verify.sh` | all checks pass: `/use` unpaid 402 with challenge, DANGEROUS 403, **every SAFE row: 15 for sale, 0 undeliverable priced** |
| rehearsal skill `com.sterish.e2e-rehearsal-unit-converter-1789569559` 1.0.0 (the one STE-27 paid for) | `404 ARTIFACT_NOT_FOUND` **before** any payment, no challenge |
| `api/scripts/e2e_paid_path.py`, real USDC | fresh agent `GAISQEDZDZO3ZODO6DRDD3DV5VKMVNOULTU7B4VASXSXH56BUOAIPXAG`, **no `X-AGENT-ADDRESS`**, bought `agentic-payments.x402`: paid exactly 0.1 USDC ([settle `c72b7def…`](https://stellar.expert/explorer/testnet/tx/c72b7defe42575b5fa83eed1f2e6c155112901eede29c1eeafd8496dfdb15c04)), licence minted to the payer ([`16755730…`](https://stellar.expert/explorer/testnet/tx/167557302d8a0d43e75325b012dd4c4a57da82a403a946fb13ac09f0587414b1)), bytes hash to the on-chain `content_hash`, a second signed payment settled nothing |

Record: [`evidence/ste-42-e2e-paid-path-prod-2026-09-17.json`](evidence/ste-42-e2e-paid-path-prod-2026-09-17.json)
([funding](https://stellar.expert/explorer/testnet/tx/f8aea7458bad0deb9078532415b1a5e46e033b0c1fedb2417abd1ae0e27879c4)).

**Operational note.** For up to 30 s after every redeploy the public URL answers `503` with an empty
body: Caddy's active health check (`health_interval 30s`) marks the API down while its container
restarts and does not look again until the next interval. It clears on its own; run `verify.sh`
after it has.


### Redeploy 2026-09-17 — corrected verdicts and re-anchored reports served (STE-37)

After the on-chain correction ([PR #44](https://github.com/Lin1er/sterish/pull/44); run record in
[`audit-evidence.md`](audit-evidence.md#executed-17-september-2026)), CT 204 was redeployed so
`/reports` serves the new `reports/` bytes, and `publish-artifacts` ran again:
**18 for sale (2 newly published: `cctp` and `price-checker`, now SAFE), 4 not SAFE, 0 failed.**

Checked through `https://api-sterish.jameshub.fun`, for every audited version:

| | |
|---|---|
| `/check` verdict, score, `audit_tx` equal the run log · `sha256(/reports bytes) == evidence_hash` | **25 / 25** |
| `/use` unpaid on `cctp` and `price-checker` | `402` with a challenge (they were `403` while DANGEROUS) |
| `deploy/verify.sh` | all checks pass; 17 SAFE rows for sale, 0 undeliverable priced |

Record: [`evidence/ste-37-public-reports-check-2026-09-17.json`](evidence/ste-37-public-reports-check-2026-09-17.json).
### Redeploy 2026-09-17 (third) — licences need proof of ownership, visitors are seen, filters work (STE-48, STE-53, STE-34, STE-46)

`467f29e` on CT 204 (PRs #50, #53, #54, #55, #56), ~12:00 UTC. `ctredeploy`, then the index volume
dropped and rebuilt (a cache; STE-46 backfills `mint_tx` from it), Caddy restarted to load the new
`Caddyfile`, `publish-artifacts` (18 for sale, 0 newly published). The payments volume was kept.

| Ticket | Checked through the public URL | Result |
|---|---|---|
| — | `deploy/verify.sh` | all pass; 17 SAFE rows for sale, 0 undeliverable priced, `sha256(report) == evidence_hash` |
| **STE-48** | real purchase by a fresh agent `GCLFME6G…` (`dapp.react`, settle [`92a64981…`](https://stellar.expert/explorer/testnet/tx/92a64981a142f8d0481a63e35262640018fa146425b45cc3cf9e6d458e253e2a), mint [`da0d2a93…`](https://stellar.expert/explorer/testnet/tx/da0d2a93b7e95141ae328057b4b3c2c36d068817c05d83247db66aced2d65558)), then `api/scripts/e2e_paid_path.py --expiry-wait` | holder **with** a SEP-53 proof → `200 held`, bytes match `content_hash`; address only, `?agent=`, another key's signature, replayed proof, a stranger's proof for the holder, another version's proof, and an **expired** proof (after 303 s) → all `401`, no artifact, no challenge; a stranger proving its own address → `402` ([`evidence`](evidence/ste-48-e2e-ownership-proof-prod-2026-09-17.json)) |
| **STE-53** | x402 challenge, 401 body, API logs | `resource.url` and `challenge_url` are `https://`; the API log shows the real visitor addresses, and `172.18.0.3` (Caddy) only for its own health checks ([`evidence`](evidence/ste-53-proxy-aware-prod-2026-09-17.json)) |
| **STE-34** | `api/scripts/verify_skills_filters.py` | PASS, 57 checks; `?verdict=SAFE` returns 17 SAFE rows only, `?verified=true` → `400 INVALID_PARAMETER` ([`evidence`](evidence/ste-34-e2e-skills-filters-prod-2026-09-17.json)) |
| **STE-46** | `GET /licenses?agent=GAISQEDZ…` | 200, the licence listed with its `mint_tx` backfilled by the rebuilt index |
| **STE-52** | `api/scripts/d3_flow_transcript.py` regenerated | 15/15, now recording the ownership-proof path ([`transcript`](evidence/d3-flow-transcript-2026-09-17.md)) |

**Expected side effect, announced on STE-48:** the dashboard's `200 held` path answers `401
OWNERSHIP_PROOF_REQUIRED` until its SEP-43 signing UI lands. New purchases are unaffected.

### Migration 2026-09-17 — production moves to a VPS, `api.sterish.xyz` (STE-54)

From the homelab LXC (Proxmox pve02, CT 204) to a VPS, `187.53.142.100` (Ubuntu 26.04, 2 vCPU / 8 GB /
96 GB, IPv4 + IPv6). Same Cloudflare Tunnel (`sterish-api`, `0cce8c0e…`), now with the VPS as its only
connector. Record: [`evidence/ste-54-vps-migration-2026-09-17.json`](evidence/ste-54-vps-migration-2026-09-17.json).

**Order, so there is never a moment with two ledgers taking payments:**

1. VPS prepared with the tunnel **off**: repo cloned, `.env` and the tunnel credentials copied
   host-to-host (never printed), Caddy bound to loopback, stack built, `publish-artifacts`
   (18 for sale, 4 not SAFE), health checked locally.
2. **13:49:02 UTC** — API stopped on CT 204, freezing the payments ledger.
3. Ledger copied: `sha256` `058a002e…` identical on the old host, in transit and on the VPS; 8 settlements,
   0 owed a licence.
4. VPS API and its tunnel connector started; CT 204's Caddy and connector stopped. **13:49:16 UTC** —
   `cloudflared tunnel info` lists one connector, origin `187.53.142.100`.
5. CT 204's redeploy scripts renamed `*.DISABLED-moved-to-vps`; its stack is kept for rollback.

**Verified through `https://api-sterish.jameshub.fun`, now served by the VPS:**

| | |
|---|---|
| `deploy/verify.sh` | all pass; 17 SAFE rows for sale, 0 undeliverable priced, `sha256(report) == evidence_hash` |
| real purchase, `e2e_paid_path.py` | fresh agent `GC6VEHOE…` bought `standards.ecosystem`: exactly 0.1 USDC (settle [`54d18460…`](https://stellar.expert/explorer/testnet/tx/54d18460153bc4bcc6c51229898c138a4591be9f5b8a681fbcde4346f8d4b170), mint [`2eb739ee…`](https://stellar.expert/explorer/testnet/tx/2eb739eeaeddbb7b344fd2bb539ff7681a069447f6318fe2f1641cdb961e047c)); holder served with a SEP-53 proof; address-only, forged, replayed, borrowed and wrong-version proofs all `401`; a second payment settled nothing |
| ledger continuity | 9 rows after the purchase: the 8 migrated plus the new one |
| API log | real visitor addresses, 0 5xx, **0 warnings** — the IPv6→IPv4 RPC retries seen on CT 204 are gone |

**`api.sterish.xyz` — live the same evening.** The Cloudflare origin certificate available (`cert.pem`)
turned out to be scoped to the `jameshub.fun` zone: `cloudflared tunnel route dns` with it created a
stray `api.sterish.xyz.jameshub.fun` record instead. That record was deleted in the dashboard, and a
proxied CNAME `api` → `0cce8c0e-6239-4454-9ec6-a2a4515e4c9d.cfargotunnel.com` was added in the
`sterish.xyz` zone (the stray name now returns NXDOMAIN). `REPORT_BASE_URL` then moved to
`https://api.sterish.xyz`; for a few minutes earlier it had been set there before the record existed
and was reverted, so `report_uri` briefly pointed at an unresolvable name.

Verified through `https://api.sterish.xyz`: `deploy/verify.sh` all pass; `report_uri`, the x402
`resource.url` and the STE-48 `challenge_url` all use `https://api.sterish.xyz`; the old hostname
still answers; and the D3 flow transcript was regenerated through the new hostname, **15/15**
([`evidence/d3-flow-transcript-2026-09-17.md`](evidence/d3-flow-transcript-2026-09-17.md)).

## Full-loop rehearsal against the v2 pair (STE-27, 2026-09-16)

The first run of the whole loop against Registry v2 + Tokens v2 + the unchanged Escrow — the
write path the migration had not yet exercised. **4 / 7 steps green**, 15 / 15 transaction links
resolve. The escrow-to-v2 wiring and both Tokens v2 roles held under real transactions; the paid
path charged an agent 0.10 USDC and minted its licence, then answered `404 ARTIFACT_NOT_FOUND`
(STE-42). Generated evidence: [`rehearsal/runs/2026-09-16T143919Z/EVIDENCE.md`](rehearsal/runs/2026-09-16T143919Z/EVIDENCE.md);
owners and tickets: [`rehearsal/FINDINGS.md`](rehearsal/FINDINGS.md).

## Operational notes

- **Registry and Tokens are upgradeable since STE-44** — two-step, 300s timelock, events on
  every step, and `renounce_upgradeability()` to switch it off permanently. **Escrow is not, and
  must not become so**: it is the only contract holding real USDC, and an admin who can replace
  the logic of a fund-holding contract can drain it. `scripts/verify-upgrade-target.sh` fails CI
  if that ever stops being true in either direction.
- **Testnet is reset periodically** by SDF — every contract address above disappears when that
  happens. `scripts/deploy-testnet.sh` exists so that redeploying is a single command.
  The next scheduled reset is **16 December 2026, 17:00 UTC**
  ([official schedule](https://developers.stellar.org/docs/networks#testnet-and-futurenet-data-reset)).
  A reset clears all ledger entries, contract data included, so after it: redeploy the contracts,
  update every address in this document, then re-seed with one `intake seed` run. What a third
  party can and cannot verify either side of that date is set out in
  [`audit-evidence.md`](audit-evidence.md).
- The USDC SAC address in Escrow is **immutable** (locked in `__constructor`, no setter). Getting
  it wrong at deploy time means redeploying.
