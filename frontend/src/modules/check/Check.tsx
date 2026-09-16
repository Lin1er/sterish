"use client";

import { FolderUp, Upload } from "lucide-react";
import { useRef, useState, type DragEvent, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, checkByHash, checkVersion } from "@/lib/api";
import { ContentHashError, contentHash } from "@/lib/contentHash";
import {
  CheckResult,
  type CheckQuery,
  type CheckState,
} from "./component/CheckResult";
import { packageDrop, packageFileList, type PackagedFiles } from "./readFiles";

type Mode = "files" | "paste" | "hash" | "name";

/**
 * Files first, because it is the only mode that answers the question somebody
 * about to install actually has: are the bytes in front of me the bytes that
 * were audited? Hash is the same question for somebody who already computed
 * it. Name is last and says so, since it trusts the name.
 */
const MODES: Array<{ id: Mode; label: string }> = [
  { id: "files", label: "Files" },
  { id: "paste", label: "Paste" },
  { id: "hash", label: "Content hash" },
  { id: "name", label: "Name and version" },
];

const HASH = /^[0-9a-f]{64}$/;

const INPUT =
  "w-full rounded-lg border border-input bg-bg-deep px-3 py-2 font-mono text-sm text-text placeholder:text-text-tertiary focus-visible:border-keyword focus-visible:outline-none";

