# STE-27 rehearsal — findings

Run [`2026-09-16T143919Z`](runs/2026-09-16T143919Z/EVIDENCE.md), against the live stack on
16 September 2026: API `https://api-sterish.jameshub.fun`, Registry v2 `CCZJN366…`, Tokens v2
`CB6VK4EX…`, Escrow v1 `CCVCNFXK…`.

The evidence document is generated and untouched. This file is the human reading of it: what
failed, why, who owns it. Anything below marked **looked up after the run** was not produced by
the runner and says how it was obtained.

## Result: 4 / 7 GREEN

| # | Step | Status | Owner of what is left | Ticket |
|---|---|---|---|---|
| 1 | Submit brand-new skill, escrow locks fee + bond | **GREEN** | — | — |
| 2 | Audit → SAFE → VERIFIED → settle | **GREEN** | — | — |
| 3 | Fresh agent checks via the dashboard → SAFE | **PARTIAL** | Ancung (deploy the dashboard) | [STE-26](https://linear.app/sterish/issue/STE-26) |
| 4 | 402 → pay → licence → 200 | **RED** | James | [STE-42](https://linear.app/sterish/issue/STE-42) |
| 5 | Second call → 200 | **RED** (consequence of 4) | James | [STE-42](https://linear.app/sterish/issue/STE-42) |
| 6 | Poisoned → DANGEROUS, blocked, not buyable | **GREEN** | — | — |
| 7 | Slash: bond → reporter | **GREEN** | — | — |

No step was `MANUAL REQUIRED`. The only human-dependent input — testnet USDC — was already in the
team accounts, and the fresh agent was funded by a scripted transfer from DEVELOPER rather than
from the Captcha-gated Circle faucet.

All **15 / 15** transaction links resolve on stellar.expert and Horizon, and all 15 transactions
are `successful`.

## What the brief asked to watch for

**Escrow v1 with the v2 pair.** Proven. The off-chain side wired the untouched escrow to the new
Registry and Tokens without a hitch: request #18 locked, then settled after a v2 verdict and a v2
badge; request #19 slashed. Escrow holds no Registry reference, and nothing needed one.

**Tokens v2 roles.** Proven by transactions, not only by reads. `get_auditor_role` and
`get_minter_role` read back as AUDITOR and DEPLOYER in preflight, and both roles then authorised
real mints: `mint_verified` signed by AUDITOR
([`4eaf33eb…`](https://stellar.expert/explorer/testnet/tx/4eaf33ebe792e617e8eb39a2ad65ee58f22e63bcd9badde58f04776ea446d086))
and the API's `mint_license` signed by the minter
([`2053d3fe…`](https://stellar.expert/explorer/testnet/tx/2053d3fe4c60af74f0ef606ecb2bc8bc23ffcbfc34f5fa6f65bed92e073ab79f), looked up after the run, see F1).
The gate held too: `mint_license` on the DANGEROUS version was refused by the contract with
`#5 NotVerified`.

**STE-42.** Hit, exactly as the ticket describes. See F1.

## Findings

### F1 — the agent is charged, licensed, and served nothing (steps 4 and 5) · STE-42 · James

`GET /use` returned **402** correctly. With `X-PAYMENT` attached, the API settled, minted, and only
then looked for the artifact:

| UTC | What happened | Source |
|---|---|---|
| 14:41:42 | USDC SAC `transfer` agent → `GD73M4F7…`, 1000000 base units, fee-bumped by the facilitator | [`192d8453…`](https://stellar.expert/explorer/testnet/tx/192d845349e888df42b3caa55d32c23eb7cda39a63f04ea8de5a343f0fa957e4) — the runner found it through Horizon effects because the API returned no receipt; decoded after the run |
| 14:41:52 | `tokens.mint_license(agent, skill, 1.0.0)` signed by the minter | [`2053d3fe…`](https://stellar.expert/explorer/testnet/tx/2053d3fe4c60af74f0ef606ecb2bc8bc23ffcbfc34f5fa6f65bed92e073ab79f) — **looked up after the run** from the minter account's operations on Horizon and decoded; the API response carried no `X-STERISH-LICENSE-TX` |
| response | `404 ARTIFACT_NOT_FOUND` | runner |

The agent went 0.5 → 0.4 USDC, `has_license` is `true`, `/license` says `held: true`, and the
second call is **404 again** rather than `200 held`.

Worse than the ticket states today: **no version in Registry v2 has an artifact on the server.**
The only artifact deployed is `com.sterish.weather-lookup/1.0.0`, a legacy test id that STE-44
deliberately did not migrate. So on the live stack every purchase currently ends in a 404 after
payment, not only the catalogue skills. No second, "control" purchase was made for that reason —
it could only have repeated the same loss.

> **Correction, 17 September 2026.** The paragraph above was too broad, and it is left in place
> rather than rewritten so the record shows what was believed at the time.
>
> It was true of the **brand-new skill this rehearsal registered minutes earlier** — that artifact
> had never been published, so of course the server did not hold it. It was **not** true of the
> registry as a whole, and the sweeping form of the claim was not tested before it was written.
>
> @m.ulinasidiki pointed this out, and the STE-42 redeploy on 17 Sep published artifacts for the
> migrated entries: **16 for sale, 6 correctly refused as not SAFE, 0 failed.** Verified against
> production the same day: `GET /use/org.stellar.skills.dapp.react/2026.8.31` answers **402**, not
> 404 — under the STE-42 fix a price is only offered for something that can actually be delivered,
> so a 402 is positive proof the artifact is there.
>
> What remains true from F1: the agent in this run **did** pay, receive a licence, and get a 404.
> That is the bug STE-42 fixed, and this run is how it was caught on the live stack.

Evidence added to STE-42 as a comment. Not patched here: `api/` is James's.

### F2 — no public dashboard (step 3) · STE-26 · Ancung

No dashboard URL is documented anywhere in the repo (`docs/`, `frontend/README.md`, `deploy/`,
PR bodies), and STE-26 "dashboard live on Vercel" is still in Backlog. The runner therefore ran the
dashboard from this commit **locally** against the live API. It rendered the SAFE banner for the
new skill and the DANGEROUS banner for the poisoned one, straight from v2 chain data — the code is
ready, the deployment is not. Step 3 is `PARTIAL`, not `GREEN`, because "via the dashboard on the
live stack" did not happen.

Rerun with `--dashboard-url <vercel-url>` once it exists; the step turns green on its own.

### F3 — the orchestrator cannot express the product's economic order · STE-49 · James

Not a failed step — the runner worked around it — but production code cannot do what steps 1
and 7 did:

* `orchestrate()` opens the escrow job **after** the verdict, so fee and bond are not locked while
  the audit runs. The runner locked first using the orchestrator's own `onchain` primitives.
* `orchestrate()` always slashes to the **admin**. The runner passed `REPORTER_ADDRESS`.

### F4 — Tokens errors are named with the Registry's table · STE-50 · James

The refused mint in step 6 is `TokenError::NotVerified (#5)`, the right refusal. The pipeline's
error mapper has no Tokens table and printed `VersionAlreadyExists (#5, registry)`, which would
send an operator looking for a duplicate version. The evidence row states the tokens meaning next
to the pipeline's label.

## Notes that are not tickets

* **Stage 3 ran without the model.** No `LLM_API_KEY` in this environment (the key is Axel's). Both
  verdicts are the deterministic policy; stage 3 is advisory, and the safe skill still scored 100
  and the poisoned one 10 with 28 findings.
* **Reports are not served by the API for these skills.** The orchestrator published them into the
  run directory, not onto the API host, so `/reports/<id>/1.0.0` is 404. They are committed instead,
  and **looked up after the run**: `sha256` of both committed reports equals the on-chain
  `evidence_hash` (`c872b351…` SAFE, `9ee8b1ae…` DANGEROUS).
* **This worktree's `.env` still names Registry/Tokens v1.** The runner pins v2 and logs the
  mismatch in preflight. `.env` is local and was not changed except for appending the agent key.
* **Absolute local paths** appear in two `publish_report` rows of the evidence. Not secret; the
  runner now writes repo-relative paths for future runs.

## Remaining, out of scope for this run (Axel)

* Rough screen footage of each step, raw material for the demo video.
* Scheduling the team rehearsal with every owner.
* The demo video itself — the brief calls it STE-24; in Linear the demo video is
  [STE-28](https://linear.app/sterish/issue/STE-28) and STE-24 is the polish pass.
* Re-running steps 3–5 after STE-26 and STE-42 land. The ticket asks for failed steps to be
  repeated until green; that cannot happen in this run because both fixes belong to other owners.

---

# Run 2 — 17 September 2026 (`runs/2026-09-17T114445Z`)

Re-run after STE-42, STE-49, STE-50 and STE-37 landed. **4 / 7 GREEN — the same score as run 1, for
a completely different and much better reason.**

| # | Step | Run 1 | Run 2 |
|---|---|---|---|
| 1 | new skill, escrow locks fee + bond | GREEN | **GREEN** (request #22) |
| 2 | audit → SAFE → VERIFIED → settle | GREEN | **GREEN** |
| 3 | fresh agent checks via dashboard | PARTIAL | **PARTIAL** (still no dashboard, STE-26) |
| 4 | 402 → pay → licence → 200 | **RED — agent paid and got nothing** | **RED — nothing was charged** |
| 5 | second call → 200 | RED | BLOCKED (depends on 4) |
| 6 | poisoned → DANGEROUS, blocked, unbuyable | GREEN | **GREEN** |
| 7 | slash: bond → reporter | GREEN | **GREEN** (request #23, reporter +0.2) |

## Step 4 is red, and the system was right

```
GET /use  →  HTTP 404, PAYMENT-REQUIRED present=False, price 0.0000000 USDC
```

In run 1 this step charged the agent 0.1 USDC, minted a licence, then answered `404`. In run 2
**no price was offered and no money moved.** That is the STE-42 fix working exactly as designed:
a price is only quoted for something the server can actually deliver.

So the red is now **the rehearsal's own fault, not the product's.** Every run registers a
brand-new skill (`com.sterish.e2e-rehearsal-*`) whose artifact has never been published to the
server, so `/use` correctly refuses to sell it. Steps 4 and 5 cannot go green while the runner
registers a skill it never publishes an artifact for.

**This also settles the over-broad claim in F1 above.** Run 1's failure was the brand-new skill,
not the registry — exactly as the 17 September correction says.

**Fix (owner: Axel, this script):** either publish the new skill's artifact as part of step 2, or
point steps 4–5 at an already-published catalogue version. The first is truer to the loop the
ticket describes, because a developer submitting a skill does expect it to become buyable.

## Step 6 gained a detail worth keeping

The mint refusal now reads `NotVerified (#5, tokens)` instead of the registry's error name. That is
STE-50 live: the same refusal, finally labelled with the contract it came from.

## What is still not exercised

* **Step 3 dashboard** — STE-26, nothing is publicly openable.
* **STE-48 ownership proof** — merged but not deployed, so this run did not exercise the challenge
  flow at all. `GET …/challenge` is still `404` in production. Until the deploy, a licence can still
  be borrowed by anyone who reads the ledger.
