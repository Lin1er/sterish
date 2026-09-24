"use client";

import { useState } from "react";

import { API_BASE_URL } from "@/lib/api";
import { RUG_PULL_SKILL, type RugPull as RugPullData } from "../liveStats";

/**
 * The hero, and the argument the whole page rests on.
 *
 * Not a headline with a gradient: the most characteristic object in this
 * product's world is a skill's identity, and the thesis is that identity is
 * the bytes and not the name. So the hero is the thing an agent looks at
 * before installing, and the reader flips it between two versions of one real
 * skill. The name does not move a pixel. The hash and the verdict do.
 *
 * That is CVE-2025-54136 rendered as an object rather than described: Cursor
 * remembered approval under an MCP entry's NAME, so swapping what it ran
 * needed no new prompt. A reader who sees the name hold still while the
 * verdict flips has understood the problem and the fix in one gesture.
 *
 * The data is live from the registry (see liveStats.ts), and the hash is set
 * large on purpose — it is the page's display type, because it is the thing
 * being argued about.
 */
export function RugPull({ data }: { data: RugPullData }) {
  const [poisoned, setPoisoned] = useState(false);
  const shown = poisoned ? data.dangerous : data.safe;

  return (
    <figure className="m-0">
      <div
        className="overflow-hidden rounded-xl border border-hairline bg-surface"
        style={{
          borderColor: poisoned ? "var(--danger-border)" : "var(--safe-border)",
          transition: "border-color 320ms ease",
        }}
      >
        {/* The name bar. Deliberately outside the flipping region: it is the
            one thing that must visibly not change. */}
        <div className="border-b border-hairline px-5 py-4">
          <p className="font-mono text-[11px] uppercase tracking-widest text-text-tertiary">
            Skill
          </p>
          <p className="mt-1 font-mono text-sm break-all text-text sm:text-base">
            {RUG_PULL_SKILL}
          </p>
        </div>

        <div
          className="px-5 py-5"
          style={{
            background: poisoned
              ? "var(--danger-surface)"
              : "var(--safe-surface)",
            transition: "background-color 320ms ease",
          }}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p
              className="flex items-center gap-2 text-lg font-semibold"
              style={{
                color: poisoned ? "var(--danger)" : "var(--safe)",
                transition: "color 320ms ease",
              }}
            >
              <Glyph poisoned={poisoned} />
              {shown.verdict}
            </p>
            <p className="font-mono text-xs text-text-secondary">
              v{shown.version} · trust {shown.trust_score}/100
            </p>
          </div>

          <p className="mt-4 font-mono text-[11px] uppercase tracking-widest text-text-tertiary">
            content hash
          </p>
          <p
            className="mt-1 font-mono text-[13px] leading-relaxed break-all sm:text-sm"
            style={{
              color: poisoned ? "var(--danger)" : "var(--safe)",
              transition: "color 320ms ease",
            }}
          >
            {shown.content_hash}
          </p>

          <p className="mt-4 text-sm text-text-secondary">
            {shown.is_verified
              ? "VERIFIED badge minted. An agent may install this version."
              : "No VERIFIED badge. The contract refuses to licence this version."}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-hairline px-5 py-3">
          <Toggle
            active={!poisoned}
            onClick={() => setPoisoned(false)}
            label={`v${data.safe.version}`}
          />
          <Toggle
            active={poisoned}
            onClick={() => setPoisoned(true)}
            label={`v${data.dangerous.version}`}
          />
          <a
            className="ml-auto font-mono text-xs text-keyword underline underline-offset-4 hover:no-underline"
            href={`${API_BASE_URL}/check/${RUG_PULL_SKILL}/${shown.version}`}
            target="_blank"
            rel="noreferrer"
          >
            check it yourself
          </a>
        </div>
      </div>

      <figcaption className="mt-3 text-sm text-text-secondary">
        One skill, two versions. The name never changes.{" "}
        {data.live ? (
          <span>Read live from the registry just now.</span>
        ) : (
          <span className="text-warning">
            The registry did not answer; showing a verified snapshot from 20 Sep
            2026.
          </span>
        )}
      </figcaption>
    </figure>
  );
}

function Toggle({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-md px-3 py-1.5 font-mono text-xs transition-colors ${
        active
          ? "bg-primary text-primary-foreground"
          : "border border-hairline-strong text-text-secondary hover:text-text"
      }`}
    >
      {label}
    </button>
  );
}

/** Verdict is never colour alone (docs/brand.md §2). */
function Glyph({ poisoned }: { poisoned: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d={poisoned ? "M5 5l10 10M15 5L5 15" : "M4 10.5l4 4 8-9"} />
    </svg>
  );
}
