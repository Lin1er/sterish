# Sterish `content_hash` — canonical bytes v1

**Status:** FROZEN (STE-10). **Spec id:** `sterish-content-hash/v1`.
**Perubahan apa pun pada dokumen ini = versi baru (`/v2`), bukan edit di tempat.**

`content_hash` adalah identitas byte sebuah skill. Ia dihitung di **tiga tempat**:

| Tempat | Kapan | Implementasi |
|---|---|---|
| Pipeline audit (Python) | saat intake, sebelum Stage 1 | `docs/specs/reference/content_hash.py` |
| Kontrak Registry (Rust/Soroban) | saat `register_skill` / `check_skill` lookup | `env.crypto().sha256()` |
| Dashboard / klien (TypeScript) | saat check-before-install | `docs/specs/reference/contentHash.ts` |

Kalau ketiganya tidak sepakat, `check(skill)` **berbohong**: user meng-install byte
yang berbeda dari byte yang diaudit, sambil melihat badge VERIFIED. Itulah kenapa
tiket ini membekukan algoritmanya sampai level byte dan membuktikannya dengan runner
lintas bahasa, bukan sekadar mendeskripsikannya.

---

## 1. Algoritma

```
CANON = MAGIC
     || u32be(file_count)
     || untuk tiap file, diurut ASC bytewise berdasarkan path_bytes:
            u32be(len(path_bytes))    || path_bytes
            u32be(len(norm_content))  || norm_content

MAGIC        = b"sterish-content-hash/v1\n"      (24 byte, termasuk \n)
content_hash = sha256(CANON)                     (32 byte, 64 hex huruf kecil)
```

`MAGIC` hex: `737465726973682d636f6e74656e742d686173682f76310a`.

`content_hash` selalu direpresentasikan sebagai **64 karakter hex huruf kecil**
di JSON, API, dan dokumen. Di kontrak ia adalah `BytesN<32>` mentah.

### 1.1 Aturan normalisasi (normatif)

1. **`path_bytes`** = UTF-8 dari path file **relatif terhadap root skill**.
   Separator POSIX `/`. Tanpa prefix `./` atau `/`. Tanpa komponen `..`.
2. **Urutan** = ASC **bytewise pada `path_bytes` mentah** — bukan perbandingan
   per-codepoint, bukan locale-aware, bukan urutan UTF-16 code unit.
   - Python: `sorted(files, key=lambda f: f.path_bytes)` (`Ord` untuk `bytes` = bytewise).
   - TypeScript: bandingkan `Uint8Array` byte per byte (`compareBytes`).
     **JANGAN** pakai `Array.prototype.sort()` default pada string — itu urutan
     UTF-16 code unit dan **berbeda** untuk code point non-BMP.
   - Rust: `Ord` bawaan `[u8]` / `Vec<u8>`.
3. **`norm_content`** = byte isi file, dinormalisasi dalam urutan ini:
   a. semua `\r\n` → `\n` (leftmost, non-overlapping);
   b. lalu semua `\r` yang tersisa → `\n`;
   c. lalu **semua** `\n` di akhir file dibuang.
   Tidak ada normalisasi whitespace lain. Tidak ada trim per-baris.
   Tidak ada perubahan encoding.
4. **File harus UTF-8 valid.** Kalau tidak → error eksplisit `NotUtf8`.
   v1 hanya mendukung skill berbasis teks; lihat §5 (batasan yang diketahui).
5. **`u32be`** = unsigned 32-bit big-endian. Length-prefix **wajib** supaya
   `("ab","c")` dan `("a","bc")` tidak pernah menghasilkan byte stream yang sama.
6. **Path duplikat → error `DuplicatePath`. Set file kosong → error `EmptyFileSet`.**
7. `file_count` dan setiap panjang harus muat di u32. Skill dengan >4 GiB satu file,
   atau >2^32-1 file, ditolak.

### 1.2 Validasi path (normatif)

Path ditolak dengan `InvalidPath` jika salah satu berlaku:

| Kondisi | Contoh |
|---|---|
| path kosong | `""` |
| bukan UTF-8 valid | — |
| mengandung `\` | `tools\zeta.py` |
| mengandung byte NUL | — |
| ada komponen kosong (leading/trailing/double slash) | `/SKILL.md`, `a//b`, `a/` |
| ada komponen `.` | `./SKILL.md`, `a/./b` |
| ada komponen `..` | `../SKILL.md` |

