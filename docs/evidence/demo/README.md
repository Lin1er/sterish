# Deliverable 3 — demo video and flow screenshots

Recorded **28 September 2026** against the live stack: `api.sterish.xyz`, `app.sterish.xyz`,
`sterish.xyz` and Stellar testnet. STE-58.

- **Video:** [`sterish-demo.mp4`](sterish-demo.mp4) — 2 min 52 s, 1920×1080, narrated.
  Also served at <https://sterish.xyz/demo.mp4>.
- **Screenshots:** [`screenshots/`](screenshots) — nine full-page captures at 2× scale.
- **Raw terminal recordings:** [`terminal-session.cast`](terminal-session.cast) and
  [`terminal-api.cast`](terminal-api.cast), replayable with `asciinema play`.

## What is real, and what was added

Everything on screen happened during the take. The skills were registered, audited and bought
while recording, and the hashes in the frames are the hashes the network returned. Nothing is
re-enacted, mocked or pointed at a fixture server.

Four things were added in the edit, and nothing else: the **typing animation** of each command
before it runs, the **caption strip** at the bottom, the **title, escrow and closing cards**, and
the **narration**. Idle gaps in the terminal were trimmed to 1.2 s, so the loop looks faster than it
was — the real durations are in the `.cast` files, which carry a timestamp per event. An audit takes
about 22 seconds end to end; the video shows it in ten.

**The voice is synthetic**, generated with Piper (`en_US-ryan-high`) from
[`narration.json`](narration.json), which holds the script word for word. Nobody in the team
recorded it, and it is said here rather than left for someone to wonder about. Where a scene's
narration runs longer than its footage, the last frame is held rather than the sentence cut, which
is why the poisoned refusal and the 401 sit on screen for several seconds.

Motion and transitions are added too, and none of it changes what is on screen — it exists because
a static screencast is hard to watch for three minutes. The cards are rendered as animated frame
sequences rather than stills: headlines and rows slide in one at a time, and the figures on the
closing card count up to their real values. The footage drifts a few pixels so no shot is frozen,
every cut uses a different transition, and a progress line runs along the bottom edge.

## The transactions in the video

The take registered one safe skill and one poisoned skill, then bought the safe one. Every hash
below was checked against Horizon after the recording: **7 of 7 successful**.

