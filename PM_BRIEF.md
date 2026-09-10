# PM BRIEF - Sterish MVP build (Axel tickets only)

You are the PM/orchestrator, model **Opus, HIGH effort**. **Do not use fable.** Work
methodically, one ticket at a time, and do not skip testing.

## 0. Read first (MANDATORY)
1. `CLAUDE.md` (root) - scope, decisions, conventions, the ACC gate.
2. `docs/SYSTEM_DESIGN.md` - the Registry/Escrow blueprint, the pipeline, the ethnyc mapping.

## 1. SCOPE (critical)
- **Only tickets assigned to Axel (axelmatsama@gmail.com).** Check the assignee through Linear
  before every ticket. Not Axel means SKIP.
- Axel's tickets: **STE-5, 9, 10, 11, 12, 13, 14, 18, 27, 30**.
- Work only in this worktree
  (`/Users/axelurwawuskaatarubby/orca/workspaces/sterish/worktree-axel-2`). Build **on top of**
  the scaffold, not from scratch.

## 2. Linear (Sterish workspace)
- Load: `ToolSearch "select:mcp__claude_ai_Linear__get_issue,mcp__claude_ai_Linear__list_issues,mcp__claude_ai_Linear__save_issue"`.
- Project "Sterish Instawards MVP". Read each ticket's description in full (Requirements / Not
  in this / Left to the owner / Tasks).

## 3. Build order (Axel's tickets, dependency-aware)
**STE-5** harden Registry -> **STE-9** harden Escrow -> **STE-10** ⭐ freeze the interfaces, the
`content_hash` spec and the verdict JSON -> **STE-11** VERIFIED + licence token (soulbound) ->
**STE-12** tests >80% plus wasm -> **STE-13** deploy to testnet, wire the USDC SAC, settle and
slash on chain -> **STE-14** LLM audit stages -> **STE-18** ⭐ the seed run (also needs James's
STE-15/16) -> **STE-27** ⭐ end-to-end -> **STE-30** ⭐⭐⭐ adoption (human work, later).

If one of Axel's tickets is blocked by a teammate's (for instance STE-18 needing James's
STE-15/16), STOP there and report to Axel; do NOT work the teammate's ticket.

## 4. START with STE-5 (harden Registry)
The `contracts/registry` scaffold exists but has gaps (read the ticket and the design):
`register_skill` has no owner auth, there is NO `lookup_by_hash` (content-hash pinning is the
central claim), there are zero events, no typed errors, no TTL, and `SkillIndex` sits in
instance storage. Fix them per the STE-5 requirements and the design. Verify the patterns
through MCP Raven and the Soroban skill.

## 5. Tooling and testing, every ticket
- **MCP Stellar Raven is mandatory**, plus the **Stellar Soroban skill**.
- End-to-end tests (edge, positive, negative); contracts need `cargo llvm-cov` >80%.
- Spawn **Opus** workers (high effort) through the Agent tool for implementation; you plan and
  review.

## 6. THE ACC GATE (per ticket)
- A new branch per ticket (named from the ticket description, based on main). Small commits,
  each referencing STE-#.
- Take ONE ticket to code-complete with green tests. Then **STOP COMPLETELY**: do not merge, do
  not start the next ticket. Update the worktree comment to begin with
  `MENUNGGU ACC AXEL: <short STE-# summary>`. Wait for Axel to say "acc".
- After ACC (from Axel, via the terminal): merge to main, push, **flip the Linear ticket to
  Done** (actually change the status, not just comment), and leave a short comment. Then wait
  for ACC again before the next ticket.

To begin: read `CLAUDE.md`, `SYSTEM_DESIGN.md` and ticket STE-5, verify through Raven, create
the branch, spawn an Opus worker, harden the Registry, and test. Report when STE-5 is
code-complete and awaiting ACC.
