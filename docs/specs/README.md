# Sterish — Frozen Specs

Kontrak handoff antar-owner. Setelah dokumen di folder ini merged, James dan Ancung bisa
membangun paralel tanpa menunggu implementasi selesai penuh — selama semua pihak patuh
pada isi folder ini.

**Status: FROZEN v1.1.0** (STE-11, 2026-09-03).

---

## Isi

| Dokumen | Apa yang dibekukan | Dipakai oleh |
|---|---|---|
| [`content-hash.md`](content-hash.md) | Canonical bytes v1 + `content_hash = sha256(...)`, byte-exact | pipeline (intake), kontrak (`lookup_by_hash`), dashboard (check-before-install) |
| [`interfaces.md`](interfaces.md) | Seluruh function signature publik Registry + Escrow + Tokens | semua |
| [`events.md`](events.md) | Seluruh layout `#[contractevent]` termasuk field yang jadi topic (10 event) | indexer, API, dashboard |
| [`verdict-json.md`](verdict-json.md) + [`verdict.schema.json`](verdict.schema.json) | Skema verdict JSON output pipeline | stage 3, on-chain submitter, API, dashboard |
| [`../api-spec.md`](../api-spec.md) | Bentuk response API termasuk check by `content_hash` + evidence links | dashboard, agen pemanggil |
| [`vectors/`](vectors/) | Test vectors `content_hash` (+ error cases) | ketiga implementasi |
| [`reference/`](reference/) | Implementasi referensi `content_hash` (Python + TypeScript) | pipeline, dashboard |
| [`examples/`](examples/) | Contoh verdict JSON valid + invalid | stage 3, submitter, API |

Sisi Rust hidup sebagai test di `contracts/registry/src/test.rs` dan meng-hash lewat
`env.crypto().sha256()` — host function yang sama dengan kontrak ter-deploy.

---

## Cara memverifikasi (siapa pun, tanpa izin khusus)

```bash
make verify-spec
# atau satu per satu:
bash scripts/verify-content-hash.sh    # hash identik di Python + TypeScript + Rust
bash scripts/verify-verdict-json.sh    # contoh verdict lolos/ditolak sesuai skema
bash scripts/verify-soulbound.sh       # contract spec tokens tidak punya transfer/approve/burn
```

Runner menjalankan **tiga** implementasi (Python, TypeScript, Rust), mem-`diff` laporannya
byte-for-byte, lalu memeriksa relasi antar-vector. Exit code ≠ 0 kalau ada satu saja yang
menyimpang. Runner ini sudah diuji negatif: mengubah 1 byte di fixture atau mengedit tangan
`expected_sha256` membuatnya gagal.

> **Bukti reproduksibilitas pihak ketiga.** Selain tiga implementasi di repo ini, PM menulis
> implementasi keempat dari nol — hanya bermodal teks `content-hash.md`, tanpa melihat
> `reference/` — dan mendapat kedelapan hash yang identik. Kalau spec-nya ambigu, itu tidak
> mungkin terjadi.

---

## Aturan perubahan (WAJIB)

Spec di folder ini **frozen**. Perubahan apa pun pada interface, event layout, `content_hash`,
skema verdict JSON, atau bentuk response API:

1. **Lewat PR baru**, tidak boleh langsung ke `main`.
2. **Di-approve Axel (PM) + fable (AI co-PM)** — dua-duanya, bukan salah satu.
3. **Tercatat di changelog** di bawah, dengan tanggal, PR, dan alasannya.
4. **Beri tahu owner yang terdampak** (James: pipeline/API/indexer; Ancung: dashboard)
   sebelum merge, bukan sesudah.

### Aturan versi

- `content_hash`: algoritmanya **immutable**. Perubahan aturan canonicalization = algoritma
  **baru** (`sterish-content-hash/v2\n` sebagai MAGIC), bukan edit terhadap v1. Hash lama harus
  tetap bisa dihitung ulang selamanya, kalau tidak setiap verdict yang sudah tertulis on-chain
  jadi tidak terverifikasi.
- **Kode error kontrak** (`RegistryError` 1–9, `EscrowError` 1–9, `TokenError` 1–6) adalah ABI publik.
  Boleh **menambah** varian di nomor berikutnya; **tidak boleh** me-renumber atau menghapus.
- **Event**: menambah event baru = additive, aman. Mengubah field/topic event yang sudah ada =
  breaking, wajib lewat aturan di atas.

---

## Changelog

### v1.1.0 — 2026-09-03 (STE-11, PR TBD)

Aditif. Tidak ada bentuk v1.0.0 yang berubah.

- **§5 `interfaces.md` naik dari `PLANNED` ke FROZEN**: kontrak `sterish_tokens` (badge VERIFIED
  + license token, keduanya soulbound) sekarang punya ABI hasil generate, tabel fungsi,
  invariant T1–T7, dan kode error publik `TokenError` 1–6.
