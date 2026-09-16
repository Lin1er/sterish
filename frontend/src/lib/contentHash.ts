/**
 * `content_hash` v1 in the browser, so a user can check bytes before installing.
 *
 * A port of `docs/specs/reference/contentHash.ts`, the frozen reference that
 * `scripts/verify-content-hash.sh` holds identical to the Python and Rust
 * implementations. The algorithm is copied, not reinterpreted: if this file and
 * `docs/specs/content-hash.md` ever disagree, the spec wins and this file is the
 * bug. `contentHash.test.ts` runs the shared vectors against it to keep it that
 * way.
 *
 * Two differences from the reference, both forced by the browser:
 *
 * - sha256 comes from WebCrypto, which is async, so `contentHash` returns a
 *   promise. `node:crypto` does not exist here.
 * - There is no filesystem walk. The caller hands over files picked or dropped
 *   by the user, and `packageFiles` applies the packager's exclusion list
 *   (spec section 1.3) to them instead.
 */

const ENCODER = new TextEncoder();
const STRICT_UTF8 = new TextDecoder("utf-8", { fatal: true });

/** Domain separation prefix. 24 bytes, trailing newline included. */
export const MAGIC: Uint8Array = ENCODER.encode("sterish-content-hash/v1\n");

export type ContentHashErrorKind =
  | "EmptyFileSet"
  | "DuplicatePath"
  | "InvalidPath"
  | "NotUtf8";

export class ContentHashError extends Error {
  readonly kind: ContentHashErrorKind;

  constructor(kind: ContentHashErrorKind, message: string) {
    super(`${kind}: ${message}`);
    this.name = "ContentHashError";
    this.kind = kind;
  }
}

export interface SkillFile {
  /** Skill-root-relative POSIX path, as text. */
  path: string;
  /** Raw file bytes, before normalisation. */
  raw: Uint8Array;
}

function u32be(n: number): Uint8Array {
  if (!Number.isInteger(n) || n < 0 || n > 0xffff_ffff) {
    throw new Error(`value out of u32 range: ${n}`);
  }
  return new Uint8Array([
    (n >>> 24) & 0xff,
    (n >>> 16) & 0xff,
    (n >>> 8) & 0xff,
    n & 0xff,
  ]);
}

/**
 * Bytewise order on the raw UTF-8 path. Not `localeCompare` and not the default
 * string sort, which is UTF-16 code unit order and disagrees for non-BMP code
 * points (the `non-bmp-path-order` vector).
 */
function compareBytes(a: Uint8Array, b: Uint8Array): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
  }
  return a.length - b.length;
}

function isUtf8(bytes: Uint8Array): boolean {
  try {
    STRICT_UTF8.decode(bytes);
    return true;
  } catch {
    return false;
  }
}

function checkPath(path: string): void {
  if (path.length === 0) {
    throw new ContentHashError("InvalidPath", "empty path");
  }
  if (path.includes("\\")) {
    throw new ContentHashError(
      "InvalidPath",
      `backslash is not a path separator: ${path}`,
    );
  }
  if (path.includes("\0")) {
    throw new ContentHashError("InvalidPath", `NUL byte in path: ${path}`);
  }
  for (const part of path.split("/")) {
    if (part === "") {
      throw new ContentHashError(
        "InvalidPath",
        `empty path component (leading, trailing or double slash): ${path}`,
      );
    }
    if (part === "." || part === "..") {
      throw new ContentHashError(
        "InvalidPath",
        `'${part}' component not allowed: ${path}`,
      );
    }
  }
}

/**
 * (a) every CRLF to LF, (b) every remaining CR to LF, (c) strip all trailing
 * LF. Three literal passes so it maps line for line onto the spec text.
 */
export function normalizeContent(raw: Uint8Array): Uint8Array {
  if (!isUtf8(raw)) {
    throw new ContentHashError("NotUtf8", "content is not valid UTF-8");
  }
  const CR = 0x0d;
  const LF = 0x0a;

  const out = new Uint8Array(raw.length);
  let n = 0;
  for (let i = 0; i < raw.length; ) {
    if (raw[i] === CR && i + 1 < raw.length && raw[i + 1] === LF) {
      out[n++] = LF;
      i += 2;
    } else {
      out[n++] = raw[i];
      i += 1;
    }
  }
  for (let i = 0; i < n; i++) {
    if (out[i] === CR) out[i] = LF;
  }
  let end = n;
  while (end > 0 && out[end - 1] === LF) end--;
  return out.subarray(0, end);
}

export function canonicalBytes(files: SkillFile[]): Uint8Array {
  if (files.length === 0) {
    throw new ContentHashError(
      "EmptyFileSet",
      "a skill must contain at least one file",
    );
  }

  const seen = new Set<string>();
  const items = files.map((file) => {
    checkPath(file.path);
    if (seen.has(file.path)) {
      throw new ContentHashError(
        "DuplicatePath",
        `duplicate path: ${file.path}`,
      );
    }
    seen.add(file.path);
    return {
      pathBytes: ENCODER.encode(file.path),
      content: normalizeContent(file.raw),
    };
  });

  items.sort((a, b) => compareBytes(a.pathBytes, b.pathBytes));

  const chunks: Uint8Array[] = [MAGIC, u32be(items.length)];
  for (const item of items) {
    chunks.push(u32be(item.pathBytes.length), item.pathBytes);
    chunks.push(u32be(item.content.length), item.content);
  }
  const buf = new Uint8Array(chunks.reduce((sum, c) => sum + c.length, 0));
  let offset = 0;
  for (const chunk of chunks) {
    buf.set(chunk, offset);
    offset += chunk.length;
  }
  return buf;
}

/** 64 lowercase hex characters, exactly what `GET /check/by-hash` expects. */
export async function contentHash(files: SkillFile[]): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    canonicalBytes(files) as Uint8Array<ArrayBuffer>,
  );
  return Array.from(new Uint8Array(digest), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
}

const EXCLUDED_DIRS = new Set([
  ".git",
  "node_modules",
  "__pycache__",
  ".venv",
  "target",
]);
const EXCLUDED_FILES = new Set([".DS_Store"]);
const EXCLUDED_SUFFIXES = [".pyc"];

/**
 * Spec section 1.3: files the packager drops before hashing. They are not part
 * of the algorithm, so an uploaded folder that still contains `.git/` must have
 * it removed here or it would hash to bytes nobody ever audited.
 */
export function isExcludedPath(path: string): boolean {
  const parts = path.split("/");
  const name = parts[parts.length - 1];
  return (
    parts.slice(0, -1).some((dir) => EXCLUDED_DIRS.has(dir)) ||
    EXCLUDED_FILES.has(name) ||
    EXCLUDED_SUFFIXES.some((suffix) => name.endsWith(suffix))
  );
}

/**
 * Turn what a browser picker produced into skill-root-relative paths.
 *
 * A folder picked with `webkitdirectory` reports `webkitRelativePath` as
 * `<folder>/<path>`, and the folder name is not part of the skill: the
 * reference hashes paths relative to the skill root, so the first component is
 * removed. Loose files have no relative path and use their own name.
 */
export function relativeSkillPath(file: {
  name: string;
  webkitRelativePath?: string;
}): string {
  const relative = file.webkitRelativePath;
  if (!relative) return file.name;
  const slash = relative.indexOf("/");
  return slash === -1 ? relative : relative.slice(slash + 1);
}
