# Sterish - Instawards MVP (CLAUDE.md)

Registry audit "skill" AI + USDC escrow di **Stellar/Soroban**. Basis: pemenang ETHGlobal Arc (`ethnyc`).
Design lengkap: **`docs/SYSTEM_DESIGN.md`**. WAJIB dibaca sebelum kerja.

## 🚨 SCOPE (PALING PENTING)
- **HANYA kerjakan tiket yang assign ke AXEL (axelmatsama@gmail.com).** JANGAN pernah kerjakan tiket teammate (James=m.ulinasidiki, Ancung=ancungaulia, Nabil=sharkzneverending).
- **SEBELUM menyentuh tiket apa pun, cek assignee-nya via Linear MCP.** Kalau bukan Axel, SKIP.
- Tiket Axel (Sterish): **STE-5, STE-9, STE-10, STE-11, STE-12, STE-13, STE-14, STE-18, STE-27, STE-30**.
- Kerja HANYA di worktree ini (repo Lin1er/sterish). JANGAN sentuh repo lain (web3-rich, sterun).

## Model & effort
- PM + worker = **Opus, effort TINGGI (high/xhigh)**. **JANGAN pakai fable** (boros token).

## Bangun DI ATAS scaffold (bukan dari nol)
Scaffold Lin1er/sterish udah ada: `contracts/registry` + `contracts/escrow` (~80% D1), `pipeline/` (3-stage + poisoned fixture), `api/` (FastAPI, masih mock), `dashboard/` (Next.js skeleton), `docs/`. Tiket = **finish/harden/deploy/buktikan**, bukan tulis ulang. Tiap tiket tandai apa yang sudah ada vs kurang.

## Keputusan FINAL
- Asset bayar = **USDC SAC testnet resmi** via `@x402/stellar` (BUKAN issue asset sendiri).
- Verdict enum 4 nilai (Unaudited/Safe/Dangerous/Warning) + gate: **poisoned WAJIB Dangerous**, cuma **Safe** yang mint VERIFIED.
- Token VERIFIED + license = **soulbound** (non-transferable, tanpa export transfer).
- **Upgrade soroban-sdk** ke stabil terbaru + `wasm32v1-none` (scaffold di 22.0.0).
- **LLM key = punya Axel**. Stage 2 = analisis statis declared-vs-actual (bukan Docker penuh).

## Tooling WAJIB
- **MCP Stellar Raven** (`mcp__stellar-raven__search`/`execute` via ToolSearch) — verifikasi tiap keputusan Stellar/Soroban (Registry/Escrow pattern, SEP-41/SAC USDC, x402, state archival/TTL, OZ non-fungible soulbound).
- **Skill Stellar Soroban** (stellar-dev smart-contracts).

## Testing (WAJIB, no bug)
- e2e + edge + positive + negative tiap tiket. Kontrak: `cargo llvm-cov` **>80%**, semua revert/guard path.

## Sync dengan origin/main (WAJIB, tim kerja paralel)
Teammate (James, Ancung, Nabil) push ke `main` terus, jadi **SEBELUM mulai tiap tiket**:
1. `git fetch origin --prune`
2. Sync ke `origin/main` TERBARU (`git merge --ff-only origin/main` / rebase kalau ada commit lokal).
3. **Base branch tiket dari `origin/main` terbaru**, JANGAN dari branch lama/stale.
4. Cek PR/push terbaru: `gh pr list --state all`, `git log --oneline origin/main -10`.

**SEBELUM merge** tiket: `git fetch origin` lagi + rebase/merge `origin/main` terbaru ke branch tiket, resolve konflik, test hijau lagi, BARU merge.

## Secret & wallet key (deploy testnet, mis. STE-13)
SEMUA wallet/identity key yang dipakai deploy WAJIB disimpan di **`.env` di root repo** biar kesimpen + bisa diakses ulang.
Urutan WAJIB, jangan dibalik:
1. **Pastikan `.env` sudah ada di `.gitignore` DULU** sebelum menulis secret apa pun (sudah: `.env`, `.env.keys`, `.stellar/`, `.soroban/`).
2. `chmod 600 .env` (dan `chmod 600` file secret lain).
3. Format per identity: `<NAME>_ADDRESS=G...` + `<NAME>_SECRET=S...` (mis. `DEPLOYER_ADDRESS` / `DEPLOYER_SECRET`, `AUDITOR_ADDRESS` / `AUDITOR_SECRET`).
4. Header file wajib berisi warning: `# TESTNET ONLY - JANGAN COMMIT - JANGAN REUSE KEY MAINNET`.

**JANGAN PERNAH** print secret ke stdout/log/terminal/laporan/Linear/PR — tulis LANGSUNG ke file (`stellar keys ... >> .env`, heredoc, atau `python3` write), jangan lewat `echo` yang isinya secret.
Yang boleh dilaporkan/di-commit cuma **public address (G...)** dan **contract address (C...)**. Bukti deploy tetap di `docs/deployments.md`.

## Git & workflow (ACC GATE per tiket)
- **Branch baru per tiket** (nama dari deskripsi tiket, base main).
- **Commit kecil-kecil**, pesan rujuk STE-#.
- **GATE ACC:** kerjakan SATU tiket sampai code-complete + test hijau, LALU **BERHENTI** (jangan merge, jangan mulai tiket berikutnya), update worktree comment diawali `MENUNGGU ACC AXEL:` + ringkas, **tunggu Axel bilang "acc"**. Baru setelah ACC: merge ke main + update Linear tiket jadi **Done** (jangan lupa flip status) + comment.
- Deploy WAJIB bukti (CA + stellar.expert / URL) di `docs/deployments.md`.
- Update CLAUDE.md ini kalau ada keputusan/konvensi baru.