> **Catatan penyimpangan dari teks tiket.** Spec PM menyebut "tanpa prefix `./` atau `/`,
> tanpa komponen `..`". Implementasi memperluas ini menjadi larangan **komponen** `.`
> dan `..` di posisi mana pun, larangan komponen kosong, dan larangan backslash.
> Backslash secara teknis legal di nama file POSIX; ia ditolak dengan sengaja supaya
> path gaya Windows (`tools\zeta.py`) tidak diam-diam menjadi *satu* nama file dan
> menghasilkan `content_hash` yang berbeda dari packager di OS lain.
> Ini pengetatan, bukan pelonggaran: tidak ada input yang sebelumnya valid menjadi hash berbeda.

### 1.3 File yang dikecualikan

Dikecualikan oleh **packager sebelum hashing** — bukan bagian dari algoritma hash:

```
.git/**   node_modules/**   __pycache__/**   .venv/**   target/**   .DS_Store   *.pyc
```

Nama direktori dicocokkan di kedalaman mana pun. `*.pyc` dicocokkan pada nama file.
**Set file final yang ikut di-hash dicatat eksplisit di tiap test vector**
(field `files_note` di `content-hash-vectors.json`).

---

## 2. Worked example — vector `single-file`

Input: satu file, path `SKILL.md`, isi mentah
`"# Example Skill\n\nDoes nothing harmful.\nEnd.\n"` (43 byte).

Normalisasi membuang `\n` terakhir → `norm_content` 43 − 1 = **42** byte (`0x2b`).

```
00000000  73 74 65 72 69 73 68 2d 63 6f 6e 74 65 6e 74 2d  |sterish-content-|
00000010  68 61 73 68 2f 76 31 0a 00 00 00 01 00 00 00 08  |hash/v1.........|
00000020  53 4b 49 4c 4c 2e 6d 64 00 00 00 2b 23 20 45 78  |SKILL.md...+# Ex|
00000030  61 6d 70 6c 65 20 53 6b 69 6c 6c 0a 0a 44 6f 65  |ample Skill..Doe|
00000040  73 20 6e 6f 74 68 69 6e 67 20 68 61 72 6d 66 75  |s nothing harmfu|
00000050  6c 2e 0a 45 6e 64 2e                             |l..End.|
```

| Offset | Byte | Arti |
|---|---|---|
| `0x00..0x18` | `sterish-content-hash/v1\n` | MAGIC (24 byte) |
| `0x18` | `00 00 00 01` | `u32be(file_count) = 1` |
| `0x1c` | `00 00 00 08` | `u32be(len("SKILL.md")) = 8` |
| `0x20` | `SKILL.md` | `path_bytes` |
| `0x28` | `00 00 00 2b` | `u32be(len(norm_content)) = 42` |
| `0x2c..0x57` | `# Example Skill\n\n…End.` | `norm_content` |

CANON = 87 byte →
`sha256` = **`eaaad94080f641183a4caa2c03e9ccea36c2d466d446909b5b55e0824d3d9edd`**

### Kenapa length-prefix wajib

Tanpa length-prefix, `[("a", "bc")]` dan `[("ab", "c")]` sama-sama menjadi `abc`.
Dengan length-prefix (bagian setelah MAGIC):

```
("a","bc")   00000001 00000001 61 00000002 6263
("ab","c")   00000001 00000002 6162 00000001 63
```

→ vector `concat-ambiguity-a` ≠ `concat-ambiguity-b`, diuji di ketiga bahasa.

---

## 3. Error model

Nama error stabil lintas bahasa (Python `.kind`, TS `ErrorKind`, Rust `HashError::kind()`):

| Error | Kapan |
|---|---|
| `EmptyFileSet` | set file kosong |
| `DuplicatePath` | `path_bytes` yang sama muncul lebih dari sekali |
| `InvalidPath` | lihat §1.2 |
| `NotUtf8` | isi file bukan UTF-8 valid |

Urutan pemeriksaan: `EmptyFileSet` → (per file, urutan input) `InvalidPath` →
`DuplicatePath` → `NotUtf8`. Sebuah input yang melanggar lebih dari satu aturan
melaporkan error pertama menurut urutan itu. Ketiga implementasi wajib sepakat
pada error mana yang keluar — ini diuji, bukan diasumsikan.

Error **tidak pernah** berarti "hash apa adanya". Tidak ada fallback diam-diam.

---

## 4. Yang SENGAJA TIDAK dilakukan

- **TIDAK ada kanonikalisasi JSON.** `manifest.json` di-hash sebagai byte biasa
  seperti file lain. Alasan: kanonikalisasi JSON lintas bahasa (format float,
  urutan key, escaping, integer besar) justru sumber drift yang **lebih besar**
  daripada masalah yang diselesaikannya — persis kelas bug yang ingin dihindari
  `content_hash`. Tiket memberi kebebasan ini di "Left to the owner"; pilihannya
  eksplisit di sini.
