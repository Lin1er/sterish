# Sterish — Deployments

Deployment evidence, per point 8 of the working agreement. Every address below is **live on
Stellar testnet** and clickable. No secrets in this document — only public addresses (`G…`) and
contract addresses (`C…`); keys live in a git-ignored `.env` (see `CLAUDE.md`).

---

## Testnet — 2026-09-03 (STE-13)

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
`sha256(file)`), so the values above pin exactly the bytes that were deployed. Re-verify with
`bash scripts/build-wasm.sh --check`.

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

## Operational notes

- **v1 is non-upgradeable.** If an interface changes, redeploy and update this document.
- **Testnet is reset periodically** by SDF — every contract address above disappears when that
  happens. `scripts/deploy-testnet.sh` exists so that redeploying is a single command.
- The USDC SAC address in Escrow is **immutable** (locked in `__constructor`, no setter). Getting
  it wrong at deploy time means redeploying.
