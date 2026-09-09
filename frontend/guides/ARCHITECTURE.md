# Sterish Dashboard — Architecture Guide

> Baca ini sebelum menulis kode di `frontend/`.
> Baca bersama [`docs/api-spec.md`](../../docs/api-spec.md) (beku sejak STE-10) dan
> [`app/globals.css`](../app/globals.css) (token desain milik Nabil).

Struktur di sini mengikuti pola yang sama dengan `fe/` di proyek Sterun, supaya siapa pun
yang pindah antar dua repo tidak perlu belajar dua tata letak.

---

## 1. Pemisahan tanggung jawab

| Lapisan | Isinya |
| --- | --- |
| `app/` | routing saja — tidak ada logic, tidak ada UI |
| `src/modules/` | satu folder per halaman: logic + UI |
| `src/components/` | primitif dan layout yang dipakai lintas modul |
| `src/hooks/` | semua hook dan provider client |
| `src/lib/` | urusan API dan chain: client, tipe, wallet kit, fixtures |
| `src/utils/` | helper murni tanpa efek samping |

---

## 2. Struktur folder

```
frontend/
├── app/                                  ← ROUTING SAJA
│   ├── layout.tsx                        shell: font, Providers, Header, Footer
│   ├── providers.tsx                     titik komposisi provider client
│   ├── page.tsx                          /                    → <Registry />
│   ├── error.tsx                         error boundary
│   ├── globals.css                       tailwind + token (MILIK NABIL)
│   ├── skills/[skillId]/
│   │   ├── page.tsx                      /skills/:id          → <SkillDetail />
│   │   └── not-found.tsx                 skill tidak terdaftar
│   ├── tokens/page.tsx                   preview token, alat kerja desain
│   └── api/mock/[...path]/route.ts       delegasi ke src/lib/mockApi.ts
│
├── public/brand/logo/                    aset STE-7 dari Nabil
├── guides/ARCHITECTURE.md                file ini
│
└── src/
    ├── components/
    │   ├── elements/
    │   │   ├── VerdictBadge.tsx          4 verdict, warna + ikon + teks
    │   │   └── ErrorNotice.tsx           menerima ApiError, bukan string mentah
    │   ├── layouts/
    │   │   ├── Header.tsx
    │   │   ├── Footer.tsx
    │   │   └── WalletButton.tsx
    │   └── ui/                           shadcn, dikelola components.json
    │
    ├── modules/
    │   ├── registry/
    │   │   ├── Registry.tsx              dirender app/page.tsx
    │   │   └── component/
    │   │       ├── RegistryTable.tsx
    │   │       ├── RegistryPagination.tsx
    │   │       └── RegistrySkeleton.tsx
    │   └── skill-detail/
    │       ├── SkillDetail.tsx           dirender app/skills/[skillId]/page.tsx
    │       └── component/
    │           ├── VersionCard.tsx
    │           ├── VerdictBanner.tsx
    │           ├── EvidenceLinks.tsx
    │           └── CopyHash.tsx
    │
    ├── hooks/
    │   └── useWallet.tsx                 WalletProvider + useWallet
    │
    ├── lib/
    │   ├── api.ts                        satu-satunya pintu ke API
    │   ├── types.ts                      cermin api-spec v1.0.0
    │   ├── wallet.ts                     Stellar Wallets Kit, dimuat lazy
    │   ├── fixtures.ts                   4 kasus verdict
    │   ├── mockApi.ts                    logic mock, di luar app/
    │   └── utils.ts                      `cn()` milik shadcn
    │
    └── utils/
        └── format.ts                     shortAddress, formatLedgerTime, shortHash
```

---

## 3. Aturan per lapisan

### 3.1 `app/` — routing saja

`page.tsx` melakukan satu hal: `await params` / `await searchParams`, lalu merender komponen
modulnya. Kalau muncul `useState`, `fetch`, atau JSX lebih dari satu elemen, itu tandanya
kodenya milik `modules/`.

Route handler pun begitu: `app/api/mock/[...path]/route.ts` cuma menyelesaikan params dan
memanggil `handleMockRequest`. Logic-nya di `src/lib/mockApi.ts`, yang juga membuat tesnya bisa
memanggil langsung tanpa memalsukan konteks route.

### 3.2 `src/components/elements/` — primitif

Digerakkan props saja. Tanpa fetch, tanpa hook baca data. `ErrorNotice` menerima `ApiError`
supaya bisa membedakan "API bilang tidak" dari "API tidak terjangkau"; itu dua fakta berbeda dan
cuma satu yang layak tombol coba lagi.

