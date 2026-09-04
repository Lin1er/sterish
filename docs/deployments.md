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

**Untuk menyelesaikan jalur kanonik:** isi USDC ke `GD73M4F7RN74KBLF…` (developer) dan
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

✅ **Selesai di STE-16.** `pipeline/src/sterish_pipeline/onchain.py` sudah ditulis ulang.
Kondisi sebelumnya bahkan lebih parah dari catatan awal ini: modul itu **tidak bisa di-import
sama sekali** (`from stellar_sdk.contract import Contract` — modul itu tidak mengekspor
`Contract`) dan memakai `Server` (Horizon, yang tidak punya `prepare_transaction` maupun
`simulate_transaction`), selain memang memanggil `submit_verdict` dengan 4 argumen dan verdict
sebagai `u32`. Tidak ada satu pun kode yang meng-import-nya, jadi semua itu tidak pernah jalan.
Bukti jalur barunya ada di bagian "orchestrator pipeline (STE-16)" di bawah.

## Bukti on-chain — orchestrator pipeline (STE-16)

Jalur penuh `audit -> register -> submit_verdict -> mint_verified` dieksekusi dari
`sterish_pipeline.orchestrator` melawan kontrak kanonik di atas. Skill uji dibuat dengan
id ber-timestamp supaya `register_skill` benar-benar dijalankan, bukan di-skip.

**Skill SAFE — `com.sterish.e2e-1788541618`** (score 90):

| Langkah | tx |
|---|---|
| `register_skill` | [`c7fa57577317a474…`](https://stellar.expert/explorer/testnet/tx/c7fa57577317a474e301a0d5ae5a6012a52e9ab004cf1602ccd07309d383b69b) |
| `submit_verdict` | [`193b6be0c1b00b03…`](https://stellar.expert/explorer/testnet/tx/193b6be0c1b00b030c2a5e31e5f63921e737ef0a20e9ee0560b3db3acd2ce765) |
| `mint_verified` | [`11615d79803ed451…`](https://stellar.expert/explorer/testnet/tx/11615d79803ed451bf34330c7a82b6bee530f0aa008649901ede2b4046906b70) |

Jalur ekonomi pada escrow rehearsal (aset yang kami kontrol — lihat peringatan di atas):

| Langkah | tx |
|---|---|
| `create_audit_request` | [`2fcecf65bd81f63e…`](https://stellar.expert/explorer/testnet/tx/2fcecf65bd81f63e7654c6aa7426cb29f905168f424ab4ddf56552245132b2b2) |
| `post_bond` | [`ed798f4ddb357669…`](https://stellar.expert/explorer/testnet/tx/ed798f4ddb3576698c7a12e59e42fb94d53d86ce2028ca55cc4cf611ad65749e) |
| **`settle`** | [`34c42da63b00ea7b…`](https://stellar.expert/explorer/testnet/tx/34c42da63b00ea7b3474c955a076f59ab6a05bf6673c63af09d4eb1143b252fc) |

Diverifikasi dengan membaca ulang dari chain, bukan dari objek hasil orchestrator:
`lookup_by_hash` mengembalikan `Safe` dengan score yang sama dengan report,
`registry.is_verified` dan `tokens.is_verified_token` keduanya `true`, dan
`evidence_hash` on-chain **sama persis** dengan `sha256` byte report yang dipublish
(pihak ketiga bisa menghitung ulang sendiri).

Skill DANGEROUS diaudit lewat jalur yang sama **tidak pernah** mendapat badge:
`mint_verified` di-skip orchestrator, dan kontrak sendiri menolaknya lewat
`registry.is_verified` — dua gerbang independen.

### Tiga perilaku RPC yang ditemukan lewat pengujian, bukan dari dokumen

1. **Transaction meta sekarang `v4`, bukan `v3`.** Membaca `meta.v3.soroban_meta.return_value`
   diam-diam menghasilkan `None`. Ini bukan kehilangan yang tidak berbahaya: `request_id`
   dari `create_audit_request` datang lewat jalur itu, dan fallback tebakan
   (`get_request_count() - 1`) sempat menunjuk request **milik STE-13**, sehingga
   `post_bond` nyaris mengunci bond di job orang lain. Sekarang semua versi meta dicoba
   dan orchestrator **menolak menebak** kalau id tidak ada.
2. **`prepare_transaction` melempar pesan generik** ("Simulation transaction failed…") dan
   menyimpan detailnya di response yang menempel. Tanpa menggali detail itu, penolakan
   kontrak terlihat seperti gangguan jaringan dan di-retry tiga kali percuma.
3. **Enum unit variant di-encode sebagai `vec[symbol]`.** Dibuktikan dengan simulasi:
   `vec[symbol]` -> `Error(Contract, #3)` (diterima, ditolak logika bisnis); `u32` dan
   symbol telanjang -> `Error(WasmVm, InvalidAction)`; 4 argumen -> `UnexpectedSize`.

## Catatan operasional

- **v1 non-upgradeable.** Kalau interface berubah, redeploy dan perbarui dokumen ini.
- **Testnet di-reset berkala** oleh SDF — semua contract address di atas akan hilang saat itu terjadi.
  `scripts/deploy-testnet.sh` sengaja dibuat supaya redeploy jadi satu perintah.
- Alamat USDC SAC di Escrow **immutable** (dikunci di `__constructor`, tanpa setter). Salah alamat
  saat deploy = redeploy.
