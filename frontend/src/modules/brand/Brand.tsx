"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

import { COLOR_GROUPS, FONTS, RADII, VERDICTS, type Swatch } from "./tokenData";
import { contrastRatio, resolveToken, threshold, verdict } from "./contrast";

/**
 * The living reference for the Sterish design tokens (STE-7).
 *
 * This page is deliberately NOT a copy of the palette. Every swatch paints
 * itself with `var(--token)` and reads the resolved value back out of the DOM,
 * and every contrast figure is recomputed in the browser. Change a value in
 * `app/globals.css` and this page changes with it; rename a token and it shows
 * up here as unresolved instead of as a stale-but-plausible colour.
 *
 * It is not in NavTabs. This is a reference for the people building Sterish,
 * not a destination for people evaluating a skill, and the product nav is
 * deliberately short (see NavTabs). Reach it at /brand.
 */
export function Brand() {
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
      <Header />
      <Logo />
      {COLOR_GROUPS.map((group) => (
        <ColorGroup key={group.id} {...group} />
      ))}
      <Verdicts />
      <Typography />
      <Radii />
      <Footer />
    </main>
  );
}

function Header() {
  return (
    <header className="mb-12 border-b border-hairline pb-8">
      <p className="font-mono text-xs uppercase tracking-widest text-tan">
        STE-7 · brand
      </p>
      <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">
        Sterish design tokens
      </h1>
      <p className="mt-4 max-w-2xl text-text-secondary">
        Five brand values — <Mono>#122C4F</Mono> navy, <Mono>#FBF9E4</Mono>{" "}
        cream, and three accents — with everything else derived from them, so
        changing one changes the app rather than one component. The written
        rules live in <Mono>docs/brand.md</Mono>; this page is the visual half,
        and it reads the real tokens rather than a copy of them.
      </p>
      <p className="mt-4 max-w-2xl rounded-lg border border-hairline bg-surface p-4 text-sm text-text-secondary">
        <strong className="text-text">Two rules.</strong> Never write a raw hex,
        font name or pixel value in a component — if the value you need is
        missing, add a token. And verdict is never communicated by colour alone:
        every verdict surface pairs the colour with an icon and the verdict
        word.
      </p>
    </header>
  );
}

function Logo() {
  return (
    <Section
      title="Logo"
      blurb="Two forms. The lockup is the default; the mark stands alone only where the name is already present or the space is square."
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Frame label="Lockup, cream — on navy" tone="bg">
          <Image
            src="/brand/logo/sterish-lockup-cream.svg"
            alt="Sterish lockup in cream"
            width={692}
            height={138}
            className="w-full max-w-xs"
            priority
          />
        </Frame>
        <Frame label="Lockup, navy — on cream" tone="cream">
          <Image
            src="/brand/logo/sterish-lockup-navy.svg"
            alt="Sterish lockup in navy"
            width={692}
            height={138}
            className="w-full max-w-xs"
          />
        </Frame>
        <Frame label="Mark, cream — on navy" tone="bg">
          <Image
            src="/brand/logo/sterish-mark-cream.svg"
            alt="Sterish mark in cream"
            width={400}
            height={400}
            className="w-40"
          />
        </Frame>
        <Frame label="Mark, navy — on cream" tone="cream">
          <Image
            src="/brand/logo/sterish-mark-navy.svg"
            alt="Sterish mark in navy"
            width={400}
            height={400}
            className="w-40"
          />
        </Frame>
      </div>

      <div className="mt-4 rounded-lg border border-warning-border bg-warning-surface p-4 text-sm">
        <p className="font-medium text-warning">
          The mark is a wide band, not a square.
        </p>
        <p className="mt-2 text-text-secondary">
          Measured on a 1024px render, the artwork occupies{" "}
          <Mono>1024×198</Mono> of the square canvas — a 5.2:1 band, full-bleed
          horizontally, with ~40% empty space above and below. Dropped straight
          into an avatar it becomes an illegible sliver. Square placements use{" "}
          <Mono>sterish-avatar-navy-tight-1024.png</Mono>, which crops to the
          lens. Details in <Mono>docs/brand.md</Mono>.
        </p>
      </div>
    </Section>
  );
}

