"use client";

import { FolderUp, Upload } from "lucide-react";
import { useRef, useState, type DragEvent, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, checkByHash, checkVersion } from "@/lib/api";
import { ContentHashError, contentHash } from "@/lib/contentHash";
import {
  CheckResult,
  type CheckQuery,
  type CheckState,
} from "./component/CheckResult";
import { SkillVersionPicker } from "./component/SkillVersionPicker";
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

/**
 * Fields get the same breathing room as the mode pills above them: text never
 * sits against the border. The shadcn defaults (h-8, px-2.5) are sized for
 * dense toolbars, not for a form somebody pastes a 64-character hash into.
 */
const FIELD = "mt-2 h-11 px-4 font-mono text-sm md:text-sm";
const LABEL = "text-xs text-text-tertiary";

export function Check() {
  const [mode, setMode] = useState<Mode>("files");
  const [state, setState] = useState<CheckState>({ status: "idle" });
  const [dragging, setDragging] = useState(false);
  const folderInput = useRef<HTMLInputElement>(null);
  const filesInput = useRef<HTMLInputElement>(null);

  const [pastePath, setPastePath] = useState("SKILL.md");
  const [pasteText, setPasteText] = useState("");
  const [hash, setHash] = useState("");
  const [skillId, setSkillId] = useState<string | null>(null);
  const [version, setVersion] = useState<string | null>(null);

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
    if (!skillId || !version) return;
    void ask({ by: "name", skillId, version });
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
              onClick={() => {
                if (m.id === mode || busy) return;
                setMode(m.id);
                // An answer belongs to the question under it. Left in place, a
                // SAFE from the paste form reads as the verdict for whatever
                // is typed into the next form.
                setState({ status: "idle" });
              }}
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

      <div className="mt-5">
        {mode === "files" ? (
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            // Tall enough to be an obvious target, filling what is left of the
            // screen under the heading and tabs. A literal min-h-screen would
            // push the footer and the result below the fold before anything
            // has been dropped.
            className={`flex min-h-[max(20rem,calc(100dvh-30rem))] flex-col items-center justify-center rounded-lg border border-dashed px-6 py-12 text-center transition-colors ${
              dragging
                ? "border-keyword bg-elevated"
                : "border-hairline-strong bg-surface"
            }`}
          >
            <FolderUp className="size-8 text-text-tertiary" aria-hidden />
            <p className="mt-4 text-base text-text">
              Drop a skill folder or its files here
            </p>
            <p className="mt-2 max-w-xl text-xs text-text-tertiary">
              .git, node_modules, __pycache__, .venv, target, .DS_Store and .pyc
              files are left out, as the packager does before hashing
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <Button
                variant="outline"
                size="lg"
                className="px-4"
                disabled={busy}
                onClick={() => folderInput.current?.click()}
              >
                <FolderUp data-icon="inline-start" />
                Choose a folder
              </Button>
              <Button
                variant="outline"
                size="lg"
                className="px-4"
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
          <form onSubmit={onPaste} className="space-y-5">
            <div>
              <label htmlFor="check-paste-path" className={LABEL}>
                Path inside the skill
              </label>
              <Input
                id="check-paste-path"
                className={FIELD}
                value={pastePath}
                onChange={(event) => setPastePath(event.target.value)}
                spellCheck={false}
                required
              />
            </div>
            <div>
              <label htmlFor="check-paste-text" className={LABEL}>
                File contents
              </label>
              <Textarea
                id="check-paste-text"
                className="mt-2 min-h-60 resize-y px-4 py-3 font-mono text-sm leading-relaxed md:text-sm"
                value={pasteText}
                onChange={(event) => setPasteText(event.target.value)}
                spellCheck={false}
                placeholder="# My skill"
              />
              <p className="mt-2 text-xs text-text-tertiary">
                For a skill that is a single file. The path is part of the
                hash, so it must match the name the file has in the skill.
              </p>
            </div>
            <Button
              type="submit"
              size="lg"
              className="px-4"
              disabled={busy || pastePath.trim() === ""}
            >
              Check this file
            </Button>
          </form>
        ) : null}

        {mode === "hash" ? (
          <form onSubmit={onHash} className="space-y-5">
            <div>
              <label htmlFor="check-hash" className={LABEL}>
                content_hash, 64 lowercase hex characters
              </label>
              <Input
                id="check-hash"
                className={FIELD}
                value={hash}
                onChange={(event) => setHash(event.target.value)}
                spellCheck={false}
                autoComplete="off"
                aria-invalid={hashProblem !== null}
                placeholder="c2bd4a316415b4919e3f1f40d9925f4052d020cf3dc2ecabe0e7c9dd28cc87f0"
              />
              {hashProblem ? (
                <p className="mt-2 text-xs text-danger">{hashProblem}</p>
              ) : null}
            </div>
            <Button
              type="submit"
              size="lg"
              className="px-4"
              disabled={busy || trimmedHash === "" || hashProblem !== null}
            >
              Check this hash
            </Button>
          </form>
        ) : null}

        {mode === "name" ? (
          <form onSubmit={onName} className="space-y-5">
            <SkillVersionPicker
              skillId={skillId}
              version={version}
              onSkillChange={setSkillId}
              onVersionChange={setVersion}
              disabled={busy}
            />
            <Button
              type="submit"
              size="lg"
              className="px-4"
              disabled={busy || !skillId || !version}
            >
              Check this version
            </Button>
          </form>
        ) : null}
      </div>

      <section aria-live="polite" className="mt-8">
        <CheckResult state={state} />
      </section>
    </div>
  );
}