- **`events.md` §3b**: dua event baru `verified_minted` dan `license_minted` + baris emission order.
- Tiga open question di §5.3 lama sudah dijawab dan dicatat di §5.5: license terikat
  `(skill_id, version)` (bukan `content_hash`), royalties **di-drop** (tidak ada resale di token
  soulbound), dan `mint_license` dipanggil `MinterRole` tunggal yang bisa dirotasi admin.

Keputusan yang berbeda dari teks tiket STE-11, beserta alasannya:

- **Tanpa OpenZeppelin.** `stellar-tokens` 0.7.2 butuh `soroban-sdk ^26.1.0` sementara workspace
  frozen di `27.0.6` — cargo meresolusi dua salinan SDK yang tidak kompatibel. Terlepas dari itu,
  modul `non_fungible` OZ 0.7.2 **tidak punya dukungan soulbound**: meng-`contractimpl` trait
  `NonFungibleToken` justru meng-export `transfer`/`approve` yang dilarang tiket. Kontrak custom
  adalah satu-satunya cara memenuhi stack frozen DAN done-criteria soulbound sekaligus.
- **`mint_verified(skill_id, version, owner)`** menerima `owner` sebagai parameter, tidak membacanya
  dari Registry — membacanya menuntut duplikasi struct `SkillEntry` di crate tokens, yang menciptakan
  drift terhadap ABI frozen. Verdict `Safe` tetap dicek on-chain, dan itu bagian yang penting.
- **`mint_license` mengecek Registry live**, bukan cuma badge lokal. Badge adalah snapshot saat mint
  dan tidak bisa di-burn (soulbound), jadi tanpa cek ini versi yang di-re-audit `Dangerous` masih
  bisa terus menjual lisensi lewat badge basi. Lisensi yang sudah terjual tetap sah.
- **`TokenError::NotAuthorized` dibuang** sebelum freeze (varian mati — semua role check gagal lewat
  `require_auth()` sebagai host error). Setelah freeze ini kode error jadi ABI publik.

Batasan yang diketahui dan sengaja dibiarkan:

- **Badge tidak bisa dicabut** (invariant T7). Tanpa `burn`, `is_verified_token` bisa tetap `true`
  setelah versi di-re-audit `Dangerous`. Konsumen yang butuh jawaban live WAJIB baca
  `SkillRegistry::is_verified`. Jalur yang berbahaya — penjualan lisensi baru — sudah ditutup.


### v1.0.0 — 2026-09-03 (STE-10, PR TBD)

Pembekuan awal. Dibangun di atas kontrak yang sudah merged: STE-5 (Registry) dan STE-9 (Escrow).

Keputusan yang diambil di luar/berbeda dari rekomendasi tiket, beserta alasannya:

- **Tidak ada kanonikalisasi JSON.** Tiket merekomendasikan "manifest JSON ter-normalisasi
  (sorted keys)". Ditolak: kanonikalisasi JSON lintas Rust/Python/TypeScript (format float,
  urutan key, escaping, integer besar) justru sumber drift yang lebih besar daripada masalah
  yang diselesaikannya. `manifest.json` diperlakukan sebagai byte biasa seperti file lain.
- **Urutan file = bytewise pada path UTF-8**, bukan perbandingan string. Alasannya
  `Array.prototype.sort()` di JavaScript mengurutkan berdasarkan UTF-16 code unit, yang berbeda
  untuk karakter non-BMP. Vector `non-bmp-path-order` ada khusus untuk menangkap kesalahan ini.
- **Length-prefix `u32be` pada path dan konten**, supaya `("ab","c")` dan `("a","bc")` tidak
  pernah menghasilkan byte stream yang sama. Vector `concat-ambiguity-a/b` membuktikannya.
- **Normalisasi hanya CRLF→LF + strip trailing newline.** Tidak ada trim per-baris, tidak ada
  normalisasi Unicode. Setiap normalisasi tambahan memperbesar permukaan tempat perubahan bisa
  disembunyikan; CRLF dan trailing newline tidak bisa membawa payload berbahaya.
- **File wajib UTF-8 valid**; file biner ditolak (`NotUtf8`). Batasan v1 yang diketahui —
  skill dengan aset biner butuh v2.
- **Backslash ditolak dalam path.** Sebenarnya legal di POSIX, ditolak sengaja supaya
  `tools\zeta.py` dari packager Windows tidak diam-diam terbaca sebagai satu nama file.
- **Verdict JSON mendapat 3 field identitas** di luar daftar tiket: `skill_id`, `version`,
  `content_hash`. Tanpa itu on-chain submitter tidak tahu record mana yang harus ditulis.
- **8 test vector**, tiket meminta minimal 3.

Batasan yang diketahui dan sengaja dibiarkan:

- Daftar exclusion (`.git/**`, `node_modules/**`, dst.) baru hidup di implementasi referensi.
  Pipeline (STE-13) **wajib memakai `hash_dir()` dari `reference/content_hash.py`**, bukan
  menulis packager sendiri — kalau tidak, drift-nya kembali lewat pintu belakang.
- Interface token VERIFIED/license ditandai `STATUS: PLANNED`, belum frozen; menyusul di STE-11.