function ColorGroup({
  title,
  blurb,
  swatches,
}: {
  title: string;
  blurb: string;
  swatches: Swatch[];
}) {
  return (
    <Section title={title} blurb={blurb}>
      <div className="overflow-hidden rounded-lg border border-hairline">
        <table className="w-full text-left text-sm">
          <thead className="bg-elevated text-xs uppercase tracking-wide text-text-tertiary">
            <tr>
              <th className="px-4 py-3 font-medium">Swatch</th>
              <th className="px-4 py-3 font-medium">Token</th>
              <th className="px-4 py-3 font-medium">Value</th>
              <th className="px-4 py-3 font-medium">Contrast</th>
              <th className="hidden px-4 py-3 font-medium sm:table-cell">Use</th>
            </tr>
          </thead>
          <tbody>
            {swatches.map((s) => (
              <SwatchRow key={s.name} swatch={s} />
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function SwatchRow({ swatch }: { swatch: Swatch }) {
  const ref = useRef<HTMLTableRowElement>(null);
  const [value, setValue] = useState<string>("");
  const [ratio, setRatio] = useState<number | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fg = resolveToken(swatch.name, el);
    const bg = resolveToken(swatch.against ?? "bg", el);
    setValue(toHex(fg));
    setRatio(contrastRatio(fg, bg));
  }, [swatch.name, swatch.against]);

  const role = swatch.role ?? "body";
  const v = verdict(ratio, role);

  return (
    <tr ref={ref} className="border-t border-hairline">
      <td className="px-4 py-3">
        <span
          className="block h-8 w-14 rounded border border-hairline-strong"
          style={{ background: `var(--${swatch.name})` }}
        />
      </td>
      <td className="px-4 py-3">
        <Mono>--{swatch.name}</Mono>
      </td>
      <td className="px-4 py-3">
        <Mono>{value || "…"}</Mono>
      </td>
      <td className="px-4 py-3 whitespace-nowrap">
        <Mono>{v.label}</Mono>{" "}
        {v.pass === null ? null : v.pass ? (
          <span className="text-safe" title={`AA needs ${threshold(role)}:1`}>
            ✓ AA
          </span>
        ) : (
          <span className="text-danger" title={`AA needs ${threshold(role)}:1`}>
            ✗ AA
          </span>
        )}
        {role !== "body" && (
          <span className="ml-1 text-xs text-text-tertiary">
            ({role === "nontext" ? "non-text" : "large"})
          </span>
        )}
      </td>
      <td className="hidden px-4 py-3 text-text-secondary sm:table-cell">
        {swatch.note}
      </td>
    </tr>
  );
}

function Verdicts() {
  return (
    <Section
      title="Verdict"
      blurb="Four values, and the one place where the palette carries meaning rather than style. Each is shown the way it must always ship: colour, plus an icon, plus the word."
    >
      <div className="grid gap-4 sm:grid-cols-2">
        {VERDICTS.map((v) => (
          <div
            key={v.key}
            className="rounded-lg border p-4"
            style={{
              background: `var(--${v.key}-surface)`,
              borderColor: `var(--${v.key}-border)`,
            }}
          >
            <p
              className="flex items-center gap-2 font-medium"
              style={{ color: `var(--${v.key})` }}
            >
              <Glyph kind={v.glyph} />
              {v.label}
            </p>
            <p className="mt-2 text-sm text-text-secondary">{v.meaning}</p>
            <p className="mt-3 font-mono text-xs text-text-tertiary">
              --{v.key} · --{v.key}-surface · --{v.key}-border
            </p>
          </div>
        ))}
      </div>

      <p className="mt-4 text-sm text-text-secondary">
        Try this page in greyscale. All four remain distinguishable, because the
        icon and the word carry the meaning and the colour only reinforces it.
        A verdict rendered as a bare coloured dot is a bug.
      </p>
    </Section>
  );
}

function Glyph({ kind }: { kind: string }) {
  const paths: Record<string, string> = {
    check: "M4 10.5l4 4 8-9",
    alert: "M10 4v8m0 3.5v.5",
    cross: "M5 5l10 10M15 5L5 15",
    dash: "M4 10h12",
  };
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
      <path d={paths[kind] ?? paths.dash} />
    </svg>
  );
}

function Typography() {
  return (
    <Section title="Typography" blurb="Two families, no more.">
      <div className="space-y-4">
        {FONTS.map((f) => (
          <div
            key={f.token}
            className="rounded-lg border border-hairline bg-surface p-5"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="text-lg font-medium">{f.name}</p>
              <Mono>--{f.token}</Mono>
            </div>
            <p
              className="mt-3 text-2xl"
              style={{ fontFamily: `var(--${f.token})` }}
            >
              {f.sample}
            </p>
            <p className="mt-3 text-sm text-text-secondary">{f.note}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}

function Radii() {
  return (
    <Section
      title="Radius"
      blurb="One base value, --radius at 0.625rem, with every step derived from it by a multiplier."
    >
      <div className="flex flex-wrap gap-4">
        {RADII.map((r) => (
          <div key={r} className="text-center">
            <div
              className="h-20 w-20 border border-hairline-strong bg-elevated"
              style={{ borderRadius: `var(--radius-${r})` }}
            />
            <p className="mt-2 font-mono text-xs text-text-secondary">{r}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}

function Footer() {
  return (
    <footer className="mt-14 border-t border-hairline pt-6 text-sm text-text-tertiary">
      <p>
        Source of truth: <Mono>frontend/app/globals.css</Mono>. Written rules:{" "}
        <Mono>docs/brand.md</Mono>. Contrast on this page is computed in your
        browser, not copied from those files.
      </p>
    </footer>
  );
}

function Section({
  title,
  blurb,
  children,
}: {
  title: string;
  blurb: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-12">
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="mt-2 mb-5 max-w-2xl text-sm text-text-secondary">{blurb}</p>
      {children}
    </section>
  );
}

function Frame({
  label,
  tone,
  children,
}: {
  label: string;
  tone: "bg" | "cream";
  children: React.ReactNode;
}) {
  return (
    <figure className="overflow-hidden rounded-lg border border-hairline">
      <div
        className="flex min-h-40 items-center justify-center p-6"
        style={{ background: tone === "cream" ? "var(--text)" : "var(--bg)" }}
      >
        {children}
      </div>
      <figcaption className="border-t border-hairline bg-surface px-4 py-2 text-xs text-text-secondary">
        {label}
      </figcaption>
    </figure>
  );
}

function Mono({ children }: { children: React.ReactNode }) {
  return <code className="font-mono text-xs text-tan">{children}</code>;
}

/** rgb(18, 44, 79) -> #122c4f, so the page shows what globals.css authored. */
function toHex(rgb: string): string {
  const m = rgb.match(/rgba?\(([^)]+)\)/);
  if (!m) return rgb;
  const [r, g, b] = m[1].split(/[,\s/]+/).filter(Boolean).map(Number);
  if ([r, g, b].some(Number.isNaN)) return rgb;
  return `#${[r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}
