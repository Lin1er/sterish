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

## Git & workflow (ACC GATE per tiket)
- **Branch baru per tiket** (nama dari deskripsi tiket, base main).
- **Commit kecil-kecil**, pesan rujuk STE-#.
- **GATE ACC:** kerjakan SATU tiket sampai code-complete + test hijau, LALU **BERHENTI** (jangan merge, jangan mulai tiket berikutnya), update worktree comment diawali `MENUNGGU ACC AXEL:` + ringkas, **tunggu Axel bilang "acc"**. Baru setelah ACC: merge ke main + update Linear tiket jadi **Done** (jangan lupa flip status) + comment.
- Deploy WAJIB bukti (CA + stellar.expert / URL) di `docs/deployments.md`.
- Update CLAUDE.md ini kalau ada keputusan/konvensi baru.
