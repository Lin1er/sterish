#!/usr/bin/env -S npx tsx
/**
 * Sterish canonical `content_hash` v1 — reference implementation (TypeScript).
 *
 * Normative spec: `docs/specs/content-hash.md`. If this file and the spec ever
 * disagree, the spec wins and this file is the bug.
 *
 * CLI:
 *   npx tsx contentHash.ts <dir>              # hash a skill directory, print 64 hex chars
 *   npx tsx contentHash.ts --vectors [path]   # run the shared test vectors, print report lines
 *
 * The `--vectors` report is byte-for-byte comparable with the Python and Rust
 * reference implementations; `scripts/verify-content-hash.sh` diffs them.
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Domain-separation prefix. 24 bytes, trailing newline included. */
export const MAGIC: Uint8Array = new TextEncoder().encode("sterish-content-hash/v1\n");
if (MAGIC.length !== 24) throw new Error("MAGIC must be exactly 24 bytes");

const EXCLUDED_DIRS = new Set([".git", "node_modules", "__pycache__", ".venv", "target"]);
const EXCLUDED_FILES = new Set([".DS_Store"]);
const EXCLUDED_SUFFIXES = [".pyc"];

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export type ErrorKind = "EmptyFileSet" | "DuplicatePath" | "InvalidPath" | "NotUtf8";

export class ContentHashError extends Error {
  constructor(public readonly kind: ErrorKind, message: string) {
    super(`${kind}: ${message}`);
    this.name = "ContentHashError";
  }
}

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------

export interface SkillFile {
  /** UTF-8 bytes of the skill-root-relative POSIX path. */
  pathBytes: Uint8Array;
  /** Raw file bytes, BEFORE normalization. */
  raw: Uint8Array;
}

/** Unsigned 32-bit big-endian length prefix. */
export function u32be(n: number): Uint8Array {
  if (!Number.isInteger(n) || n < 0 || n > 0xffff_ffff) {
    throw new Error(`value out of u32 range: ${n}`);
  }
  return new Uint8Array([(n >>> 24) & 0xff, (n >>> 16) & 0xff, (n >>> 8) & 0xff, n & 0xff]);
}

/**
 * ASC bytewise comparison on RAW bytes.
 * Deliberately NOT `String.prototype.localeCompare` and NOT the default
 * `Array.prototype.sort()` on strings — that is UTF-16 code-unit order, which
 * disagrees with UTF-8 byte order for non-BMP code points (see the
 * `non-bmp-path-order` vector).
 */
export function compareBytes(a: Uint8Array, b: Uint8Array): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
  }
  return a.length === b.length ? 0 : a.length < b.length ? -1 : 1;
}

const STRICT_UTF8 = new TextDecoder("utf-8", { fatal: true });

function isUtf8(bytes: Uint8Array): boolean {
  try {
    STRICT_UTF8.decode(bytes);
    return true;
  } catch {
    return false;
  }
}

export function checkPath(pathBytes: Uint8Array): void {
  if (pathBytes.length === 0) throw new ContentHashError("InvalidPath", "empty path");
  if (!isUtf8(pathBytes)) throw new ContentHashError("InvalidPath", "path is not valid UTF-8");
  const text = STRICT_UTF8.decode(pathBytes);
  if (text.includes("\\")) {
    throw new ContentHashError("InvalidPath", `backslash is not a path separator: ${text}`);
  }
  if (text.includes("\0")) {
    throw new ContentHashError("InvalidPath", `NUL byte in path: ${text}`);
  }
  for (const part of text.split("/")) {
    if (part === "") {
      throw new ContentHashError(
        "InvalidPath",
        `empty path component (leading/trailing/double slash): ${text}`,
      );
    }
    if (part === ".") throw new ContentHashError("InvalidPath", `'.' component not allowed: ${text}`);
    if (part === "..") throw new ContentHashError("InvalidPath", `'..' component not allowed: ${text}`);
  }
}

/**
 * Step (a) every CRLF -> LF, step (b) every remaining CR -> LF, step (c) strip
 * ALL trailing LF. Written as three literal passes so it maps 1:1 onto the
 * spec text; do not "optimize" it into a single pass without re-running
 * scripts/verify-content-hash.sh.
 */
export function normalizeContent(raw: Uint8Array): Uint8Array {
  if (!isUtf8(raw)) throw new ContentHashError("NotUtf8", "content is not valid UTF-8");

  const CR = 0x0d;
  const LF = 0x0a;

  // (a) CRLF -> LF (leftmost, non-overlapping).
  const stepA = new Uint8Array(raw.length);
  let n = 0;
  for (let i = 0; i < raw.length; ) {
    if (raw[i] === CR && i + 1 < raw.length && raw[i + 1] === LF) {
      stepA[n++] = LF;
      i += 2;
    } else {
      stepA[n++] = raw[i];
      i += 1;
    }
  }

  // (b) remaining CR -> LF.
  for (let i = 0; i < n; i++) {
    if (stepA[i] === CR) stepA[i] = LF;
  }

  // (c) strip all trailing LF.
  let end = n;
  while (end > 0 && stepA[end - 1] === LF) end--;
  return stepA.subarray(0, end);
}

