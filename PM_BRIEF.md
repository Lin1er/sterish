# PM BRIEF - Sterish MVP build (Axel tickets only)

Kamu PM/orchestrator, model **Opus, effort TINGGI**. **JANGAN pakai fable.** Kerja metodis, satu tiket, jangan skip testing.

## 0. Baca dulu (WAJIB)
1. `CLAUDE.md` (root) - scope, keputusan, konvensi, GATE ACC.
2. `docs/SYSTEM_DESIGN.md` - blueprint Registry/Escrow, pipeline, mapping ethnyc.

## 1. SCOPE (kritis)
- **HANYA tiket assign ke Axel (axelmatsama@gmail.com).** Cek assignee via Linear MCP sebelum tiap tiket. Bukan Axel = SKIP.
- Tiket Axel: **STE-5, 9, 10, 11, 12, 13, 14, 18, 27, 30**.
- Kerja HANYA di worktree ini (`/Users/axelurwawuskaatarubby/orca/workspaces/sterish/worktree-axel-2`). Bangun DI ATAS scaffold, bukan dari nol.

## 2. Linear (Sterish workspace)
- Muat: `ToolSearch "select:mcp__claude_ai_Linear__get_issue,mcp__claude_ai_Linear__list_issues,mcp__claude_ai_Linear__save_issue"`.
- Project "Sterish Instawards MVP". Baca deskripsi tiap tiket (Requirements/Not in this/Left/Tasks lengkap).

## 3. Urutan build (tiket Axel, dependency-aware)
**STE-5** Harden Registry -> **STE-9** Harden Escrow -> **STE-10** ⭐ Freeze interface+spec content_hash+verdict JSON -> **STE-11** VERIFIED+license token (soulbound) -> **STE-12** tests >80% + wasm -> **STE-13** Deploy testnet + wiring USDC SAC + settle/slash on-chain -> **STE-14** LLM audit stages -> **STE-18** ⭐ seed run (butuh STE-15/16 James juga) -> **STE-27** ⭐ E2E -> **STE-30** ⭐⭐⭐ adopsi (kerja manusia, nanti).

Kalau tiket Axel keblok tiket teammate (mis. STE-18 butuh STE-15/16 James), STOP di situ + lapor Axel; JANGAN kerjain tiket teammate.

## 4. MULAI dari STE-5 (Harden Registry)
Scaffold `contracts/registry` udah ada tapi ada celah (baca ticket + design): `register_skill` tanpa auth owner, TIDAK ada `lookup_by_hash` (content-hash pinning = klaim inti), nol events/typed errors/TTL, `SkillIndex` di instance storage. Perbaiki sesuai Requirements STE-5 + design. Verifikasi pola via MCP Raven + skill Soroban.

## 5. Tooling + testing tiap tiket
- **MCP Stellar Raven wajib** + **skill Stellar Soroban**.
- Test e2e (edge/positive/negative), kontrak `cargo llvm-cov` >80%.
- Spawn worker **Opus** (effort tinggi) via Agent tool untuk implementasi; kamu plan + review.

## 6. GATE ACC (per tiket)
- Branch baru per tiket (nama dari deskripsi tiket, base main). Commit kecil-kecil (rujuk STE-#).
- Kerjakan SATU tiket sampai code-complete + test hijau. LALU **BERHENTI TOTAL**: jangan merge, jangan mulai tiket berikutnya. Update worktree comment jadi diawali `MENUNGGU ACC AXEL: <ringkas STE-#>`. Tunggu Axel bilang "acc".
- Setelah ACC (dari Axel via terminal): merge ke main + push + **update Linear tiket jadi Done** (jangan lupa flip status) + comment ringkas. Lalu tunggu ACC lagi untuk tiket berikutnya.

Mulai: baca CLAUDE.md + SYSTEM_DESIGN + ticket STE-5, verifikasi via Raven, bikin branch, spawn worker Opus, harden Registry, test. Lapor pas STE-5 code-complete + MENUNGGU ACC.
