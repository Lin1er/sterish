# Finding the first external user (STE-30)

Everything needed to send the first message today. Targets, what to say, what to link, and what
to answer when they push back.

**The one thing this cannot do for you:** press send. The rest is here.

## The opening that is actually ours

Most outreach for a tool like this says *"we built something, please try it."* We can say something
better, because it already happened:

> **We already audited 13 skills from the official `skills.stellar.org` catalogue, and the results
> are on chain. Here is what we found in yours.**

That is a completed piece of work handed over before anything is asked for. It also demonstrates the
product instead of describing it, and it survives the obvious first question — *does this actually
run?* — because the transaction hashes answer it.

Concretely, we can show any of these without the other person doing anything:

| | |
| -- | -- |
| Catalogue skills audited, on chain | **13 of 13, zero exclusions** |
| Poisoned fixtures correctly caught | 4 of 4 `DANGEROUS`, no VERIFIED minted |
| False-positive rate, measured | **0 / 16** benign · false negatives **0 / 4** poisoned |
| Reports whose bytes hash to the on-chain `evidence_hash` | every one — `sha256(report) == evidence_hash` |
| A skill whose v1 is SAFE and v2 is DANGEROUS | live, and v1's badge does **not** reach v2 |

The last row is the demo that lands: a version-2 rug pull, caught, with the contract itself refusing
to licence it.

## Targets, strongest first

Sourced from the Stellar ecosystem directory via MCP Stellar Raven on **17 September 2026**;
activity dates are that snapshot. Verify a repo is still active before writing — a stale opener is
worse than none.

### 1. CleverCon — `clevercon-protocol/clevercon`

**Last commit 13 Sep 2026.** Testnet, TypeScript, winner at Stellar Hacks: Agents.

> *"Service marketplace and orchestrator that decomposes tasks, hires specialist agents, and pays
> them through x402 or MPP."*

**Why they are first.** They have our problem already, written in their own description. A
marketplace that **hires specialist agents** has to answer "which of these agents is safe to run?"
— and today nothing answers it. They also already pay through x402, which is the exact rail Sterish
licences run on. Nothing to integrate conceptually; they need the missing half.

**Opening line:** how do you decide which agent is safe enough to hire?

### 2. RouteDock — `winsznx/routedock` · routedock.xyz

**Last commit 7 Sep 2026.** Published on npm as `@routedock/routedock`.

One `client.pay()` that routes across the three Stellar agent-payment protocols. They are the
payment layer for autonomous agents; we are the trust layer for what those agents run. Adjacent,
not competing, and they already ship to real users through npm.

**Opening line:** you route the payment — do you know what the agent on the other side actually does?

### 3. x402 MCP Stellar Template — `ffarinas/x402-mcp-stellar-template`

Node.js, Python and Go templates for **paid MCP servers**, mainnet-proven, hackathon winner
(judge score 1.0 — the highest in this list).

Whoever uses this template is publishing a paid MCP tool. That is a skill someone will install, and
the author has a direct interest in being able to say it was audited. Reaching the template author
reaches every builder downstream of it.

**Opening line:** a VERIFIED badge on a paid MCP server is a reason to install it over the other one.

### 4. CredioLabs.AI — crediolabs.ai

Types: **AI + Security**. *"An MCP server and Claude skill for composing smart-account policies."*

**They publish a Claude skill.** That is literally the artefact Sterish audits, and they are already
a security-minded team — they will scrutinise the method rather than accept a badge, which makes
them the most useful sceptic on this list.

**Opening line:** we audit Claude skills for prompt injection and capability overreach. Yours is the
kind we would like to be checked against.

### 5. TollPay — `rajkaria/toll`

Middleware and SDKs for monetizing MCP tools, **on mainnet**. Last commit 18 Apr 2026, so confirm
it is still live before writing.

### 6. Stellar AI Agent Kit — `JoseCToscano/stellar-mcp`

MCP integration and CLI for AI agents on Stellar. Last commit 26 Mar 2026 — oldest here, lowest
priority, but squarely in the right category.

### Deliberately not on this list

**Authors of the 13 catalogue skills we already audited.** Tempting, because we have results for
them — but one of those results is a `DANGEROUS` we ourselves believe is wrong (`cctp`, now
corrected). A first contact that opens with a verdict about someone's work needs the detector to be
settled. Revisit once the STE-37 correction has been live for a while.

## First message

Keep it short. Adapt per target using the opening line above. **Do not send this verbatim to
everyone** — the specific sentence about their project is the reason it gets read.