### 3.3 `src/modules/` — satu folder per halaman

**Aturan promosi:** dipakai satu modul → tetap di `component/`. Dipakai dua modul atau lebih →
naik ke `components/elements/`. Jangan meng-import dari `component/` milik modul lain; kalau
butuh, promosikan dulu. `VerdictBadge` sudah naik karena dipakai registry dan skill-detail.
`CopyHash` sengaja belum, karena baru dipakai satu modul.

### 3.4 `src/lib/` — API dan chain

Semua yang tahu soal API atau Stellar. Komponen tidak boleh tahu detailnya, dan **tidak ada
`fetch` ke API di luar `lib/api.ts`**. Itu yang membuat tukar mock ↔ live cukup lewat env.

---

## 4. Aturan yang khusus untuk produk ini

### 4.1 Verdict milik satu versi, bukan milik skill

Tidak pernah ada badge verdict di level skill. Tabel registry memisahkan kolom `Latest` dan
`Audited` dan menandai baris saat keduanya berbeda. Skill yang rilis terbarunya belum diaudit
tidak boleh terbaca seperti sudah direstui. Pewarisan verdict antar versi itu bug scaffold yang
dibuang STE-5 dari kontrak, dan sama salahnya kalau muncul lagi di UI.

### 4.2 Gagal baca tidak pernah jadi verdict

Baca yang gagal memunculkan `ErrorNotice`, tidak pernah nilai default. Registry yang tidak
terjangkau bukan bukti sebuah skill aman. `fetch` juga tidak di-cache, walau spec mengizinkan 60
detik, karena verdict basi adalah hal terburuk yang bisa disajikan produk ini.

### 4.3 Status HTTP harus jujur

Skill tidak terdaftar wajib menjawab **404**, bukan 200 berisi teks "not registered". Karena itu
`SkillDetail` menunggu fetch-nya **tanpa** Suspense: shell yang ter-flush duluan mengunci status
di 200.

### 4.4 Teks UI Bahasa Inggris, tanpa em dash

Semua string yang tampil di layar Bahasa Inggris. Em dash dilarang; pakai koma, titik, titik
dua, atau kurung. Komentar kode, commit, dan komentar Linear tetap Bahasa Indonesia.

### 4.5 Jangan tulis nilai warna mentah

Selalu lewat token di `app/globals.css`. Verdict tidak boleh dibedakan warna saja: selalu ada
ikon dan kata, supaya tetap terbaca dalam greyscale dan oleh mata yang buta warna merah-hijau.

---

## 5. Yang perlu diketahui soal API

- **`GET /skills` lambat**, sekitar 0,44 detik per baris. Karena itu halaman minta 20 baris,
  bukan 50 yang dibolehkan spec, timeout client 30 detik, dan tabelnya dibungkus `<Suspense>`.
- **`report_uri` masih null** di semua versi. `GET /reports` masih PLANNED (STE-32), jadi panel
  evidence menulis "not published yet" alih-alih mengarang alasan.
- **Tidak ada filter atau sort di API.** Jangan buat kontrol filter/sort yang jalan di client di
  atas satu halaman; label seperti "trust tertinggi dulu" yang cuma mengurutkan sepertiga data
  itu menyesatkan.

---

## 6. Path alias dan penamaan

`@/` menunjuk ke `src/`. Jangan pernah `../../` lintas folder; di dalam satu modul, relatif boleh.

| Item | Konvensi | Contoh |
| --- | --- | --- |
| File komponen | PascalCase | `VersionCard.tsx` |
| File hook | camelCase, awalan `use` | `useWallet.tsx` |
| File lib / utility | camelCase | `mockApi.ts`, `format.ts` |
| Folder komponen lokal | huruf kecil | `component/` |
| Folder modul | kebab-case | `skill-detail/` |
| Tipe TypeScript | PascalCase | `type Verdict = …` |
| Konstanta | SCREAMING_SNAKE_CASE | `PAGE_SIZE`, `API_BASE_URL` |

---

## 7. Perintah

```bash
pnpm dev          # http://localhost:3000
pnpm typecheck    # next typegen && tsc --noEmit
pnpm lint
pnpm test         # vitest: data layer + mock API
pnpm build
```

`next typegen` wajib jalan sebelum `tsc`: `PageProps` dan `RouteContext` di-generate ke
`.next/types` dan tidak ikut di paket `next`. Tanpa itu, typecheck hijau di mesin yang kebetulan
menjalankan `next dev` dan merah di CI.

**Untuk klaim yang menentukan CI, verifikasi di kloning bersih**, bukan di worktree ini.
