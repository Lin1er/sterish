# Full-loop rehearsal (STE-27)

One command that runs the whole Sterish loop against the **live testnet stack** and writes down
what happened as it happens. These are real transactions: real escrow locks, real USDC, real
mints. A rehearsal that does not touch the chain proves nothing.

| File | What it is |
|---|---|
| [`run_rehearsal.py`](run_rehearsal.py) | The runner. Uses the same `sterish_pipeline` modules production uses. |
| [`x402_pay.mjs`](x402_pay.mjs) | One x402 purchase, reported as JSON. Run by the runner, not by hand. |
| [`skills/`](skills/) | The two skills the run registers: a safe unit converter and a poisoned PDF summarizer. Neither was ever part of a seed run. |
| [`runs/<run-id>/`](runs/) | One directory per run. `EVIDENCE.md` is generated; nothing in it is edited by hand. |
| [`FINDINGS.md`](FINDINGS.md) | Written by a person after a run: what failed, who owns it, which ticket. |

Latest run: [`runs/2026-09-16T143919Z/EVIDENCE.md`](runs/2026-09-16T143919Z/EVIDENCE.md) —
**4 / 7 GREEN**, see [`FINDINGS.md`](FINDINGS.md).

## The seven steps

| # | Step | How the runner does it |
|---|---|---|
| 0 | Preflight | API `/health` names Registry v2; Tokens v2 `registry`/`auditor`/`minter` roles and Escrow `usdc_token`/`admin` read back from chain; balances logged |
| 1 | Developer submits a brand-new skill, escrow locks fee + bond | `create_audit_request` (developer) + `post_bond` (auditor); asserts status `Bonded` and escrow **+fee+bond** |
| 2 | Audit → SAFE → VERIFIED → settle | all three pipeline stages, then `orchestrator.orchestrate()` (register, publish report, `submit_verdict`, `mint_verified`), read back, then `settle` with balance assertions |
| 3 | Fresh agent checks via the dashboard → SAFE | new keypair, Friendbot, USDC trustline, 0.5 USDC from DEVELOPER; `/check/by-hash`, `/check/{id}/{v}`, `/license`; dashboard `/skills/<id>` if `--dashboard-url` is given |
| 4 | `use` without licence → 402 → pay → licence → 200 | `x402_pay.mjs` with `@x402/stellar`; agent balance and `has_license` read from chain |
| 5 | Second call → 200 | `X-AGENT-ADDRESS` only; asserts `X-STERISH-LICENSE: held` and no debit |
| 6 | Poisoned skill → DANGEROUS, blocked, not buyable | audit must be DANGEROUS; registered with its verdict; no badge; `/use` must be `403 NOT_VERIFIED` with no payment offer; `mint_license` must be refused by the contract itself |
| 7 | Slash: bond → reporter | new escrow job on the poisoned skill, `slash` to `REPORTER_ADDRESS`, balance assertions |

After the steps, every transaction hash is fetched from stellar.expert's API and from Horizon, and
the result is part of the evidence.

**Statuses.** `GREEN` · `RED` · `PARTIAL` (the check passed but not in the form the ticket asks
for) · `MANUAL REQUIRED` · `BLOCKED` (an earlier step did not produce what this one needs). Only
`GREEN` is counted. A dashboard on `localhost` can make step 3 `PARTIAL`, never `GREEN`.

## Run it

```bash
# once
(cd demo/x402-buyer && npm ci)

# optional, for step 3: the dashboard against the live API
(cd frontend && pnpm install && NEXT_PUBLIC_API_URL=https://api-sterish.jameshub.fun pnpm dev --port 3100)

# the run (from the repo root)
uv run --project pipeline python docs/rehearsal/run_rehearsal.py --dashboard-url http://localhost:3100
```

Needs `.env` at the repo root with `DEVELOPER_SECRET`, `AUDITOR_SECRET`, `DEPLOYER_SECRET` and
`REPORTER_ADDRESS`. Secrets are read and never printed; every string written to the evidence is
also scrubbed of them. The fresh agent's key is appended to `.env` as
`REHEARSAL_AGENT_<unix-time>_ADDRESS/SECRET`.

Set `LLM_API_KEY` to run stage 3 with the model; without it the verdict is the deterministic
policy, and the evidence says which.

**Contract addresses are pinned in the script** to the STE-44 pair, not read from `.env`. A
worktree `.env` written before 15 September still names Registry/Tokens v1, and a run that
silently used v1 would say nothing about the migration.

## Cost per run

| Account | USDC |
|---|---|
| DEVELOPER | −0.1 fee (settled job) −0.5 to the agent; the slashed job's fee is refunded |
| AUDITOR | +0.1 (settle) −0.2 (slash) |
| REPORTER | +0.2 |
| agent | +0.5 funded, −0.1 per purchase |

Testnet USDC only comes from the Circle faucet, which is Captcha-gated. When DEVELOPER or AUDITOR
runs dry, a person has to refill them at <https://faucet.circle.com/> — that is the one step here
that cannot be automated.

## What it leaves behind

Two skills per run in the append-only registry, under `com.sterish.e2e-*` so the API hides them
by default (`namespaces.new_test_skill_id`). Testnet resets to genesis on **16 December 2026**,
which also retires every link in the evidence.
