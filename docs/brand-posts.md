# X post drafts — @sterishxyz

Drafts, not a schedule. **Per Axel: the introduction post ships after everything is
deployed**, so that the first thing a visitor clicks actually works. Nothing here is
published until then.

Voice rules are in `docs/brand.md` §8. The two that matter most:

- **No "official app store"**, no phrasing implying Stellar endorsement or an exclusive
  role. Sterish is a registry with an audit pipeline.
- **No dates and no promises.** Per STE-7, the introduction post says what Sterish is,
  not when something will land.

One more, specific to this product: **never state or imply that an unaudited skill is
unsafe, or that an audited one is guaranteed safe.** The audit reports findings against a
specific version's bytes. Overclaiming it is the fastest way to lose the only thing
Sterish is selling.

Character counts below are for the free 280-character limit and were counted, not
estimated.

---

## A. Introduction post — recommended

> AI agents install skills the way we once installed browser extensions: by trusting the
> name.
>
> Sterish is an audit registry for agent skills on Stellar. Each version is audited, the
> verdict goes on chain, and anyone can check it before installing.
>
> Instawards by @StellarOrg.

**274 characters.** Opens with the problem rather than the product, which is what makes a
stranger read the second line. "Each version is audited" is doing real work: it is the honest
form of the claim, because the audit binds to a version's bytes, not to a name.

---

## B. Introduction post — shorter alternative

> Your agent installs a skill. Who checked it?
>
> Sterish audits agent skills and writes the verdict on chain, so anyone can check a
> specific version before installing it — not the publisher's word for it.
>
> Instawards by @StellarOrg.

**229 characters.** Sharper hook, less explanation. Use this one if the post ships with an
image or video that carries the explanation instead.

---

## C. Thread opener (for STE-29, after the demo exists)

> 1/ We built Sterish because "this skill is safe" is currently a claim with nothing
> behind it.
>
> Here is the whole loop: register a skill → audit it → verdict on chain → pay in USDC →
> use it. Testnet, real transactions.

**217 characters.** Opens the launch thread. STE-29 owns the rest of the thread; this is
here so the opener's voice matches the introduction post.

---

## Assets to attach

| Post | Asset |
|---|---|
| Profile picture | `frontend/public/brand/logo/sterish-avatar-navy-tight-1024.png` |
| Header | `frontend/public/brand/logo/sterish-header-navy-1500x500.png` |
| Any post image | cream lockup on navy — never the cream lockup on white |

---

## Verified, 20 Sep 2026

Checked against MCP Stellar Raven before any of this ships. Full record:
`docs/evidence/ste-7-raven-positioning-2026-09-20.json`.

- **"audit registry" is accurate and unoccupied.** Stellar's security projects audit smart
  contracts; its agent-skill projects do not audit. Nobody spans both.
- **"x402" is correct usage**, documented by Stellar at
  `developers.stellar.org/docs/build/agentic-payments/x402`. Note it sits beside **MPP** in
  those docs — we use x402, so do not use the two names interchangeably.
- **⚠️ "Instawards" may be misspelled.** The SDF programme appears as **InstAward /
  InstAwards** (capital A) in two dated sources. Axel specified the current string and the
  bio is already live, so it is unchanged here — **confirm before posting**, since all
  three drafts end with that line.

## Before publishing

- [ ] The dashboard URL in the profile resolves publicly (blocked on STE-26).
- [ ] The demo video exists, if the post references it (STE-28).
- [ ] Re-read for accidental absolutes: "safe", "guaranteed", "official", "verified by
      Stellar". None of those are claims Sterish can make.
- [ ] **Axel has confirmed the InstAward / Instawards spelling** (see above).
- [ ] Axel has seen the final text.
