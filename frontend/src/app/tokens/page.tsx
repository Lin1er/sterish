/**
 * Design token preview. PROPOSAL for STE-7 (owner: Nabil).
 *
 * Not part of the product. This is the page Nabil and Ancung look at to agree a
 * token set is right before any flow is built on top of it. Every value shown
 * here is a token in src/app/globals.css: nothing on this page uses a
 * hand-written hex.
 *
 * Delete it, or move it behind a flag, once the tokens are signed off.
 */

import { AlertTriangle, CircleHelp, ShieldCheck, ShieldX } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { VerdictBadge } from "@/components/verdict-badge";

type Swatch = {
  token: string;
  hex: string;
  /** Contrast against --bg (#0a0a0f), computed offline so nobody trusts the eye. */
  onBg?: string;
  note?: string;
  /** Set when the ratio is below the 4.5:1 body-text bar. */
  failsBodyText?: boolean;
};

const surfaces: Swatch[] = [
  { token: "--bg", hex: "#0a0a0f", note: "Page" },
  { token: "--surface", hex: "#12121a", note: "Card, table row" },
  { token: "--surface-2", hex: "#1a1a24", note: "Popover, hovered row" },
  { token: "--border", hex: "#1e1e2e", note: "Hairline" },
  { token: "--border-strong", hex: "#2c2c40", note: "Input, focused card" },
];

const text: Swatch[] = [
  { token: "--text", hex: "#e8e8ed", onBg: "16.17:1", note: "Primary" },
  { token: "--text-muted", hex: "#a1a1ab", onBg: "7.71:1", note: "Secondary" },
  {
    token: "--text-subtle",
    hex: "#71717a",
    onBg: "4.09:1",
    note: "Decorative and disabled only",
    failsBodyText: true,
  },
];

const brand: Swatch[] = [
  {
    token: "--accent",
    hex: "#c2320a",
    onBg: "3.53:1",
    note: "Fill only. White on it clears AA at 5.59:1",
    failsBodyText: true,
  },
  {
    token: "--accent-lift",
    hex: "#ff6a3d",
    onBg: "6.94:1",
    note: "Accent as text, links, focus ring",
  },
  { token: "--accent-surface", hex: "#2c1715", note: "Badge fill" },
  { token: "--accent-border", hex: "#5d2b1f", note: "Badge outline" },
];

/** One swatch inside a verdict triplet. The two ratio fields are mutually
 *  exclusive in practice, but typing them together keeps the render loop
 *  uniform instead of narrowing a three-way union at the call site. */
type VerdictSwatch = {
  token: string;
  hex: string;
  /** Contrast of this colour as text on --bg. */
  onBg?: string;
  /** Contrast of the verdict text placed on this fill. */
  onFill?: string;
};

const verdicts: {
  verdict: "SAFE" | "WARNING" | "DANGEROUS" | "UNAUDITED";
  icon: typeof ShieldCheck;
  meaning: string;
  fg: VerdictSwatch;
  surface: VerdictSwatch;
  border: VerdictSwatch;
}[] = [
  {
    verdict: "SAFE" as const,
    icon: ShieldCheck,
    meaning: "Passed every stage. The only verdict that mints a VERIFIED token.",
    fg: { token: "--safe", hex: "#3ddc84", onBg: "11.07:1" },
    surface: { token: "--safe-surface", hex: "#11271f", onFill: "8.82:1" },
    border: { token: "--safe-border", hex: "#1b5137" },
  },
  {
    verdict: "WARNING" as const,
    icon: AlertTriangle,
    meaning: "Findings worth reading before you install. Not blocked.",
    fg: { token: "--warning", hex: "#f5b301", onBg: "10.66:1" },
    surface: { token: "--warning-surface", hex: "#2b220d", onFill: "8.47:1" },
    border: { token: "--warning-border", hex: "#5a430a" },
  },
  {
    verdict: "DANGEROUS" as const,
    icon: ShieldX,
    meaning: "Blocked. A poisoned skill must always land here.",
    fg: { token: "--danger", hex: "#ff5c4d", onBg: "6.48:1" },
    surface: { token: "--danger-surface", hex: "#2c1518", onFill: "5.61:1" },
    border: { token: "--danger-border", hex: "#5d2624" },
  },
  {
    verdict: "UNAUDITED" as const,
    icon: CircleHelp,
    meaning: "Hash not in the registry. Absence of a verdict, not a pass.",
    fg: { token: "--unaudited", hex: "#8b8b96", onBg: "5.86:1" },
    surface: { token: "--unaudited-surface", hex: "#1c1c22", onFill: "5.03:1" },
    border: { token: "--unaudited-border", hex: "#36363d" },
  },
];

