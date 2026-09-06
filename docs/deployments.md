# Sterish — Deployments

Bukti deploy per Working agreement poin 8. Semua alamat di bawah **live di Stellar testnet**
dan bisa diklik. Tidak ada secret di dokumen ini — hanya alamat publik (`G…`) dan contract
address (`C…`); key hidup di `.env` yang ter-`gitignore` (lihat `CLAUDE.md`).

---

## Testnet — 2026-09-03 (STE-13)

| | |
|---|---|
| Network | Stellar **testnet** (`Test SDF Network ; September 2015`), protocol 28 |
| RPC | `https://soroban-testnet.stellar.org` |
| Deploy script | [`scripts/deploy-testnet.sh`](../scripts/deploy-testnet.sh) — deterministik, bisa diulang |
| WASM | build final STE-12, hash diverifikasi sebelum deploy ([`contracts/wasm-hashes.txt`](../contracts/wasm-hashes.txt)) |

### Contract addresses

| Kontrak | Contract address | WASM sha256 | stellar.expert |
|---|---|---|---|
| **Registry** | `CAPDQW2XWTOCFQEP3AUCRRQHVJ5IOUZ45DWPNPVG7USNPE6RZQ3BUXND` | `8c438004591f65d84f8087738c4ff327bc016b38e443b2661bb36f6cd3852489` | [buka](https://stellar.expert/explorer/testnet/contract/CAPDQW2XWTOCFQEP3AUCRRQHVJ5IOUZ45DWPNPVG7USNPE6RZQ3BUXND) |
| **Escrow** | `CCVCNFXK4YHY3ECPWCXLAMEXT4MI457ZREAZBR57CEJ3GQXONW7HVVDE` | `cb241f74d20146b9d4895160e68d0c337f68317c3b6c1f272b0505cdb84d0ad0` | [buka](https://stellar.expert/explorer/testnet/contract/CCVCNFXK4YHY3ECPWCXLAMEXT4MI457ZREAZBR57CEJ3GQXONW7HVVDE) |
| **Tokens** (VERIFIED + license, soulbound) | `CCHVZRLOFGZ5IAYQUSHIPQOTVFABOX6SK5MHNZZUKAOT333KZNVW4EJX` | `318f44583ae3144a65c3992b163f91795b8f28a95d4bc59b4c2147ad00b83206` | [buka](https://stellar.expert/explorer/testnet/contract/CCHVZRLOFGZ5IAYQUSHIPQOTVFABOX6SK5MHNZZUKAOT333KZNVW4EJX) |

WASM sha256 **adalah** wasm hash Soroban (`stellar contract upload` menyimpan kontrak di bawah
`sha256(file)`), jadi nilai di atas mem-pin persis byte yang ter-deploy. Verifikasi ulang:
`bash scripts/build-wasm.sh --check`.

### Aset pembayaran

| | |
|---|---|
| USDC SAC testnet (dipakai Escrow) | `CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA` · [buka](https://stellar.expert/explorer/testnet/contract/CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA) |
| USDC classic issuer (untuk trustline) | `GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5` (`home_domain: centre.io`) |

Keduanya diverifikasi via MCP Stellar Raven (konstanta `USDC_TESTNET_ADDRESS` dari `@x402/stellar`)
**dan** dibaca langsung on-chain. Jangan tertukar: SAC = `C…` (yang di-`transfer` kontrak),
issuer classic = `G…` (yang dipakai saat `changeTrust`).

### Akun test

| Peran | Address | Catatan |
|---|---|---|
| Deployer / admin | `GAGU7Z5RZZJZI2TINQD2E2WAA4JEYB5LRXBBQ23JN6OHV4YUJJCJJ3FB` | admin ketiga kontrak + minter role |
| Auditor | `GCFCURTZ7XHMTKZR7QN2MXRRAIWKGVOOVQV4KCP5EIQ62HGG4S3Y2XPL` | auditor role Registry + Tokens, poster bond |
| Developer | `GD73M4F7RN74KBLFGJP4WKBMCBJWBOA4SFNOP5HG4NBCDQUQCC2ARSZU` | skill owner + requestor audit |
| Reporter | `GADNHGAFXH3BE2PY2QYY5NAH3A6PWKQKK2YMF4HAF5BDOVHKI2GC5JFJ` | penerima bond saat slash |

Semua ter-fund XLM via Friendbot. Auditor sengaja **terpisah** dari developer karena Escrow
menolak `requestor == auditor` (`EscrowError::SelfAudit = 9`).

Trustline USDC (`USDC:GBBD47IF…`) sudah dipasang ke keempatnya:

| Akun | tx |
|---|---|
| deployer | [`3a86fe976cf972e6…`](https://stellar.expert/explorer/testnet/tx/3a86fe976cf972e6a7c42c5d5b6700856fa7c85b6a30702039ac278e9ddddefa) |
| auditor | [`c96324050f717d0f…`](https://stellar.expert/explorer/testnet/tx/c96324050f717d0fc36c43568e6680301c7a6c01f2b5ea7edbcf2b66f9650b41) |
| developer | [`4aaf24b61a20cbf0…`](https://stellar.expert/explorer/testnet/tx/4aaf24b61a20cbf0f525b3e47403a0be263a22647427e659a67b11610be5b009) |
| reporter | [`c147d3c4b7deb4b2…`](https://stellar.expert/explorer/testnet/tx/c147d3c4b7deb4b28ad12d722f90fe775ed7debdb39b91065abe074780fb30a2) |

---

## Bukti on-chain — jalur audit (Registry + Tokens)

Dua skill dipakai. `content_hash` keduanya dihitung dengan implementasi referensi frozen
[`docs/specs/reference/content_hash.py`](specs/reference/content_hash.py) (STE-10), bukan angka karangan.

| Skill | `content_hash` | Verdict |
|---|---|---|
| `com.sterish.weather-lookup` v1.0.0 | `4bf3f90c4047ca2b6c950e127296da95b2ace4f99c8d777eac921358811e42dd` | **Safe**, score 92 |
| `com.evil.token-drainer` v1.0.0 | `c2bd4a316415b4919e3f1f40d9925f4052d020cf3dc2ecabe0e7c9dd28cc87f0` | **Dangerous**, score 5 |

Hash poisoned identik dengan vector `poisoned-token-drainer` di
[`docs/specs/vectors/content-hash-vectors.json`](specs/vectors/content-hash-vectors.json) —
spec, korpus, dan chain terikat pada angka yang sama.

| Langkah | tx |
|---|---|
| `register_skill` (weather-lookup) | [`589a0c31c6d4b14d…`](https://stellar.expert/explorer/testnet/tx/589a0c31c6d4b14d3807e1373f80b99bc2679b749b3b9f0af6b63897cc32b7dc) |
| `submit_verdict` Safe 92 | [`499883165894078a…`](https://stellar.expert/explorer/testnet/tx/499883165894078ad8b5be199b4dcb079e8980a024fa93d42a62512b4a2da41b) |
| `mint_verified` → token #1 | [`d554c547f28677e6…`](https://stellar.expert/explorer/testnet/tx/d554c547f28677e60891444a1cc4a77189b9eb3f1cc2f3e4e2b63ed0a92909eb) |
| `register_skill` (token-drainer) | [`853a3d9b0d6c0971…`](https://stellar.expert/explorer/testnet/tx/853a3d9b0d6c097164ec3bcf56349bdd0083fba70fa65dd39afa5ac022675313) |
| `submit_verdict` Dangerous 5 | [`563b021bba4b4c44…`](https://stellar.expert/explorer/testnet/tx/563b021bba4b4c44a95d2cbe3b7057b6d71b7cb7fb2920b33fe02cf277c69a87) |
| `mint_verified` (token-drainer) | **ditolak on-chain** — `Error(Contract, #4)` = `TokenError::NotSafeVerdict`. Tidak ada tx sukses, dan itu memang buktinya. |

### Pembacaan yang bisa direproduksi siapa pun

```bash
R=CAPDQW2XWTOCFQEP3AUCRRQHVJ5IOUZ45DWPNPVG7USNPE6RZQ3BUXND
T=CCHVZRLOFGZ5IAYQUSHIPQOTVFABOX6SK5MHNZZUKAOT333KZNVW4EJX

stellar contract invoke --id $R --network testnet --send=no -- query_all_skills --start 0 --limit 10
stellar contract invoke --id $R --network testnet --send=no -- \
  lookup_by_hash --content_hash 4bf3f90c4047ca2b6c950e127296da95b2ace4f99c8d777eac921358811e42dd
stellar contract invoke --id $T --network testnet --send=no -- \
  is_verified_token --skill_id com.evil.token-drainer --version 1.0.0
```

Hasil yang diverifikasi saat deploy:

| Query | Hasil |
|---|---|
| `lookup_by_hash(4bf3f90c…)` | record `com.sterish.weather-lookup` v1.0.0, verdict `Safe`, score 92 |
| `lookup_by_hash(<hash sama, 1 bit di-flip>)` | **`null`** — skill terbaca *unaudited*. Ini klaim inti proposal, live. |
| `lookup_by_hash(c2bd4a31…)` | record `com.evil.token-drainer`, verdict `Dangerous`, score 5 |
| `is_verified` safe / poisoned | `true` / `false` |
| `is_verified_token` safe / poisoned | `true` / `false` |
| `get_skill_count` · `total_supply` | `2` · `1` |

---

## Bukti on-chain — jalur ekonomi (settle & slash)

⚠️ **Baca ini dulu.** Escrow kanonik di atas di-wire ke **USDC SAC resmi**, dan USDC testnet
hanya bisa didapat dari [Circle faucet](https://faucet.circle.com/) yang **web-only + Captcha —
tidak bisa di-script**. Jadi kedua jalur ekonomi dieksekusi on-chain memakai **escrow rehearsal
kedua** yang di-wire ke SAC aset uji yang kami kontrol, supaya mekanikanya terbukti live dengan
tx nyata. Kode kontrak, script, dan aktornya **identik**; yang berbeda hanya alamat aset.

| | |
|---|---|
| Escrow rehearsal | `CAZUICCUXUCDN2V6QPWY3TM7KLUE6U7PDAIGQYIH65QIQWJCZYU6WV3G` · [buka](https://stellar.expert/explorer/testnet/contract/CAZUICCUXUCDN2V6QPWY3TM7KLUE6U7PDAIGQYIH65QIQWJCZYU6WV3G) |
| Aset rehearsal | `TUSDC` SAC `CDAYXDIDIINSVQVQRFCH7JSHTFZN4KIZKMNUZRVACHHFLTYGZEZV4OF2`, issuer `GAYCOQ5AMBT3FCIDU5DVIHEGN2QJND5HJOVXSRNT7OKRYETNU5V6MQGI` |
| Nominal | fee 5.0000000 · bond 10.0000000 |

✅ **Jalur kanonik sudah dijalankan (STE-16, 2026-09-06).** USDC testnet diisi lewat Circle
faucet, lalu seluruh alur dieksekusi di escrow kanonik dengan **USDC asli** — bukti di bagian
"orchestrator pipeline (STE-16)" di bawah. Bagian di bawah ini dipertahankan sebagai catatan
kondisi saat STE-13, dan sebagai prosedur kalau saldo habis lagi.

**Kalau perlu diulang:** isi USDC ke `GD73M4F7RN74KBLF…` (developer) dan
`GCFCURTZ7XHMTKZR…` (auditor) lewat Circle faucet, lalu jalankan satu perintah:

```bash
ESCROW=CCVCNFXK4YHY3ECPWCXLAMEXT4MI457ZREAZBR57CEJ3GQXONW7HVVDE \
ASSET=CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA \
bash scripts/testnet-economic-flows.sh
```

Script yang sama itulah yang menghasilkan tabel di bawah, jadi jalur kanonik tinggal dijalankan.

### Jalur SETTLE — auditor jujur dibayar

Saldo (stroops): developer `1000000000 → 950000000` (−fee), auditor `1000000000 → 1050000000`
(+fee, bond kembali), escrow `0 → 0`.

| Langkah | tx |
|---|---|
| `create_audit_request` #1 | [`67aa12227fe06062…`](https://stellar.expert/explorer/testnet/tx/67aa12227fe060625383b8dd0081aec20062cbfd41008c6f502a3d71e096d3e6) |
| `post_bond` #1 | [`353125251c2aae32…`](https://stellar.expert/explorer/testnet/tx/353125251c2aae3202868236284247302175e135b6ab9f9150891c1e5ece2d53) |
| **`settle` #1** | [`eae8eb123e7f5fc5…`](https://stellar.expert/explorer/testnet/tx/eae8eb123e7f5fc57beb0de90ff443c12dc1c09d09276b78c40d8b443816eeac) |

### Jalur SLASH — bond pindah ke reporter

Saldo (stroops): reporter `0 → 100000000` (+bond), developer `950000000 → 950000000`
(fee di-refund penuh), auditor `1050000000 → 950000000` (−bond), escrow `0 → 0`.

| Langkah | tx |
|---|---|
| `create_audit_request` #2 | [`6535bd3debc9b8d0…`](https://stellar.expert/explorer/testnet/tx/6535bd3debc9b8d06d3ea9332374ca4221b9cb93ddc892b798d190f21cae4cbe) |
| `post_bond` #2 | [`56ab1c9072718d7f…`](https://stellar.expert/explorer/testnet/tx/56ab1c9072718d7f66a1223d458cd6a899c8056484a46127d2b67ff811f83556) |
| **`slash` #2 → reporter** | [`c8bfb19a248b7287…`](https://stellar.expert/explorer/testnet/tx/c8bfb19a248b728784e5782b24444b2a2a8b14ac59fcbab85b4d5566adba923c) |

Script mem-`assert` tiap delta saldo, bukan sekadar mencetaknya; keempat assertion di tiap jalur
lolos. Bond benar-benar berpindah ke pihak ketiga yang bukan pembayar dan bukan auditor.

---

## Handoff

| Konsumen | Yang dibutuhkan |
|---|---|
| Pipeline / orchestrator (STE-16) | `REGISTRY_CA`, `TOKENS_CA`, secret **auditor** (`AUDITOR_SECRET` di `.env`) |
| API (STE-17) | `REGISTRY_CA`, `TOKENS_CA` — read-only, tidak butuh key |
| x402 seller (STE-19) | `TOKENS_CA` + secret **minter** (saat ini = deployer; rotasi lewat `set_minter_role`) |
| Env deploy (STE-21/22) | seluruh blok CA di atas |

⚠️ **STE-16 harus memperbaiki `pipeline/src/sterish_pipeline/onchain.py` dulu.** Submitter itu
memanggil `submit_verdict` dengan 4 argumen tanpa `version` dan meng-encode verdict sebagai `u32`;
ABI beku butuh 5 argumen dengan verdict sebagai enum. Melawan kontrak yang sekarang live, submitter
itu **pasti gagal**.

## Bukti on-chain — orchestrator pipeline (STE-16)

Alur penuh dijalankan dari `sterish_pipeline.orchestrator` melawan kontrak kanonik di atas,
dengan **USDC testnet asli** di escrow kanonik. Skill uji dibuat dengan id ber-timestamp
supaya `register_skill` benar-benar dijalankan, bukan di-skip.

**Skill SAFE — `com.sterish.canon-safe-1788685783`** (score 90)
`evidence_hash` `c99ed231df7b42bf…`

| Langkah | tx |
|---|---|
| `register_skill` | [`ed6bf00bed0c72fb…`](https://stellar.expert/explorer/testnet/tx/ed6bf00bed0c72fbeee86dd3726b74a467b0f688fcffeb087625f6d5d1abbd96) |
| `submit_verdict` | [`a04fdefac6b41297…`](https://stellar.expert/explorer/testnet/tx/a04fdefac6b41297f53258c0d9ea06626070cde79db786588f4c93da36603c96) |
| `mint_verified` | [`7feb228ac6e49065…`](https://stellar.expert/explorer/testnet/tx/7feb228ac6e49065fcd24811d766812cf2355399dff44af1f26c23f834e137c0) |
| `create_audit_request` | [`d3e1650c9821e685…`](https://stellar.expert/explorer/testnet/tx/d3e1650c9821e685314e1b832cce8e989f8b10558c7ff7d41d65712d6f0ba8ee) |
| `post_bond` | [`16452fb9441a4aa3…`](https://stellar.expert/explorer/testnet/tx/16452fb9441a4aa3009a959fab881e511b76b256d349c77c1b3e60fab14f4c5f) |
| **`settle`** | [`55ba337ed2ab8d15…`](https://stellar.expert/explorer/testnet/tx/55ba337ed2ab8d15955737331ab44fbfe44bc63e8e3c1dd0398ea63f003b43db) |

**Skill DANGEROUS — `com.sterish.canon-poisoned-1788685812`** (score 10)
`evidence_hash` `a818b83de04c1190…`

| Langkah | tx |
|---|---|
| `register_skill` | [`b7840228becdecd5…`](https://stellar.expert/explorer/testnet/tx/b7840228becdecd5648f842d59519821aa8aeabb217e7247c3e0764c7d0361a9) |
| `submit_verdict` | [`58eb78df233aaa94…`](https://stellar.expert/explorer/testnet/tx/58eb78df233aaa947f24aba0632395aa57cd539380516d47da4bc1a7adad9432) |
| `mint_verified` | **di-skip** — verdict DANGEROUS, tidak ada badge |
| `create_audit_request` | [`b90851bd81a5297e…`](https://stellar.expert/explorer/testnet/tx/b90851bd81a5297e96462ce5c89bcd20cce24de72866ce0a48fa1e73bcf0b209) |
| `post_bond` | [`5195684ee23236a7…`](https://stellar.expert/explorer/testnet/tx/5195684ee23236a7263cc885cfbd9d42ccb2ef262c0007fe3b22e80f4cf54baf) |
| **`slash`** | [`4518657fdc161a8c…`](https://stellar.expert/explorer/testnet/tx/4518657fdc161a8cc5b7669e1a6de67cc303f2bcfed1d980375c4c2c2e12abd8) |

Diverifikasi dengan membaca ulang dari chain, bukan dari objek hasil orchestrator:
`lookup_by_hash` mengembalikan verdict dan score yang sama dengan report, `registry.is_verified`
dan `tokens.is_verified_token` keduanya `true` untuk yang SAFE dan `false` untuk yang DANGEROUS,
dan `evidence_hash` on-chain sama persis dengan `sha256` byte report yang dipublish.

Nominal di suite live sengaja kecil (fee 0.1 · bond 0.2 USDC), bukan 5/10. Uangnya mengalir satu
arah — developer membayar tiap fee, auditor dan admin menerima tiap settle dan slash — jadi suite
seukuran 5 USDC per request menguras pembayar dalam tiga run, lalu gagal karena saldo kosong
alih-alih karena hal yang sebenarnya diuji. Mengisi ulang butuh Circle faucet yang ber-Captcha.

### Empat perilaku yang ditemukan lewat pengujian, bukan dari dokumen

1. **Transaction meta sekarang `v4`, bukan `v3`.** Membaca `meta.v3.soroban_meta.return_value`
   diam-diam menghasilkan `None`. `request_id` dari `create_audit_request` datang lewat jalur itu,
   dan fallback tebakan (`get_request_count() - 1`) sempat menunjuk request **milik STE-13**,
   sehingga `post_bond` nyaris mengunci bond di job orang lain. Orchestrator sekarang **menolak
   menebak** kalau id-nya tidak ada.
2. **`prepare_transaction` melempar pesan generik** ("Simulation transaction failed…") dan
   menyimpan detailnya di response yang menempel. Tanpa menggali detail itu, penolakan kontrak
   terlihat seperti gangguan jaringan dan di-retry tiga kali percuma.
3. **Enum unit variant di-encode sebagai `vec[symbol]`.** Dibuktikan lewat simulasi: `vec[symbol]`
   -> `Error(Contract, #3)` (diterima, ditolak logika bisnis); `u32` dan symbol telanjang ->
   `Error(WasmVm, InvalidAction)`; 4 argumen -> `UnexpectedSize`.
4. **Nomor error bertabrakan antar kontrak.** Escrow `#3` = `NotOpen`, registry `#3` =
   `SkillNotFound`, dan `#10` datang dari **USDC SAC** (kontrak pihak lain) menembus lewat escrow
   saat pembayar tidak sanggup menutup transfer. Satu tabel error milik registry membuat kegagalan
   escrow yang nyata terbaca `Unknown (#10)`.

## Bukti on-chain — pembayaran x402 (STE-19)

Loop berbayar penuh dijalankan di testnet dengan **agen baru** yang tidak punya riwayat apa pun:
402 → bayar USDC → license ter-mint → 200, lalu panggilan kedua **200 tanpa bayar lagi**.

| | |
|---|---|
| Agen | `GBFXMHA77OLBYF3JJB43O6CKZ4QR35AAQALJK72MUIHTZNBVAQGTTZWY` |
| Facilitator | OZ Channels `https://channels.openzeppelin.com/x402/testnet` |
| Aset | USDC SAC `CBIELTK6…` · `payTo` akun klasik `GD73M4F7…` |
| Harga | `1000000` base unit = **0.10 USDC** |
| Mint license | [`5768516f156b74e7…`](https://stellar.expert/explorer/testnet/tx/5768516f156b74e7e97ac733c45261f59ec38d550a990159743d5fb6720a9ef9) |

Diverifikasi dengan membaca ulang dari chain, bukan dari respons API:

- saldo USDC agen **2.0000000 → 1.9000000** — terbayar tepat 0.10, tidak lebih
- `tokens.has_license(agen, skill, versi)` → **true**
- `total_supply` token bertambah

Skill DANGEROUS **tidak pernah ditawarkan**: `/use` mengembalikan `403 NOT_VERIFIED` tanpa
challenge pembayaran sama sekali, dan kontrak token menolaknya secara independen lewat gerbang
badge VERIFIED.

### Catatan yang menghemat waktu berikutnya

- **Key facilitator testnet tidak butuh autentikasi.** `curl https://channels.openzeppelin.com/testnet/gen`
  langsung mengembalikan `{"apiKey": "..."}` — tidak ada Captcha, tidak ada OAuth (itu hanya untuk
  mainnet). Jadi jalur berbayar tidak terblokir langkah manual seperti Circle faucet.
- **Bentuk 402 ditangkap dari server referensi**, bukan ditebak: requirements ada di header
  `PAYMENT-REQUIRED` sebagai base64 JSON dengan body kosong. `amount` 7 desimal.
- **`/supported` melaporkan `areFeesSponsored: true`**, yang membuat agen pembeli tidak perlu XLM
  sama sekali — dia hanya menandatangani auth entry, facilitator yang merakit dan membayar fee.

## Deployment backend (STE-25)

Stack Docker Compose di `deploy/`: API (indexer jalan di dalam prosesnya) + Caddy
sebagai reverse proxy dengan TLS otomatis. Prosedur lengkap di `deploy/README.md`.

**Diverifikasi lokal end-to-end**, bukan sekadar ditulis: image dibangun, stack
dijalankan, dan seluruh permukaan diuji **lewat reverse proxy** — `/health`,
`/check`, `/skills`, `/use` (402 dengan challenge), dan `/use` untuk skill
DANGEROUS (403, tidak pernah ditawarkan). Lalu **agen baru benar-benar membeli
license lewat stack ter-container**: mint tx
[`739428bf85f92386…`](https://stellar.expert/explorer/testnet/tx/739428bf85f92386981a5858273b013956456238b8c7ee1c639e680b0939275f).

`deploy/verify.sh <base-url>` menjalankan pemeriksaan yang sama terhadap host mana
pun, termasuk jalur errornya — justru itu yang membusuk diam-diam.

### Tiga hal yang ketahuan karena benar-benar dijalankan

1. **Build context 3,8 GB.** Context-nya adalah root repo, jadi tanpa
   `.dockerignore` setiap build mengirim `contracts/target` (3,3 GB) plus dua
   virtualenv dan `node_modules`. Setelah ditambahkan: **340 kB**.
2. **`docs/` itu dependensi runtime, bukan dokumentasi.** `sterish_pipeline.specs`
   menemukan repo lewat `docs/specs/verdict.schema.json` dan memuat implementasi
   referensi `content_hash` dari `docs/specs/reference/`; `/use` meng-hash artefak
   lewat modul itu sebelum menyajikannya. Mengecualikan `docs/` membuat jalur
   berbayar melempar `SpecsNotFound` **di produksi** sementara semua test offline
   tetap hijau.
3. **Volume dan direktif Caddy yang kosong.** Container jalan sebagai uid 10001
   tapi named volume datang milik root (`unable to open database file`), dan
   `STERISH_ACME_EMAIL` kosong menghasilkan direktif `email` tanpa argumen yang
   membuat Caddy **menolak start sama sekali** — `{$VAR:default}` hanya berlaku
   kalau variabelnya tidak di-set, bukan kalau kosong.

### Live — sudah ter-deploy

| | |
|---|---|
| **URL publik** | **https://pve02.tail4d50d6.ts.net** |
| Host | Proxmox `pve02`, LXC **204 `ct-sterish`**, `192.168.18.43/24` |
| Spesifikasi | 2 core · 2 GB RAM · 20 GB `local-lvm` · unprivileged · `nesting=1,keyctl=1` · `onboot=1` |
| TLS | Let's Encrypt asli lewat Tailscale (`ssl_verify_result: 0`), berlaku s/d 5 Des 2026 |
| Akses publik | Tailscale Funnel di pve02 |

Diverifikasi **lewat URL publik**, bukan dari dalam host: seluruh `deploy/verify.sh`
lolos (`/health`, `/skills`, 404/400 pada jalur error, `/use` 402 dengan challenge,
`/use` DANGEROUS 403), dan **agen baru benar-benar membeli license lewat HTTPS
publik** — mint tx
[`9e59297638174ee3…`](https://stellar.expert/explorer/testnet/tx/9e59297638174ee3a063877e815cb78362ad46dbf276e6454dbee0232b0ad4df).

**Restart otomatis terbukti:** CT di-reboot, layanan pulih sendiri dalam ~20 detik
tanpa campur tangan (`onboot=1` + `restart: unless-stopped`).

Dipilih pve02 karena **Funnel pve01 sudah dipakai `ct-sterun`** (proxy ke
`192.168.18.42:3001`); mengambil root path di sana akan mematikan layanan itu.
Konvensi CT (pola nama, nameserver, bridge, unprivileged, onboot) disalin dari
`ct-sterun` alih-alih dikarang sendiri.

### Bug produksi yang hanya muncul setelah ter-deploy

Dua request balik **503 tanpa pernah sampai ke aplikasi**, salah satunya tepat
setelah `mint_license`. Mudah dikira gangguan jaringan karena lolos saat diulang.

Penyebabnya: setiap handler `async def` sementara **semua panggilan di dalamnya
blocking** — simulasi Soroban, round trip facilitator, dan mint. Semuanya berjalan
di atas event loop, jadi satu mint yang polling ledger beberapa detik membekukan
seluruh API. Dengan satu klien ini tidak pernah terlihat; dengan URL publik, akan
terlihat seperti layanan yang rewel.

Diperbaiki dengan melepas `async` (FastAPI menjalankan handler sync di threadpool).
Dibuktikan di deployment: 12 request paralel, terlama 4,07 detik, total wall **4,17
detik** — kalau masih terblokir, wall time akan sekitar 12×.

### Operasional

```bash
# di dalam CT 204
bash /usr/local/bin/ctredeploy          # fetch origin/main, rebuild, restart
cd /opt/sterish/deploy && docker compose logs -f api
```

`deploy/.env` di CT ber-mode 600 dan dikirim lewat stdin, jadi `MINTER_SECRET` dan
`OZ_API_KEY` tidak pernah masuk process list host maupun log SSH.

**Funnel = terekspos ke internet publik**, sesuai syarat tiket ("URL publik
ber-TLS"). Untuk membatasi ke tailnet saja: `tailscale funnel --https=443 off` di
pve02.

## Catatan operasional

- **v1 non-upgradeable.** Kalau interface berubah, redeploy dan perbarui dokumen ini.
- **Testnet di-reset berkala** oleh SDF — semua contract address di atas akan hilang saat itu terjadi.
  `scripts/deploy-testnet.sh` sengaja dibuat supaya redeploy jadi satu perintah.
- Alamat USDC SAC di Escrow **immutable** (dikunci di `__constructor`, tanpa setter). Salah alamat
  saat deploy = redeploy.
