---
name: Wallet Ledger Inspector
description: A local ledger inspector that declares every capability it holds — wallet, secrets, environment, filesystem and network — so the audit can price the disclosure honestly.
version: 1.0.0
permissions: wallet, secrets, env, fs, network
---

# Wallet Ledger Inspector

Designed to land on **WARNING via policy row 8**: the score falls in the grey band
between `warning_threshold` (40) and `safe_threshold` (70), with **no** injection
findings at all.

How the number is reached, with the shipped defaults:

| step | value |
|---|---|
| declared capabilities | WALLET_ACCESS, SECRET_READ, NETWORK_OUTBOUND (25 each), FILE_WRITE, ENV_READ (10 each), FILE_READ (3) |
| stage 1 deduction | 98 |
| stage 1 score | 2 |
| stage 2 | not applicable — this skill starts no process |
| weighted score | (2 x 40 + 100 x 60) / 100 = **60** |
| policy | 60 >= 40 and 60 < 70 → WARNING, REVIEW (row 8) |

The point of the fixture is that **nothing here is hidden**. The prose says what
the frontmatter says, there is no directive aimed at the agent, and the scanner
finds nothing. WARNING is what an honest declaration of a lot of authority earns:
not an accusation, a request that a human look before granting it.

## Usage

Point it at a local ledger export and ask for a summary by counterparty.

## Limitations

- Local files only.
- It reconciles nothing; the arithmetic is yours to check.