const typeScale: [string, string, string][] = [
  ["text-4xl", "36px", "Audited Skills for AI Agents"],
  ["text-3xl", "30px", "Registry Browser"],
  ["text-2xl", "24px", "agentic-payments.x402"],
  ["text-xl", "20px", "Trust score 87/100"],
  ["text-lg", "18px", "A poisoned skill is blocked before it is ever installed."],
  ["text-base", "16px", "Check the hash, read the verdict, then install."],
  ["text-sm", "14px", "Audited 2 hours ago on testnet"],
  ["text-xs", "12px", "content_hash 9f2a8c14"],
];

const radii: [string, string, string][] = [
  ["rounded-sm", "6px", "badge"],
  ["rounded-md", "8px", "input, button"],
  ["rounded-lg", "10px", "card"],
  ["rounded-xl", "14px", "panel"],
];

function Section({
  n,
  title,
  lede,
  children,
}: {
  n: string;
  title: string;
  lede?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-border pt-10">
      <div className="mb-6">
        <div className="numeric text-xs font-semibold tracking-widest text-accent-lift">
          {n}
        </div>
        <h2 className="text-2xl font-bold tracking-tight">{title}</h2>
        {lede ? (
          <p className="mt-2 max-w-2xl text-sm text-text-muted">{lede}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function Chip({ s }: { s: Swatch }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface">
      <div className="h-16 w-full" style={{ backgroundColor: s.hex }} />
      <div className="flex flex-col gap-1 p-3">
        <div className="numeric font-mono text-xs text-text">{s.token}</div>
        <div className="numeric font-mono text-xs uppercase text-text-subtle">
          {s.hex}
        </div>
        {s.note ? (
          <div className="text-xs text-text-muted">{s.note}</div>
        ) : null}
        {s.onBg ? (
          <Badge variant={s.failsBodyText ? "warning" : "outline"}>
            <span className="numeric">on bg {s.onBg}</span>
          </Badge>
        ) : null}
      </div>
    </div>
  );
}

function Chips({ items }: { items: Swatch[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {items.map((s) => (
        <Chip key={s.token} s={s} />
      ))}
    </div>
  );
}

export default function TokenPreview() {
  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-12">
      <header className="mb-12 flex flex-col gap-3">
        <Badge variant="warning">Proposal, not signed off</Badge>
        <h1 className="text-4xl font-extrabold tracking-tight">
          Sterish design tokens
        </h1>
        <p className="max-w-2xl text-text-muted">
          STE-7 owns the final brand. This page exists so STE-8 has something
          concrete to build on, and so there is one artefact to argue about
          instead of a hex scattered through twenty components. Every value below
          is a token in{" "}
          <span className="numeric font-mono text-sm text-accent-lift">
            src/app/globals.css
          </span>
          . Change the values, keep the shape.
        </p>
        <p className="max-w-2xl text-sm text-text-muted">
          Contrast ratios are computed against{" "}
          <span className="numeric font-mono">--bg</span>, not eyeballed. The bar
          is 4.5:1 for body text and 3:1 for large text and non-text UI.
        </p>
      </header>

      <div className="flex flex-col gap-14">
        <Section
          n="01"
          title="Surfaces"
          lede="Five steps, dark only. A light theme is a STE-7 decision, so v1 does not ship one and .dark inherits :root rather than redefining it."
        >
          <Chips items={surfaces} />
        </Section>

        <Section
          n="02"
          title="Text"
          lede="Three roles. The third one fails the body-text bar on purpose and is labelled as such, because a token that quietly fails is worse than no token."
        >
          <Chips items={text} />
        </Section>

        <Section
          n="03"
          title="Brand"
          lede="The scaffold's rust, split in two. This is the one finding on this page that changes how you write code: the brand colour cannot be used as text."
        >
          <Chips items={brand} />
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-danger">
                  Wrong: accent as text
                </CardTitle>
                <CardDescription>
                  3.53:1 against the page. Fails AA for body text.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p style={{ color: "#c2320a" }}>
                  Check the hash before you install this skill.
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-safe">
                  Right: accent-lift as text
                </CardTitle>
                <CardDescription>6.94:1 against the page. Passes.</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-accent-lift">
                  Check the hash before you install this skill.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          n="04"
          title="Verdict"
          lede="Four values, fixed by the Registry contract. Each is a triplet of text colour, badge fill and badge outline. Hues are kept far apart so safe and dangerous survive red-green colour blindness."
        >
          <div className="flex flex-col gap-3">
            {verdicts.map((v) => (
              <Card key={v.verdict}>
                <CardHeader>
                  <div className="flex flex-wrap items-center gap-3">
                    <VerdictBadge verdict={v.verdict} />
                    <CardTitle className="numeric font-mono text-sm">
                      {v.fg.token}
                    </CardTitle>
                  </div>
                  <CardDescription>{v.meaning}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-3 sm:grid-cols-3">
                    {[v.fg, v.surface, v.border].map((c) => (
                      <div
                        key={c.token}
                        className="flex items-center gap-3 rounded-md border border-border p-2"
                      >
                        <div
                          className="size-9 shrink-0 rounded-sm border border-border-strong"
                          style={{ backgroundColor: c.hex }}
                        />
                        <div className="flex min-w-0 flex-col">
                          <span className="numeric truncate font-mono text-xs">
                            {c.token}
                          </span>
                          <span className="numeric font-mono text-xs uppercase text-text-subtle">
                            {c.hex}
                          </span>
                          {c.onBg ? (
                            <span className="numeric text-xs text-text-muted">
                              on bg {c.onBg}
                            </span>
                          ) : null}
                          {c.onFill ? (
                            <span className="numeric text-xs text-text-muted">
                              text on fill {c.onFill}
                            </span>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <Card className="mt-6">
            <CardHeader>
              <CardTitle>Colour is never the only signal</CardTitle>
              <CardDescription>
                STE-20 requires a verdict to survive greyscale and colour
                blindness, so VerdictBadge always renders an icon and the word
                alongside the colour. Below is the same row set with colour
                removed: it still reads.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-3 grayscale">
                {verdicts.map((v) => (
                  <VerdictBadge key={v.verdict} verdict={v.verdict} />
                ))}
              </div>
            </CardContent>
          </Card>
        </Section>

        <Section
          n="05"
          title="Typography"
          lede="Geist for prose, Geist Mono for anything a user might copy, compare or read digit by digit."
        >
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>The .numeric class</CardTitle>
              <CardDescription>
                Tabular figures and a slashed zero. Trust scores, content hashes,
                contract addresses and USDC amounts all use it, so a value cannot
                jitter as it updates and a zero cannot be misread as an O.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-1 rounded-md border border-border p-4">
                  <span className="text-xs text-text-subtle">Without</span>
                  <span className="font-mono text-2xl tracking-widest">
                    0 O 1 l 8 B
                  </span>
                  <span className="font-mono text-2xl tracking-widest">
                    418209
                  </span>
                  <span className="font-mono text-2xl tracking-widest">
                    111000
                  </span>
                </div>
                <div className="flex flex-col gap-1 rounded-md border border-accent-border bg-accent-surface p-4">
                  <span className="text-xs text-accent-lift">With .numeric</span>
                  <span className="numeric font-mono text-2xl tracking-widest">
                    0 O 1 l 8 B
                  </span>
                  <span className="numeric font-mono text-2xl tracking-widest">
                    418209
                  </span>
                  <span className="numeric font-mono text-2xl tracking-widest">
                    111000
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              {typeScale.map(([cls, px, sample], i) => (
                <div key={cls}>
                  {i > 0 ? <Separator /> : null}
                  <div className="flex flex-col gap-1 py-4 sm:flex-row sm:items-baseline sm:gap-6">
                    <div className="numeric w-28 shrink-0 font-mono text-xs text-text-subtle">
                      {cls} {px}
                    </div>
                    <div className={cls}>{sample}</div>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </Section>

        <Section
          n="06"
          title="Radius"
          lede="Four steps, derived from a single --radius so shadcn components and hand-written surfaces round identically."
        >
          <Card>
            <CardContent>
              <div className="flex flex-wrap items-end gap-6">
                {radii.map(([cls, px, use]) => (
                  <div key={cls} className="text-center">
                    <div
                      className={`${cls} size-16 border border-border-strong bg-surface-2`}
                    />
                    <div className="numeric mt-2 font-mono text-xs text-text-subtle">
                      {px}
                    </div>
                    <div className="text-xs text-text-muted">{use}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </Section>

        <Section
          n="07"
          title="Components in context"
          lede="The same tokens, seen through shadcn components rather than as swatches. If a component looks wrong here, the token is wrong, not the component."
        >
          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Buttons</CardTitle>
                <CardDescription>
                  Variants come from shadcn. Only the token values are ours.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-3">
                  <Button>Use this skill</Button>
                  <Button variant="secondary">View versions</Button>
                  <Button variant="outline">Copy hash</Button>
                  <Button variant="ghost">Cancel</Button>
                  <Button variant="destructive">Report skill</Button>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Registry table</CardTitle>
                <CardDescription>
                  Sample rows, not live data. The trust score column is
                  right-aligned and numeric so values compare down the column.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Skill ID</TableHead>
                      <TableHead>Verdict</TableHead>
                      <TableHead className="text-right">Trust score</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell className="numeric font-mono text-xs">
                        agentic-payments.x402
                      </TableCell>
                      <TableCell>
                        <VerdictBadge verdict="SAFE" />
                      </TableCell>
                      <TableCell className="numeric text-right">
                        92/100
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell className="numeric font-mono text-xs">
                        dapp.smart-accounts
                      </TableCell>
                      <TableCell>
                        <VerdictBadge verdict="WARNING" />
                      </TableCell>
                      <TableCell className="numeric text-right">
                        68/100
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell className="numeric font-mono text-xs">
                        wallet-helper.poisoned
                      </TableCell>
                      <TableCell>
                        <VerdictBadge verdict="DANGEROUS" />
                      </TableCell>
                      <TableCell className="numeric text-right">
                        11/100
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell className="numeric font-mono text-xs">
                        9f2a8c14e7b03d55
                      </TableCell>
                      <TableCell>
                        <VerdictBadge verdict="UNAUDITED" />
                      </TableCell>
                      <TableCell className="numeric text-right text-text-subtle">
                        n/a
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          n="08"
          title="What the tokens forbid"
          lede="The rules that are easier to break than to notice."
        >
          <Card>
            <CardContent>
              <ul className="flex list-disc flex-col gap-3 pl-5 text-sm">
                <li>
                  No raw hex in a component. If the value you need is missing,
                  add a token to globals.css.
                </li>
                <li>
                  <span className="numeric font-mono">--accent</span> is a fill,
                  never text. Reach for{" "}
                  <span className="numeric font-mono">--accent-lift</span>.
                </li>
                <li>
                  <span className="numeric font-mono">--text-subtle</span> is
                  below 4.5:1. Decorative and disabled only, never a label a user
                  has to read.
                </li>
                <li>
                  Verdict is never colour alone. Always the icon and the word
                  too, which is why VerdictBadge exists and is the only way to
                  render one.
                </li>
                <li>
                  Any digit a user might compare or copy gets{" "}
                  <span className="numeric font-mono">.numeric</span>.
                </li>
              </ul>
            </CardContent>
          </Card>
        </Section>
      </div>
    </div>
  );
}
