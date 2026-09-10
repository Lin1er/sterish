# Sterish `content_hash` — canonical bytes v1

**Status:** FROZEN (STE-10). **Spec id:** `sterish-content-hash/v1`.
**Any change to this document is a new version (`/v2`), not an edit in place.**

`content_hash` is a skill's byte identity. It is computed in **three places**:

| Place | When | Implementation |
|---|---|---|
| Audit pipeline (Python) | at intake, before Stage 1 | `docs/specs/reference/content_hash.py` |
| Registry contract (Rust/Soroban) | on `register_skill` / `check_skill` lookup | `env.crypto().sha256()` |
| Dashboard / client (TypeScript) | at check-before-install | `docs/specs/reference/contentHash.ts` |

If those three ever disagree, `check(skill)` **lies**: a user installs bytes different from the
bytes that were audited, while looking at a VERIFIED badge. That is why this ticket freezes the
algorithm down to the byte and proves it with a cross-language runner rather than merely
describing it.

---

## 1. The algorithm

```
CANON = MAGIC
     || u32be(file_count)
     || for each file, sorted ASC bytewise by path_bytes:
            u32be(len(path_bytes))    || path_bytes
            u32be(len(norm_content))  || norm_content

MAGIC        = b"sterish-content-hash/v1\n"      (24 bytes, including the \n)
content_hash = sha256(CANON)                     (32 bytes, 64 lowercase hex)
```

`MAGIC` hex: `737465726973682d636f6e74656e742d686173682f76310a`.

`content_hash` is always represented as **64 lowercase hex characters** in JSON, in the API and
in documents. Inside the contract it is a raw `BytesN<32>`.

### 1.1 Normalisation rules (normative)

1. **`path_bytes`** = the UTF-8 of the file path **relative to the skill root**.
   POSIX `/` separators. No `./` or `/` prefix. No `..` components.
2. **Ordering** = ASC **bytewise on the raw `path_bytes`** — not per-codepoint comparison, not
   locale-aware, not UTF-16 code unit order.
   - Python: `sorted(files, key=lambda f: f.path_bytes)` (`Ord` on `bytes` is bytewise).
   - TypeScript: compare `Uint8Array` byte by byte (`compareBytes`).
     **Do NOT** use the default `Array.prototype.sort()` on strings — that is UTF-16 code unit
     order and it **differs** for non-BMP code points.
   - Rust: the built-in `Ord` on `[u8]` / `Vec<u8>`.
3. **`norm_content`** = the file's content bytes, normalised in this order:
   a. every `\r\n` → `\n` (leftmost, non-overlapping);
   b. then every remaining `\r` → `\n`;
   c. then **all** trailing `\n` at end of file are stripped.
   No other whitespace normalisation. No per-line trimming. No encoding change.
4. **Files must be valid UTF-8.** Otherwise → an explicit `NotUtf8` error.
   v1 supports text-based skills only; see §5 (known limits).
5. **`u32be`** = unsigned 32-bit big-endian. The length prefix is **mandatory** so that
   `("ab","c")` and `("a","bc")` can never produce the same byte stream.
6. **A duplicate path → `DuplicatePath`. An empty file set → `EmptyFileSet`.**
7. `file_count` and every length must fit in a u32. A skill with a single file over 4 GiB, or
   more than 2^32-1 files, is rejected.

### 1.2 Path validation (normative)

A path is rejected with `InvalidPath` if any of the following holds:

| Condition | Example |
|---|---|
| empty path | `""` |
| not valid UTF-8 | — |
| contains `\` | `tools\zeta.py` |
| contains a NUL byte | — |
| has an empty component (leading, trailing or double slash) | `/SKILL.md`, `a//b`, `a/` |
| has a `.` component | `./SKILL.md`, `a/./b` |
| has a `..` component | `../SKILL.md` |