export function canonicalBytes(files: SkillFile[]): Uint8Array {
  if (files.length === 0) {
    throw new ContentHashError("EmptyFileSet", "a skill must contain at least one file");
  }

  const seen = new Set<string>();
  const items: Array<{ pathBytes: Uint8Array; content: Uint8Array }> = [];
  for (const f of files) {
    checkPath(f.pathBytes);
    const key = Array.from(f.pathBytes).join(",");
    if (seen.has(key)) {
      throw new ContentHashError("DuplicatePath", `duplicate path: ${STRICT_UTF8.decode(f.pathBytes)}`);
    }
    seen.add(key);
    items.push({ pathBytes: f.pathBytes, content: normalizeContent(f.raw) });
  }

  items.sort((a, b) => compareBytes(a.pathBytes, b.pathBytes));

  const chunks: Uint8Array[] = [MAGIC, u32be(items.length)];
  for (const item of items) {
    chunks.push(u32be(item.pathBytes.length), item.pathBytes);
    chunks.push(u32be(item.content.length), item.content);
  }
  const total = chunks.reduce((acc, c) => acc + c.length, 0);
  const buf = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) {
    buf.set(c, off);
    off += c.length;
  }
  return buf;
}

/** 64 lowercase hex chars. */
export function contentHash(files: SkillFile[]): string {
  return createHash("sha256").update(canonicalBytes(files)).digest("hex");
}

// ---------------------------------------------------------------------------
// Directory packager
// ---------------------------------------------------------------------------

export function collectDir(root: string): SkillFile[] {
  const encoder = new TextEncoder();
  const out: SkillFile[] = [];
  const walk = (dir: string, relParts: string[]): void => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) =>
      a.name < b.name ? -1 : a.name > b.name ? 1 : 0,
    )) {
      if (entry.isDirectory()) {
        if (EXCLUDED_DIRS.has(entry.name)) continue;
        walk(path.join(dir, entry.name), [...relParts, entry.name]);
      } else if (entry.isFile()) {
        if (EXCLUDED_FILES.has(entry.name)) continue;
        if (EXCLUDED_SUFFIXES.some((s) => entry.name.endsWith(s))) continue;
        const rel = [...relParts, entry.name].join("/");
        out.push({
          pathBytes: encoder.encode(rel),
          raw: new Uint8Array(fs.readFileSync(path.join(dir, entry.name))),
        });
      }
    }
  };
  walk(path.resolve(root), []);
  return out;
}

export function hashDir(root: string): string {
  return contentHash(collectDir(root));
}

// ---------------------------------------------------------------------------
// Test-vector runner (shared report format)
// ---------------------------------------------------------------------------

interface VectorFile {
  path: string;
  content_b64: string;
}
interface Vector {
  id: string;
  files: VectorFile[];
  expected_sha256?: string;
  expect_equal_to?: string[];
  expect_differs_from?: string[];
}
interface ErrorCase {
  id: string;
  files: VectorFile[];
  expect_error: ErrorKind;
}
interface VectorDoc {
  vectors: Vector[];
  error_cases: ErrorCase[];
}

function filesOf(v: { files: VectorFile[] }): SkillFile[] {
  const encoder = new TextEncoder();
  return v.files.map((f) => ({
    pathBytes: encoder.encode(f.path),
    raw: new Uint8Array(Buffer.from(f.content_b64, "base64")),
  }));
}

function runVectors(vectorPath: string): number {
  const doc: VectorDoc = JSON.parse(fs.readFileSync(vectorPath, "utf8"));
  const lines: string[] = [];
  const problems: string[] = [];
  const hashes = new Map<string, string>();

  for (const v of doc.vectors) {
    const got = contentHash(filesOf(v));
    hashes.set(v.id, got);
    lines.push(`VECTOR ${v.id} ${got}`);
    if (v.expected_sha256 && v.expected_sha256 !== got) {
      problems.push(`${v.id}: expected ${v.expected_sha256}, computed ${got}`);
    }
  }

  for (const v of doc.vectors) {
    for (const other of v.expect_equal_to ?? []) {
      const ok = hashes.get(v.id) === hashes.get(other);
      lines.push(`RELATION ${v.id} equals ${other} ${ok ? "OK" : "FAIL"}`);
      if (!ok) problems.push(`${v.id} must equal ${other} but does not`);
    }
    for (const other of v.expect_differs_from ?? []) {
      const ok = hashes.get(v.id) !== hashes.get(other);
      lines.push(`RELATION ${v.id} differs ${other} ${ok ? "OK" : "FAIL"}`);
      if (!ok) problems.push(`${v.id} must differ from ${other} but does not`);
    }
  }

  for (const c of doc.error_cases) {
    let gotKind = "NO_ERROR";
    try {
      contentHash(filesOf(c));
    } catch (e) {
      gotKind = e instanceof ContentHashError ? e.kind : `UNEXPECTED(${String(e)})`;
    }
    lines.push(`ERROR ${c.id} ${gotKind}`);
    if (gotKind !== c.expect_error) {
      problems.push(`${c.id}: expected error ${c.expect_error}, got ${gotKind}`);
    }
  }

  process.stdout.write(lines.join("\n") + "\n");
  for (const p of problems) process.stderr.write(`typescript: ${p}\n`);
  return problems.length > 0 ? 1 : 0;
}

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_VECTORS = path.join(HERE, "..", "vectors", "content-hash-vectors.json");

function main(argv: string[]): number {
  if (argv[0] === "--vectors") return runVectors(argv[1] ?? DEFAULT_VECTORS);
  if (argv.length !== 1 || argv[0] === "-h" || argv[0] === "--help") {
    process.stderr.write("usage: contentHash.ts <dir> | --vectors [vectors.json]\n");
    return 2;
  }
  process.stdout.write(hashDir(argv[0]) + "\n");
  return 0;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  process.exit(main(process.argv.slice(2)));
}