| Step | Transaction | Ledger |
|---|---|---|
| Register the safe skill | [`64e88aa3…`](https://stellar.expert/explorer/testnet/tx/64e88aa392d833993b534a6f7bb57f3ca0580ec48742b9bac93a154fa2412e40) | 4916394 |
| Verdict SAFE on chain | [`c95d0424…`](https://stellar.expert/explorer/testnet/tx/c95d0424384615d068b2e2724dec7e1868b4cd77225259db649741d5d15bd827) | 4916395 |
| VERIFIED badge minted | [`1662e721…`](https://stellar.expert/explorer/testnet/tx/1662e721b477a647dcc1759d54f2d6b361667caf7b8fc3d3ce8cad0d8b916e87) | 4916396 |
| x402 settlement, 0.1 USDC | [`f8fab54e…`](https://stellar.expert/explorer/testnet/tx/f8fab54ebbcc40477550f00f2eee4fe06a7a326b88d9c3060f224e7bdfc7995a) | 4916402 |
| Licence minted to the agent | [`1aa1dff3…`](https://stellar.expert/explorer/testnet/tx/1aa1dff32396e353f36bbc03a0ddb5d1f947bbb478d5bc23e2ab2f1517f2e22a) | 4916404 |
| Register the poisoned skill | [`167f5ceb…`](https://stellar.expert/explorer/testnet/tx/167f5cebc17a33e20d3430b8fcf4bcec1e3d94dcdbe266f126daf68ef50a5b12) | 4916408 |
| Verdict DANGEROUS on chain | [`9b4afd44…`](https://stellar.expert/explorer/testnet/tx/9b4afd444ed294e6596860ac60200f5ee5dfbdcf50c2813993aaf8bd5f69e8be) | 4916409 |

Skills: [`com.fixtures.demo.unit-converter-09282125`](https://app.sterish.xyz/skills/com.fixtures.demo.unit-converter-09282125)
(SAFE, trust 100) and [`com.fixtures.demo.pdf-helper-09282125`](https://app.sterish.xyz/skills/com.fixtures.demo.pdf-helper-09282125)
(DANGEROUS, score 10). Buyer:
[`GAKOLIBH…BHFMRD3M`](https://app.sterish.xyz/licences/GAKOLIBHK4OIXTGYQSFVT3735PRJIY7LIYFHB44FX6EKSVEXBHFMRD3M),
a wallet created during `prep` and funded with 0.5 USDC.

## Chapters

| Time | What is on screen | Where to check it |
|---|---|---|
| 0:00 | Title | — |
| 0:07 | The problem: a skill is instructions the model will follow | CVE-2025-54136, CVE-2025-6514 |
| 0:15 | `sterish.xyz`, reading a live verdict | <https://sterish.xyz> |
| 0:28 | Register → three audit stages → SAFE → badge, all on chain | first three transactions above |
| 0:38 | The skill page: content hash, audit transaction, evidence hash | `app.sterish.xyz/skills/…` |
| 0:50 | The same answer as JSON, the way an agent asks for it | `GET /check/{skill_id}/{version}` |
| 1:01 | Published: `check` 200, `use` 402, `report` 200 | `terminal-session.cast` |
| 1:09 | 402 → 0.1 USDC over x402 → licence minted → 200 | settle and mint transactions |
| 1:15 | Naming someone else's address returns 401; the signed request returns 200 | SEP-53 proof, STE-48 |
| 1:18 | The licence as a soulbound token on the ledger | `app.sterish.xyz/licences/…` |
| 1:27 | The audit report behind the verdict, with its evidence hash | `GET /reports/{skill_id}/{version}` |
| 1:38 | The poisoned skill: DANGEROUS, score 10, no badge | poisoned transactions above |
| 1:44 | Buying it is refused with `NOT_VERIFIED` | `GET /use/…` |
| 1:46 | Who pays and who is at risk: fee, bond, settle, slash | `docs/SYSTEM_DESIGN.md` §4 |
| 1:56 | The dashboard shows the same refusal | `app.sterish.xyz/skills/…` |
| 2:07 | The registry, read live from the contract | <https://app.sterish.xyz> |
| 2:20 | The audit feed | `app.sterish.xyz/activity` |
| 2:29 | Check before install, hashing the files in the browser | `app.sterish.xyz/check` |
| 2:36 | The numbers, each one verified the day of the recording | table below |
| 2:47 | Closing | — |

## The numbers on the card at 2:36

Each was re-measured on 28 September, not carried over from an earlier report.

| Measure | Value | How it was checked |
|---|---|---|
| Catalogue skills audited on chain | 13 of 13, all SAFE | `GET /skills?include_test=true`, filtered to `org.stellar.skills.*` |
| Poisoned samples caught | 4 of 4 planted | verdicts of `com.fixtures.poisoned.*` |
| Measured error rate | 0 FP of 16, 0 FN of 4 | `docs/audit-evidence.md` |
| Reports whose bytes match their on-chain hash | 36 of 36 | `uv run python scripts/verify_onchain.py ../reports` |
| Real x402 settlements | 15, every one minted a licence | payments ledger on the production host |
| Full-loop rehearsal | 7 of 7 GREEN, 16 of 16 transactions | `docs/rehearsal/runs/2026-09-27T065414Z/EVIDENCE.md` |

## Screenshots

| File | What it shows |
|---|---|
| `01-landing.png` | The landing page at `sterish.xyz`, with a live registry row |
| `02-registry.png` | The registry browser: every audited version read from the contract |
| `03-skill-safe.png` | A SAFE skill: verdict, trust score, content hash, audit transaction, evidence hash |
| `04-skill-dangerous.png` | A DANGEROUS skill: no badge, and the reason it cannot be licensed |
| `05-licences.png` | The licence minted during the take, token #52, with its mint transaction |
| `06-check.png` | Check before install — the files are hashed in the browser |
| `07-activity.png` | The audit feed, newest first |
| `08-api-check.png` | `GET /check` as an agent sees it |
| `09-api-report.png` | `GET /reports`, with the evidence hash anchored on chain |

## What the video deliberately does not claim

- **Not self-service.** Registration and audit are run by the operator; a developer cannot yet
  submit and pay on their own. The escrow that makes that possible is built and shown, but the
  public submit path is out of scope for this grant (STE-56).
- **No external users.** Every wallet in the video belongs to the team.
- **The model does not decide.** Stage 3 gives notes; the verdict comes from the deterministic
  policy in `pipeline/`, which is why the poisoned sample scores 10 rather than "probably bad".
- **Testnet only.** Every link expires with the testnet reset scheduled for 16 December 2026.

## Reproducing it

```bash
~/sterish-demo/demo.sh prep      # fresh skill ids + a funded agent wallet
~/sterish-demo/demo.sh all       # audit, publish, buy
~/sterish-demo/demo.sh poison    # the negative case
```

The helper lives outside the repo because it writes to the production host. The recording itself
was `asciinema rec --cols 104 --rows 32` over that helper, rendered with `agg`, with the browser
scenes captured by Playwright and the whole thing assembled with ffmpeg.

Each demo run registers permanently on testnet, so ids use the `com.fixtures.demo.*` namespace
the registry conventions require, and each run spends 0.6 USDC of testnet funds.
