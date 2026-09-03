# Sterish - Instawards MVP (CLAUDE.md)

Registry audit "skill" AI + USDC escrow di **Stellar/Soroban**. Basis: pemenang ETHGlobal Arc (`ethnyc`).
Design lengkap: **`docs/SYSTEM_DESIGN.md`**. WAJIB dibaca sebelum kerja.

## 🚨 SCOPE (PALING PENTING)
- **HANYA kerjakan tiket yang assign ke AXEL (axelmatsama@gmail.com).** JANGAN pernah kerjakan tiket teammate (James=m.ulinasidiki, Ancung=ancungaulia, Nabil=sharkzneverending).
- **SEBELUM menyentuh tiket apa pun, cek assignee-nya via Linear MCP.** Kalau bukan Axel, SKIP.
- Tiket Axel (Sterish): **STE-5, STE-9, STE-10, STE-11, STE-12, STE-13, STE-14, STE-18, STE-27, STE-30**.
- Kerja HANYA di worktree ini (repo Lin1er/sterish). JANGAN sentuh repo lain (web3-rich, sterun).

## 🚨 STANDING RULE (paling atas, tidak bisa ditawar)
1. **HARAM bertanya ke user / pakai AskUserQuestion.** Ada tension, keputusan, atau ambiguity?
   **Ambil opsi rekomendasi sendiri, putuskan, JALAN.** Jangan berhenti nanya.
   Catat keputusan + alasannya di commit message, comment Linear, dan PR body biar transparan.
   **Satu-satunya titik berhenti = MENUNGGU ACC setelah tiket code-complete + test hijau.**
2. **HARAM mengerjakan tiket yang bukan assign ke Axel** (axelmatsama@gmail.com).
   Cek assignee via Linear MCP DULU. Bukan Axel = SKIP + lapor, jangan disentuh.

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
- **GATE ACC:** kerjakan SATU tiket sampai code-complete + test hijau, LALU **BERHENTI** (jangan merge, jangan mulai tiket berikutnya), update worktree comment diawali `MENUNGGU ACC AXEL:` + ringkas, **tunggu Axel bilang "acc"**.

### Alur merge SETELAH ACC = WAJIB lewat PR (berlaku mulai STE-9)
**JANGAN merge langsung ke main.** Urutan wajib setelah Axel bilang "acc":
1. `git fetch origin --prune` + rebase/merge `origin/main` terbaru ke branch tiket, test hijau lagi.
2. **Push branch tiket** ke origin: `git push -u origin <branch>`.
3. **Buka PR ke main**: `gh pr create --base main --head <branch> --title "STE-#: <ringkas>" --body "..."`.
   Body ringkas WAJIB memuat: fix/fitur yang dibuat, jumlah test hijau, angka coverage, link commit/issue Linear.
   **Mention @Axel + @fable** di body untuk review.
4. **BARU merge PR itu**: `gh pr merge --squash` (atau `--merge` kalau riwayat commit kecil-kecil mau dipertahankan).
5. Update Linear tiket jadi **Done** (flip status, jangan cuma comment) + comment ringkas + link PR.

Kalau `gh` belum ter-auth: **push branch saja**, kasih Axel URL `Compare & PR`
(`https://github.com/Lin1er/sterish/compare/main...<branch>?expand=1`), dan **JANGAN merge sebelum PR ada**.

Tujuan: tiap tiket terdokumentasi sebagai PR yang bisa dilacak.
(Catatan historis: STE-5 terlanjur merge fast-forward langsung ke main sebelum konvensi ini ada — dibiarkan.)

### Bukti deploy (STE-13 dst) — WAJIB dicatat di DUA tempat
Setelah deploy apa pun, catat **SEMUA contract address (CA)** + link [stellar.expert](https://stellar.expert) di:
1. **Comment Linear** tiket deploy-nya, DAN
2. **`docs/deployments.md`** (network, tanggal, CA tiap kontrak, tx hash penting, alamat USDC SAC, alamat admin/auditor **publik saja**).

Jangan cuma salah satu. Secret key TIDAK boleh ikut — lihat "Secret & wallet key" di atas.
- Update CLAUDE.md ini kalau ada keputusan/konvensi baru.