export function Check() {
  const [mode, setMode] = useState<Mode>("files");
  const [state, setState] = useState<CheckState>({ status: "idle" });
  const [dragging, setDragging] = useState(false);
  const folderInput = useRef<HTMLInputElement>(null);
  const filesInput = useRef<HTMLInputElement>(null);

  const [pastePath, setPastePath] = useState("SKILL.md");
  const [pasteText, setPasteText] = useState("");
  const [hash, setHash] = useState("");
  const [skillId, setSkillId] = useState("");
  const [version, setVersion] = useState("");

  const busy = state.status === "working";

  async function ask(query: CheckQuery) {
    setState({ status: "working", label: "Asking the registry..." });
    try {
      const result =
        query.by === "name"
          ? await checkVersion(query.skillId, query.version)
          : await checkByHash(query.hash);
      setState({ status: "answered", query, result });
    } catch (cause) {
      if (!(cause instanceof ApiError)) throw cause;
      setState(
        cause.isNotFound
          ? { status: "unknown", query, error: cause }
          : { status: "failed", error: cause },
      );
    }
  }

  async function checkPackaged(read: () => Promise<PackagedFiles>) {
    setState({
      status: "working",
      label: "Hashing the files in your browser...",
    });
    let packaged: PackagedFiles;
    let digest: string;
    try {
      packaged = await read();
      digest = await contentHash(packaged.files);
    } catch (cause) {
      if (!(cause instanceof ContentHashError)) throw cause;
      setState({ status: "unhashable", error: cause });
      return;
    }
    await ask({
      by: "files",
      hash: digest,
      files: packaged.files.map((f) => f.path).sort(),
      excluded: packaged.excluded,
    });
  }

  function onPicked(list: FileList | null) {
    if (!list || list.length === 0) return;
    void checkPackaged(() => packageFileList(list));
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (busy) return;
    // packageDrop takes the entries before its first await, which is what keeps
    // them readable after this handler returns.
    const packaging = packageDrop(event.dataTransfer.items);
    void checkPackaged(() => packaging);
  }

  function onPaste(event: FormEvent) {
    event.preventDefault();
    const path = pastePath.trim();
    void checkPackaged(async () => ({
      files: [{ path, raw: new TextEncoder().encode(pasteText) }],
      excluded: [],
    }));
  }

  function onHash(event: FormEvent) {
    event.preventDefault();
    void ask({ by: "hash", hash: hash.trim() });
  }

  function onName(event: FormEvent) {
    event.preventDefault();
    void ask({ by: "name", skillId: skillId.trim(), version: version.trim() });
  }

  const trimmedHash = hash.trim();
  // Uppercase is refused rather than lowercased. The API rejects it too (spec
  // 3.1), on the grounds that whatever produced it has a bug worth seeing.
  const hashProblem =
    trimmedHash === "" || HASH.test(trimmedHash)
      ? null
      : /^[0-9a-fA-F]{64}$/.test(trimmedHash)
        ? "Use lowercase hex. Content hashes are always written in lowercase."
        : `A content hash is exactly 64 hex characters; this is ${trimmedHash.length}.`;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-12">
      <h2 className="text-lg font-bold tracking-wider">Check before install</h2>
      <p className="mt-2 max-w-2xl text-sm text-text-secondary">
        A verdict belongs to exact bytes. Give the files you are about to
        install and they are hashed here, in your browser, then looked up on
        chain. Nothing is uploaded.
      </p>

      <div
        role="tablist"
        aria-label="What to check"
        className="mt-6 flex flex-wrap gap-2"
      >
        {MODES.map((m) => {
          const active = m.id === mode;
          return (
            <button
              key={m.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setMode(m.id)}
              className={
                active
                  ? "rounded-4xl border border-hairline-strong bg-elevated px-3 py-1 text-sm text-text"
                  : "rounded-4xl border border-border px-3 py-1 text-sm text-text-secondary transition-colors hover:border-hairline-strong hover:text-text"
              }
            >
              {m.label}
            </button>
          );
        })}
      </div>

      <div className="mt-4 max-w-3xl">
        {mode === "files" ? (
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`rounded-lg border border-dashed px-5 py-8 text-center transition-colors ${
              dragging
                ? "border-keyword bg-elevated"
                : "border-hairline-strong bg-surface"
            }`}
          >
            <p className="text-sm text-text">
              Drop a skill folder or its files here
            </p>
            <p className="mt-1 text-xs text-text-tertiary">
              .git, node_modules, __pycache__, .venv, target, .DS_Store and .pyc
              files are left out, as the packager does before hashing
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => folderInput.current?.click()}
              >
                <FolderUp data-icon="inline-start" />
                Choose a folder
              </Button>
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => filesInput.current?.click()}
              >
                <Upload data-icon="inline-start" />
                Choose files
              </Button>
            </div>
            {/* webkitdirectory is not in React's attribute types, so it is
                spread in rather than written as a typed prop. */}
            <input
              ref={folderInput}
              type="file"
              className="hidden"
              {...{ webkitdirectory: "" }}
              onChange={(event) => {
                onPicked(event.target.files);
                event.target.value = "";
              }}
            />
            <input
              ref={filesInput}
              type="file"
              multiple
              className="hidden"
              onChange={(event) => {
                onPicked(event.target.files);
                event.target.value = "";
              }}
            />
          </div>
        ) : null}

        {mode === "paste" ? (
          <form onSubmit={onPaste} className="space-y-3">
            <label className="block">
              <span className="text-xs text-text-tertiary">
                Path inside the skill
              </span>
              <input
                className={`${INPUT} mt-1`}
                value={pastePath}
                onChange={(event) => setPastePath(event.target.value)}
                spellCheck={false}
                required
              />
            </label>
            <label className="block">
              <span className="text-xs text-text-tertiary">File contents</span>
              <textarea
                className={`${INPUT} mt-1 min-h-48 resize-y`}
                value={pasteText}
                onChange={(event) => setPasteText(event.target.value)}
                spellCheck={false}
                placeholder="# My skill"
              />
            </label>
            <p className="text-xs text-text-tertiary">
              For a skill that is a single file. The path is part of the hash,
              so it must match the name the file has in the skill.
            </p>
            <Button type="submit" disabled={busy || pastePath.trim() === ""}>
              Check this file
            </Button>
          </form>
        ) : null}

        {mode === "hash" ? (
          <form onSubmit={onHash} className="space-y-3">
            <label className="block">
              <span className="text-xs text-text-tertiary">
                content_hash, 64 lowercase hex characters
              </span>
              <input
                className={`${INPUT} mt-1`}
                value={hash}
                onChange={(event) => setHash(event.target.value)}
                spellCheck={false}
                autoComplete="off"
                aria-invalid={hashProblem !== null}
                placeholder="c2bd4a316415b4919e3f1f40d9925f4052d020cf3dc2ecabe0e7c9dd28cc87f0"
              />
            </label>
            {hashProblem ? (
              <p className="text-xs text-danger">{hashProblem}</p>
            ) : null}
            <Button
              type="submit"
              disabled={busy || trimmedHash === "" || hashProblem !== null}
            >
              Check this hash
            </Button>
          </form>
        ) : null}

        {mode === "name" ? (
          <form onSubmit={onName} className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
              <label className="block">
                <span className="text-xs text-text-tertiary">Skill id</span>
                <input
                  className={`${INPUT} mt-1`}
                  value={skillId}
                  onChange={(event) => setSkillId(event.target.value)}
                  spellCheck={false}
                  autoComplete="off"
                  placeholder="com.acme.pdf-suite"
                  required
                />
              </label>
              <label className="block">
                <span className="text-xs text-text-tertiary">Version</span>
                <input
                  className={`${INPUT} mt-1`}
                  value={version}
                  onChange={(event) => setVersion(event.target.value)}
                  spellCheck={false}
                  autoComplete="off"
                  placeholder="1.0.0"
                  required
                />
              </label>
            </div>
            <Button
              type="submit"
              disabled={busy || skillId.trim() === "" || version.trim() === ""}
            >
              Check this version
            </Button>
          </form>
        ) : null}
      </div>

      <section aria-live="polite" className="mt-8 max-w-3xl">
        <CheckResult state={state} />
      </section>
    </div>
  );
}