> **Note on the deviation from the ticket text.** The PM's spec said "no `./` or `/` prefix, no
> `..` components". The implementation widens that to forbidding `.` and `..` **components** in
> any position, forbidding empty components, and forbidding backslashes. A backslash is
> technically legal in a POSIX filename; it is rejected deliberately so that a Windows-style
> path (`tools\zeta.py`) does not silently become *one* filename and produce a `content_hash`
> different from a packager on another OS. This is a tightening, not a loosening: no input that
> was previously valid now hashes differently.

### 1.3 Excluded files

Excluded by the **packager, before hashing** — they are not part of the hash algorithm:

```
.git/**   node_modules/**   __pycache__/**   .venv/**   target/**   .DS_Store   *.pyc
```

Directory names match at any depth. `*.pyc` matches on the filename. **The final set of files
that go into the hash is recorded explicitly in every test vector** (the `files_note` field in
`content-hash-vectors.json`).

---

## 2. Worked example — vector `single-file`

Input: one file, path `SKILL.md`, raw content
`"# Example Skill\n\nDoes nothing harmful.\nEnd.\n"` (43 bytes).

Normalisation strips the trailing `\n` → `norm_content` is 43 − 1 = **42** bytes (`0x2b`).

```
00000000  73 74 65 72 69 73 68 2d 63 6f 6e 74 65 6e 74 2d  |sterish-content-|
00000010  68 61 73 68 2f 76 31 0a 00 00 00 01 00 00 00 08  |hash/v1.........|
00000020  53 4b 49 4c 4c 2e 6d 64 00 00 00 2b 23 20 45 78  |SKILL.md...+# Ex|
00000030  61 6d 70 6c 65 20 53 6b 69 6c 6c 0a 0a 44 6f 65  |ample Skill..Doe|
00000040  73 20 6e 6f 74 68 69 6e 67 20 68 61 72 6d 66 75  |s nothing harmfu|
00000050  6c 2e 0a 45 6e 64 2e                             |l..End.|
```

| Offset | Bytes | Meaning |
|---|---|---|
| `0x00..0x18` | `sterish-content-hash/v1\n` | MAGIC (24 bytes) |
| `0x18` | `00 00 00 01` | `u32be(file_count) = 1` |
| `0x1c` | `00 00 00 08` | `u32be(len("SKILL.md")) = 8` |
| `0x20` | `SKILL.md` | `path_bytes` |
| `0x28` | `00 00 00 2b` | `u32be(len(norm_content)) = 42` |
| `0x2c..0x57` | `# Example Skill\n\n…End.` | `norm_content` |

CANON is 87 bytes →
`sha256` = **`eaaad94080f641183a4caa2c03e9ccea36c2d466d446909b5b55e0824d3d9edd`**

### Why the length prefix is mandatory

Without a length prefix, `[("a", "bc")]` and `[("ab", "c")]` both become `abc`.
With it (the portion after MAGIC):

```
("a","bc")   00000001 00000001 61 00000002 6263
("ab","c")   00000001 00000002 6162 00000001 63
```

→ vector `concat-ambiguity-a` ≠ `concat-ambiguity-b`, tested in all three languages.

---

## 3. Error model

Error names are stable across languages (Python `.kind`, TS `ErrorKind`, Rust `HashError::kind()`):

| Error | When |
|---|---|
| `EmptyFileSet` | the file set is empty |
| `DuplicatePath` | the same `path_bytes` appears more than once |
| `InvalidPath` | see §1.2 |
| `NotUtf8` | file content is not valid UTF-8 |

Check order: `EmptyFileSet` → (per file, in input order) `InvalidPath` → `DuplicatePath` →
`NotUtf8`. An input violating more than one rule reports the first error in that order. All
three implementations must agree on which error comes out — that is tested, not assumed.

An error **never** means "hash it anyway". There is no silent fallback.

---

## 4. What is deliberately NOT done

- **NO JSON canonicalization.** `manifest.json` is hashed as ordinary bytes like any other
  file. Reason: canonicalizing JSON across languages — float formatting, key order, escaping,
  large integers — is a **larger** source of drift than the problem it solves, exactly the class
  of bug `content_hash` exists to avoid. The ticket left this to the owner under "Left to the
  owner"; the choice is made explicitly here.
