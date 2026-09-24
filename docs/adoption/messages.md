# Outreach messages, as sent (STE-51)

The exact text of every first contact, kept so that a reply can be read against what was
actually said and so the next message can be written from what worked rather than from memory.

The targets, the opener and the objection answers live in `README.md`; this file holds only
the finished messages. Log the send in the tracker there the moment it goes out.

**Sender: Nabil, from his personal X account.** Not @sterishxyz, which has no posts yet: the
first thing a recipient does is open the sender's profile, and an empty account reads as a
bot. The credibility here comes from the links, which resolve and can be checked, not from
the account. Axel stays the one who picks up whatever comes back (STE-51: "you open the door,
he walks through it").

**No em dashes, no en dashes, no non-ASCII at all.** These are pasted into a DM box; anything
exotic risks rendering as a replacement character in the recipient's client.

---

## 1. RouteDock — Tim (`winsznx`)

**Channel:** Twitter DM to [@winsznx](https://twitter.com/winsznx)
**Status:** drafted 24 Sep 2026, not yet sent
**Why first:** the only target that is both active (last push 21 Sep 2026) and has an open
public channel. Building on x402, which is the rail Sterish licences already run on.

```
Hi Tim, RouteDock came up while I was mapping who is building agent
payments on Stellar. Putting x402, MPP charge and MPP session behind one
client.pay() is the part most people underestimate.

We have been building the other half. Sterish audits agent skills and
writes the verdict on chain, pinned to the hash of the files it read.
All 13 skills in the official skills.stellar.org catalogue are audited
already and the results are on chain. Nothing to sign up for:

https://app.sterish.xyz

Why it might matter to you: RouteDock routes the payment, but nothing
today tells the agent whether the skill on the other side was poisoned
before it ran. CVE-2025-54136 is the live example. Approval was bound to
a name, so swapping the payload needed no new prompt.

No ask, and nothing to integrate. If it is useful it is there, and if you
think we have got something wrong I would rather hear that.
```

896 characters.

**What is doing the work, so an edit does not remove it by accident:**

- The first sentence names `client.pay()` and the three payment paths it wraps. That is what
  separates this from a template: it shows the repo was actually opened.
- The claim is a number that can be checked (13, the official catalogue, on chain), not
  "we have audited many skills".
- It gives before it asks. The audit already exists; nothing is being requested.
- The close asks for nothing at all, and invites the reader to say we are wrong. A message
  that does not spend the recipient's time is likelier to get a reply, and developers answer
  an invitation to criticise more readily than a pitch.

**Claims in this message, and where they were verified**

| Claim | Verified against |
|---|---|
| 13 skills in the official catalogue, audited, on chain | `docs/audit-evidence.md`; live API 24 Sep 2026 |
| CVE-2025-54136, approval bound to a name | Published advisory; `docs/evidence/ste-23-landing-claims-2026-09-20.json` |
| `https://app.sterish.xyz` resolves | HTTP 200, 24 Sep 2026 |

**Before sending:** open `https://app.sterish.xyz` on a phone, not just a laptop. A dead link
is the one mistake a first message cannot take back.

---

## 2. TollPay — Raj Karia (`rajkaria`)

**Channel:** Twitter DM to [@rajkaria_](https://twitter.com/rajkaria_)
**Status:** not drafted
**Check first:** the repo has not been pushed to since 18 April 2026, five months. STE-51
says to confirm a target is still alive before writing. A quiet repo does not mean a quiet
person, so check whether the account is still active; if both are quiet, skip and replace the
target rather than spending a message on it.

Send this at least a day after RouteDock. One at a time is the rule, and two messages in one
evening reads as a campaign.

---

## Targets with no reachable channel

Checked 20 and 24 September 2026. Recorded here so nobody re-does the search and concludes
they were skipped out of laziness.

| Target | What was checked | Result |
|---|---|---|
| **CleverCon** | GitHub Discussions, lead's profile, org profile, dashboard site | Discussions disabled; no Twitter, email or site anywhere; dashboard page carries only the product name |
| **x402 MCP Stellar Template** | `ffarinas` GitHub profile | Empty. No links of any kind |
| **CredioLabs.AI** | `crediolabs.ai` | No email, form, social account or GitHub org on the page |

CleverCon is the painful one: it is the most active repo on the list (last push 22 Sep 2026)
and the angle for it is already written in STE-51. The only remaining route is a GitHub issue,
which STE-51 forbids, and for a good reason: it is permanent, public, reads as spam, and
attaches to Axel's name as a Stellar Ambassador.

**Consequence, which needs a decision from Axel:** the ticket asks for at least four targets
contacted. Two are reachable. Either the list grows, with "has a public contact channel" as a
condition this time, or the target of four does not survive contact with reality.