- **TIDAK ada normalisasi Unicode (NFC/NFD).** Byte apa adanya. Alasan: dukungan
  NFC tidak seragam di ketiga bahasa tanpa dependensi tambahan (Rust `std` tidak
  punya normalisasi Unicode sama sekali). Konsekuensi: `café` NFC dan `café` NFD
  adalah dua skill berbeda. Itu diterima — keduanya memang byte yang berbeda.
- **TIDAK ada trimming whitespace selain trailing newline.** Setiap normalisasi
  tambahan memperbesar permukaan tempat perubahan bisa disembunyikan dari audit.
- **TIDAK ada mode/permission file, timestamp, symlink, atau file kosong-vs-hilang
  yang dibedakan lewat metadata.** Hanya path + isi. Skill yang bergantung pada
  bit executable berada di luar jangkauan v1.

---

## 5. Batasan yang diketahui (v1)

1. **Hanya skill berbasis teks.** File biner apa pun (gambar, wasm, `.zip`) ditolak
   dengan `NotUtf8`. Skill dengan aset biner butuh `/v2`.
2. **Normalisasi newline menyembunyikan perubahan line-ending.** Itu disengaja
   (checkout Windows tidak boleh mengubah verdict), tapi berarti `content_hash`
   tidak bisa dipakai untuk membuktikan line-ending.
3. **Trailing-newline stripping menyembunyikan perbedaan newline di akhir file.**
   Sama alasannya (editor otomatis menambah/menghapus).
4. **Daftar pengecualian bersifat statis.** Skill yang benar-benar butuh file bernama
   `target/` atau `.DS_Store` tidak bisa menyertakannya.
5. **Tidak ada normalisasi Unicode** (§4). Dua path yang tampil identik di layar bisa
   menghasilkan dua hash berbeda.

---

## 6. Test vectors

File: [`vectors/content-hash-vectors.json`](vectors/content-hash-vectors.json).
Fixture nyata: [`vectors/fixtures/poisoned_skill/`](vectors/fixtures/poisoned_skill/)
(salinan `pipeline/tests/poisoned_skill/`, supaya vector self-contained).

Bentuk tiap entry:
`{id, description, files_note, files: [{path, content_b64}], expected_sha256,
expect_equal_to?, expect_differs_from?}`.
`content_b64` = base64 dari byte **mentah** (sebelum normalisasi) — supaya CRLF dan
byte apa pun selamat melewati JSON.

| id | isi | membuktikan | `expected_sha256` |
|---|---|---|---|
| `single-file` | 1 file `SKILL.md`, ASCII | jalur paling dasar | `eaaad940…4d3d9edd` |
| `poisoned-token-drainer` | `manifest.json` asli dari fixture poisoned | spec terikat ke korpus nyata | `c2bd4a31…28cc87f0` |
| `multi-file-ordering` | 3 file, urutan sisip ≠ urutan terurut, path bersarang, isi non-ASCII | urutan & length-prefix benar | `e650ee53…b6c2ade6` |
| `non-bmp-path-order` | path `Ａ.md` (U+FF21) vs `😀.md` (U+1F600) | urutan **bytewise UTF-8**, bukan UTF-16 | `3b0f76b5…6cf78248` |
| `crlf-equals-lf` | isi logis sama dengan `single-file`, pakai CRLF + CR telanjang + 3 newline akhir | hash **SAMA** — normalisasi jalan | `eaaad940…4d3d9edd` |
| `one-byte-flip` | `single-file` dengan 1 byte berubah (`l` → `L`) | hash **BEDA** — klaim keamanan jalan | `dcf8d82b…4f89732b` |
| `concat-ambiguity-a` | `[("a","bc")]` | length-prefix mencegah tabrakan | `9e858aa5…0dec5ae3` |
| `concat-ambiguity-b` | `[("ab","c")]` | ↑ pasangannya | `666e8c6e…0875de8e` |

Hash lengkap ada di file vector dan di output runner.

`non-bmp-path-order` adalah vector yang paling gampang gagal kalau seseorang menulis
ulang sisi TypeScript dengan `paths.sort()` biasa: UTF-16 menaruh emoji (high surrogate
`0xD83D`) sebelum `U+FF21`, sedangkan UTF-8 bytewise menaruh `Ａ.md` (`EF BC A1`)
sebelum `😀.md` (`F0 9F 98 80`).

### Error cases

9 kasus (`err-empty-set`, `err-duplicate-path`, `err-not-utf8`, `err-absolute-path`,
`err-dot-prefix`, `err-dotdot`, `err-empty-path`, `err-backslash-separator`,
`err-double-slash`) di `error_cases[]`. Ketiga implementasi wajib menolak dengan
**nama error yang sama persis**.