- **NO Unicode normalisation (NFC/NFD).** Bytes as they are. Reason: NFC support is not uniform
  across the three languages without extra dependencies (Rust `std` has no Unicode
  normalisation at all). Consequence: `café` in NFC and `café` in NFD are two different skills.
  That is accepted — they genuinely are different bytes.
- **NO whitespace trimming beyond the trailing newline.** Every additional normalisation
  enlarges the surface where a change can be hidden from the audit.
- **NO file mode or permission, timestamp, symlink, or empty-vs-missing distinction carried
  through metadata.** Path and content only. A skill that depends on the executable bit is out
  of scope for v1.

---

## 5. Known limits (v1)

1. **Text-based skills only.** Any binary file (an image, a wasm blob, a `.zip`) is rejected
   with `NotUtf8`. A skill with binary assets needs `/v2`.
2. **Newline normalisation hides line-ending changes.** That is deliberate — a Windows checkout
   must not change a verdict — but it means `content_hash` cannot be used to prove a line
   ending.
3. **Trailing-newline stripping hides differences in the final newline.** Same reason: editors
   add and remove it automatically.
4. **The exclusion list is static.** A skill that genuinely needs a file called `target/` or
   `.DS_Store` cannot include it.
5. **No Unicode normalisation** (§4). Two paths that look identical on screen can produce two
   different hashes.

---

## 6. Test vectors

File: [`vectors/content-hash-vectors.json`](vectors/content-hash-vectors.json).
Real fixture: [`vectors/fixtures/poisoned_skill/`](vectors/fixtures/poisoned_skill/)
(salinan `pipeline/tests/poisoned_skill/`, supaya vector self-contained).

Shape of each entry:
`{id, description, files_note, files: [{path, content_b64}], expected_sha256,
expect_equal_to?, expect_differs_from?}`.
`content_b64` is base64 of the **raw** bytes, before normalisation — so CRLF and any other byte
survive the trip through JSON.

| id | contents | what it proves | `expected_sha256` |
|---|---|---|---|
| `single-file` | one `SKILL.md`, ASCII | the most basic path | `eaaad940…4d3d9edd` |
| `poisoned-token-drainer` | the real `manifest.json` from the poisoned fixture | the spec is bound to the real corpus | `c2bd4a31…28cc87f0` |
| `multi-file-ordering` | 3 files, insertion order != sorted order, nested paths, non-ASCII content | ordering and length prefixes are right | `e650ee53…b6c2ade6` |
| `non-bmp-path-order` | paths `Ａ.md` (U+FF21) vs `😀.md` (U+1F600) | ordering is **bytewise UTF-8**, not UTF-16 | `3b0f76b5…6cf78248` |
| `crlf-equals-lf` | logically the same content as `single-file`, using CRLF, a bare CR, and 3 trailing newlines | the hash is the **SAME** — normalisation works | `eaaad940…4d3d9edd` |
| `one-byte-flip` | `single-file` with one byte changed (`l` -> `L`) | the hash **DIFFERS** — the security claim holds | `dcf8d82b…4f89732b` |
| `concat-ambiguity-a` | `[("a","bc")]` | the length prefix prevents a collision | `9e858aa5…0dec5ae3` |
| `concat-ambiguity-b` | `[("ab","c")]` | its counterpart | `666e8c6e…0875de8e` |

The full hashes are in the vector file and in the runner's output.

`non-bmp-path-order` is the vector most likely to fail if someone rewrites the TypeScript side
with a plain `paths.sort()`: UTF-16 puts the emoji (high surrogate `0xD83D`) before `U+FF21`,
whereas bytewise UTF-8 puts `Ａ.md` (`EF BC A1`) before `😀.md` (`F0 9F 98 80`).

### Error cases

