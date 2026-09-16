import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  ContentHashError,
  contentHash,
  isExcludedPath,
  relativeSkillPath,
  type SkillFile,
} from "./contentHash";

/**
 * The dashboard's hash must be byte-identical to the one the pipeline wrote on
 * chain, or a check-before-install answers about bytes nobody audited. These
 * are the same vectors `scripts/verify-content-hash.sh` runs against the
 * Python, TypeScript and Rust references, read from the spec folder rather than
 * copied, so a regenerated vector file cannot drift away from this test.
 */

interface VectorFile {
  path: string;
  content_b64: string;
}

interface VectorDoc {
  vectors: Array<{
    id: string;
    files: VectorFile[];
    expected_sha256?: string;
    expect_equal_to?: string[];
    expect_differs_from?: string[];
  }>;
  error_cases: Array<{ id: string; files: VectorFile[]; expect_error: string }>;
}

const VECTORS: VectorDoc = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL(
        "../../../docs/specs/vectors/content-hash-vectors.json",
        import.meta.url,
      ),
    ),
    "utf8",
  ),
);

function filesOf(files: VectorFile[]): SkillFile[] {
  return files.map((f) => ({
    path: f.path,
    raw: new Uint8Array(Buffer.from(f.content_b64, "base64")),
  }));
}

describe("the shared content-hash vectors", () => {
  it("has vectors to run, so an empty file cannot pass silently", () => {
    expect(VECTORS.vectors.length).toBeGreaterThan(0);
    expect(VECTORS.error_cases.length).toBeGreaterThan(0);
  });

  for (const vector of VECTORS.vectors.filter((v) => v.expected_sha256)) {
    it(`hashes ${vector.id} exactly as the reference does`, async () => {
      await expect(contentHash(filesOf(vector.files))).resolves.toBe(
        vector.expected_sha256,
      );
    });
  }

  it("keeps every equal and differs relation the vectors declare", async () => {
    const hashes = new Map<string, string>();
    for (const vector of VECTORS.vectors) {
      hashes.set(vector.id, await contentHash(filesOf(vector.files)));
    }
    for (const vector of VECTORS.vectors) {
      for (const other of vector.expect_equal_to ?? []) {
        expect(hashes.get(vector.id), `${vector.id} = ${other}`).toBe(
          hashes.get(other),
        );
      }
      for (const other of vector.expect_differs_from ?? []) {
        expect(hashes.get(vector.id), `${vector.id} != ${other}`).not.toBe(
          hashes.get(other),
        );
      }
    }
  });

  for (const errorCase of VECTORS.error_cases) {
    it(`refuses ${errorCase.id} with ${errorCase.expect_error}`, async () => {
      const outcome = await contentHash(filesOf(errorCase.files)).catch(
        (cause: unknown) => cause,
      );
      expect(outcome).toBeInstanceOf(ContentHashError);
      expect((outcome as ContentHashError).kind).toBe(errorCase.expect_error);
    });
  }
});

describe("packaging what a browser picker hands over", () => {
  it("drops the folder name a directory picker prefixes", () => {
    expect(
      relativeSkillPath({
        name: "zeta.py",
        webkitRelativePath: "my-skill/tools/zeta.py",
      }),
    ).toBe("tools/zeta.py");
  });

  it("uses the file name for a loose file", () => {
    expect(
      relativeSkillPath({ name: "SKILL.md", webkitRelativePath: "" }),
    ).toBe("SKILL.md");
    expect(relativeSkillPath({ name: "SKILL.md" })).toBe("SKILL.md");
  });

  it("excludes what the packager excludes, at any depth", () => {
    expect(isExcludedPath(".git/config")).toBe(true);
    expect(isExcludedPath("tools/node_modules/x/index.js")).toBe(true);
    expect(isExcludedPath("tools/__pycache__/a.cpython-312.pyc")).toBe(true);
    expect(isExcludedPath("lib/helper.pyc")).toBe(true);
    expect(isExcludedPath("docs/.DS_Store")).toBe(true);
  });

  it("keeps files that only look like excluded names", () => {
    expect(isExcludedPath("SKILL.md")).toBe(false);
    expect(isExcludedPath("target.md")).toBe(false);
    expect(isExcludedPath("git/notes.md")).toBe(false);
    expect(isExcludedPath("tools/helper.pyc.md")).toBe(false);
  });
});