> Hi — I'm Axel, Stellar Ambassador in Yogyakarta. I'm building Sterish: an on-chain audit registry
> for AI agent skills. A skill gets checked for prompt injection and capability overreach, and the
> verdict is written to Stellar so anyone can verify it without trusting us.
>
> I'm writing because **[one specific sentence about their project — the opening line above]**.
>
> We've already audited all 13 skills in the official skills.stellar.org catalogue. Every verdict is
> on chain with a report whose bytes hash to the on-chain record, so you can recompute it yourself:
> [audit-evidence.md link]
>
> I'd like one real skill of yours audited on testnet — free, takes minutes, and you get a
> transaction you can point at. If the verdict is bad I'll show you exactly which lines caused it.
> If it's good, the skill gets a VERIFIED badge on chain.
>
> Worth 15 minutes?

**Why it is shaped this way**

- **Who I am, once.** Ambassador is real and checkable; it buys a reply, not a commitment.
- **What it does in one sentence**, with the property that matters (*verify without trusting us*).
- **The specific sentence about them** is the part that makes it not spam. If you cannot write one,
  they are the wrong target.
- **Evidence before the ask** — the catalogue audit already exists.
- **The ask is small and reversible**: one skill, testnet, free, minutes.
- **Naming the bad case first** is disarming and it is true. "I'll show you which lines" is a
  promise the product can keep, because the reports name findings with the exact text that triggered
  them.

## Try it in five minutes

Send this only when they say yes. Nobody reads a quickstart before agreeing.

| | |
| -- | -- |
| Registry (chain) | `CCZJN366SV57JEBZVXGYY3ZBLJNFV4IR5ILCAI3EMX2WDNQPEPQ4BRL2` |
| API | `https://api-sterish.jameshub.fun` |
| Check a skill, no wallet | `GET /check/{skill_id}/{version}` — version is required |
| Check bytes you already have | `GET /check/by-hash/{content_hash}` — the primary path |
| Browse what is already audited | `GET /skills` — 24 shown, test namespaces hidden and counted |
| Evidence | `docs/audit-evidence.md` |

A live example to paste, verified working on 17 Sep 2026:

```
GET https://api-sterish.jameshub.fun/check/org.stellar.skills.dapp.react/2026.8.31
```

1. `GET /skills` — see what is there and that it is not a mock.
2. Send us a skill (repo link or the files). We audit it on testnet.
3. You get: a verdict on chain, a report whose `sha256` equals the on-chain `evidence_hash`, and a
   VERIFIED badge if it passes.
4. Recompute the hash yourself. That is the whole point — nothing asks you to trust us.

## When they push back

**"Is this just a linter?"**
No. Findings are anchored on chain with a content hash, so a verdict is attached to *exact bytes*, not
to a name or a version string. Change one byte and it is a different artefact with no verdict — which
is a feature, and it is documented as one.

**"Who audits the auditor?"**
Nobody, today, and that is written down rather than glossed. What we do instead: every report is
published, its bytes hash to the on-chain record, the detector rules are in the repo, and our
false-positive rate is measured and stated (0/16 benign, 0/4 poisoned false negatives). You can
disagree with a verdict and prove your disagreement.

**"What if it flags my skill wrongly?"**
It happened to us, publicly, and we corrected it in the open — `cctp` from the official Stellar
catalogue was flagged `DANGEROUS` by a context-blind rule, we published the verdict *along with our
own written view that it was probably wrong*, then fixed the detector and corrected the chain. The
history is still in `docs/audit-evidence.md`. That is the strongest answer to this question we have,
so use it rather than avoiding it.

**"Is it mainnet?"**
No — testnet, deliberately, while the verdict rules are still moving. Contracts are upgradeable
behind a timelock with a permanent `renounce_upgradeability()` to switch that off once the rules
settle.

**"What does it cost?"**
Nothing during the pilot. The economics exist on testnet (fee + bond escrowed before the audit,
slashed to a reporter if a bad verdict is proven), but no real money is involved.

**"How long does it take?"**
Median 14.6 s per skill. The delivery-plan target was under 5 minutes.

**"I don't want a public DANGEROUS verdict on my work."**
Fair, and worth answering honestly: we will run it and show you the result **before** anything is
published. We only publish with your agreement. The one exception is our own fixtures and the public
catalogue, and that is stated in the evidence doc.

## Tracker

| Date | Target | Channel | Sent | Reply | Outcome |
| -- | -- | -- | -- | -- | -- |
| | | | | | |

Fill a row the moment a message goes out, including the ones that get no reply — a list of five
silent attempts is information. Zero rows is not.

## What counts as done (from STE-30)

One **external** developer or agent really using Sterish on testnet, with clickable evidence. Not a
team member, not a fixture. A transaction anyone can open.