---

## 7. Cara membuktikan (runner)

```bash
bash scripts/verify-content-hash.sh      # atau: make verify-spec
```

Runner:

1. menjalankan Python, TypeScript, dan Rust atas **file vector yang sama**;
2. membandingkan ketiga laporan **byte-for-byte** (`diff -u`) — bukan sekadar mencetak;
3. mengecek ulang invarian yang disebut tiket: `crlf-equals-lf == single-file`,
   `one-byte-flip != single-file`, `concat-ambiguity-a != concat-ambiguity-b`,
   semua `RELATION` `OK`, semua `ERROR` bukan `NO_ERROR`, semua hash 64 hex lowercase,
   jumlah vector ≥ 5;
4. mengecek `expected_sha256` di file vector sama dengan yang baru dihitung
   (JSON yang diedit tangan tidak bisa lolos);
5. mengecek packager direktori: hash `vectors/fixtures/poisoned_skill/` dari disk
   harus sama dengan vector `poisoned-token-drainer`.

**Exit 0 hanya kalau semuanya benar; selain itu exit 1** (exit 2 = harness gagal jalan,
misalnya `cargo` tidak ada). Perilaku gagalnya sudah diuji dengan sabotase sengaja
(mengubah 1 byte di fixture, dan mengedit tangan `expected_sha256`) — keduanya exit 1.

Format laporan bersama (identik di ketiga bahasa):

```
VECTOR   <id> <64-hex>
RELATION <id> equals|differs <other-id> OK|FAIL
ERROR    <id> <ErrorKind>|NO_ERROR
```

Sisi Rust mencetak baris yang sama dengan prefix `STERISH_HASH ` dari
`contracts/registry/src/test.rs`; runner-lah yang melepas prefix itu.

### Kenapa Rust dihitung sebagai saksi independen

Test Rust **tidak membaca** `content-hash-vectors.json`. Ia meng-hardcode vector dan
hash yang diharapkan, dan mengambil manifest poisoned lewat `include_bytes!` langsung
dari fixture. Ia meng-hash dengan `env.crypto().sha256()` — host function yang sama
yang dipakai kontrak yang sudah ter-deploy, bukan crate sha256 dari userspace.
Jadi kesepakatan ketiganya berarti sesuatu.

---

## 8. Menggunakan implementasi referensi

```bash
# Hash sebuah direktori skill (packager + hash), cetak 64 hex
python3 docs/specs/reference/content_hash.py path/to/skill
npx tsx docs/specs/reference/contentHash.ts path/to/skill

# Jalankan vector bersama, cetak laporan
python3 docs/specs/reference/content_hash.py --vectors
npx tsx docs/specs/reference/contentHash.ts --vectors

# Hitung ulang expected_sha256 setelah SENGAJA mengubah vector (jarang!)
python3 docs/specs/reference/content_hash.py --regen
```

> `--regen` menulis ulang `expected_sha256`. Jangan pakai untuk "memperbaiki" runner
> yang merah — runner merah berarti sebuah implementasi menyimpang, dan me-regen
> hanya memindahkan kebohongan ke file vector.

API yang dipakai integrator:

| Bahasa | Fungsi |
|---|---|
| Python | `content_hash(files) -> str`, `hash_dir(root) -> str`, `canonical_bytes(files) -> bytes` |
| TypeScript | `contentHash(files): string`, `hashDir(root): string`, `canonicalBytes(files): Uint8Array` |
| Rust (test) | `content_hash(&env, files) -> Result<String, HashError>` |

---

## 9. Aturan perubahan

`content_hash` sudah dipakai sebagai kunci `DataKey::HashIndex` di Registry.
Mengubah algoritma **membatalkan setiap verdict yang sudah ada di chain**.

Karena itu:

1. Dokumen ini **frozen**. Perbaikan typo boleh; perubahan perilaku tidak.
2. Perubahan perilaku apa pun = spec id baru `sterish-content-hash/v2`, MAGIC baru
   (`b"sterish-content-hash/v2\n"`), file vector baru, dan rencana migrasi eksplisit
   untuk record yang sudah ada.
3. MAGIC yang membawa nomor versi berarti CANON v1 dan v2 tidak akan pernah bertabrakan.
4. Setiap PR yang menyentuh `docs/specs/reference/**`, `docs/specs/vectors/**`, atau
   modul `content_hash_v1` di `contracts/registry/src/test.rs` **wajib** menjalankan
   `make verify-spec` dan menempelkan outputnya.