Nine cases (`err-empty-set`, `err-duplicate-path`, `err-not-utf8`, `err-absolute-path`,
`err-dot-prefix`, `err-dotdot`, `err-empty-path`, `err-backslash-separator`,
`err-double-slash`) in `error_cases[]`. All three implementations must reject with **exactly
the same error name**.

---

## 7. How to prove it (the runner)

```bash
bash scripts/verify-content-hash.sh      # or: make verify-spec
```

The runner:

1. runs Python, TypeScript and Rust over **the same vector file**;
2. compares all three reports **byte for byte** (`diff -u`) rather than merely printing them;
3. re-checks the invariants the ticket named: `crlf-equals-lf == single-file`,
   `one-byte-flip != single-file`, `concat-ambiguity-a != concat-ambiguity-b`, every `RELATION`
   `OK`, every `ERROR` not `NO_ERROR`, every hash 64 lowercase hex, and at least 5 vectors;
4. checks that `expected_sha256` in the vector file matches what was just computed (a
   hand-edited JSON cannot pass);
5. checks the directory packager: hashing `vectors/fixtures/poisoned_skill/` from disk must
   equal the `poisoned-token-drainer` vector.

**Exit 0 only when everything holds; otherwise exit 1** (exit 2 means the harness itself could
not run, for instance `cargo` is missing). The failure behaviour has been tested by deliberate
sabotage — changing one byte in the fixture, and hand-editing an `expected_sha256` — and both
exit 1.

The shared report format, identical in all three languages:

```
VECTOR   <id> <64-hex>
RELATION <id> equals|differs <other-id> OK|FAIL
ERROR    <id> <ErrorKind>|NO_ERROR
```

The Rust side prints the same lines with a `STERISH_HASH ` prefix from
`contracts/registry/src/test.rs`; the runner strips that prefix.

### Why Rust counts as an independent witness

The Rust test **does not read** `content-hash-vectors.json`. It hardcodes the vectors and the
expected hashes, and pulls the poisoned manifest through `include_bytes!` straight from the
fixture. It hashes with `env.crypto().sha256()` — the same host function the deployed contract
uses, not a userspace sha256 crate. So agreement between the three means something.

---

## 8. Using the reference implementations

```bash
# Hash a skill directory (packager + hash), print 64 hex
python3 docs/specs/reference/content_hash.py path/to/skill
npx tsx docs/specs/reference/contentHash.ts path/to/skill

# Run the shared vectors, print the report
python3 docs/specs/reference/content_hash.py --vectors
npx tsx docs/specs/reference/contentHash.ts --vectors

# Recompute expected_sha256 after DELIBERATELY changing a vector (rare!)
python3 docs/specs/reference/content_hash.py --regen
```

> `--regen` rewrites `expected_sha256`. Do not use it to "fix" a red runner — a red runner means
> an implementation has diverged, and regenerating only moves the lie into the vector file.

The API integrators use:

| Language | Function |
|---|---|
| Python | `content_hash(files) -> str`, `hash_dir(root) -> str`, `canonical_bytes(files) -> bytes` |
| TypeScript | `contentHash(files): string`, `hashDir(root): string`, `canonicalBytes(files): Uint8Array` |
| Rust (test) | `content_hash(&env, files) -> Result<String, HashError>` |

---

## 9. Change process

`content_hash` is already used as the `DataKey::HashIndex` key in the Registry. Changing the
algorithm **invalidates every verdict already on chain**.

Therefore:

1. This document is **frozen**. Typo fixes are fine; behavioural changes are not.
2. Any behavioural change means a new spec id `sterish-content-hash/v2`, a new MAGIC
   (`b"sterish-content-hash/v2\n"`), a new vector file, and an explicit migration plan for
   existing records.
3. Because MAGIC carries the version number, CANON v1 and v2 can never collide.
4. Every PR touching `docs/specs/reference/**`, `docs/specs/vectors/**`, or the
   `content_hash_v1` module in `contracts/registry/src/test.rs` **must** run `make verify-spec`
   and paste the output.
