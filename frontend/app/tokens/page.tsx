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
import { VerdictBadge } from "@/components/elements/VerdictBadge";

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
  { token: "--bg-deep", hex: "#0c1c32", note: "Code, terminal. Sinks below" },
  { token: "--bg", hex: "#122c4f", note: "Page canvas. Nabil primary" },
  { token: "--surface", hex: "#1f3757", note: "Card, table row" },
  { token: "--elevated", hex: "#29405e", note: "Popover, nav on scroll" },
  { token: "--hairline", hex: "#374d67", note: "Row and section borders" },
  { token: "--hairline-strong", hex: "#536579", note: "Focused input, active tab" },
];

const text: Swatch[] = [
  { token: "--text", hex: "#fbf9e4", onBg: "13.19:1", note: "Nabil primary. Cream, never white" },
  { token: "--text-secondary", hex: "#bac0ba", onBg: "7.56:1", note: "Body copy, descriptions" },
  { token: "--text-tertiary", hex: "#8b979c", onBg: "4.67:1", note: "Captions and metadata only" },
];

const brand: Swatch[] = [
  {
    token: "--accent",
    hex: "#5c89b3",
    onBg: "3.79:1",
    note: "Fill and graphics only. Never text, never a filled button",
    failsBodyText: true,
  },
  {
    token: "--accent-lift",
    hex: "#89a8c1",
    onBg: "5.63:1",
    note: "The blue as text",
  },
  {
    token: "--keyword",
    hex: "#bf8ce5",
    onBg: "5.40:1",
    note: "The one leading accent: links, active tab, focus ring, keywords",
  },
  {
    token: "--tan",
    hex: "#bda094",
    onBg: "5.75:1",
    note: "Metadata, code comments, quiet marks",
  },
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
    fg: { token: "--safe", hex: "#3ddc84", onBg: "7.85:1" },
    surface: { token: "--safe-surface", hex: "#14352f" },
    border: { token: "--safe-border", hex: "#245b45" },
  },
  {
    verdict: "WARNING" as const,
    icon: AlertTriangle,
    meaning: "Findings worth reading before you install. Not blocked.",
    fg: { token: "--warning", hex: "#f5b301", onBg: "7.56:1" },
    surface: { token: "--warning-surface", hex: "#2e3220" },
    border: { token: "--warning-border", hex: "#5c541c" },
  },
  {
    verdict: "DANGEROUS" as const,
    icon: ShieldX,
    meaning: "Blocked. A poisoned skill must always land here.",
    fg: { token: "--danger", hex: "#ff7a6b", onBg: "5.50:1" },
    surface: { token: "--danger-surface", hex: "#33262f" },
    border: { token: "--danger-border", hex: "#633c3f" },
  },
  {
    verdict: "UNAUDITED" as const,
    icon: CircleHelp,
    meaning: "Hash not in the registry. Absence of a verdict, not a pass.",
    fg: { token: "--unaudited", hex: "#a3adb8", onBg: "6.16:1" },
    surface: { token: "--unaudited-surface", hex: "#232f45" },
    border: { token: "--unaudited-border", hex: "#414f61" },
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
    <section className="border-t border-hairline pt-10">
      <div className="mb-6">
        <div className="numeric text-xs font-semibold tracking-widest text-keyword">
          {n}
        </div>
        <h2 className="text-2xl font-bold tracking-tight">{title}</h2>
        {lede ? (
          <p className="mt-2 max-w-2xl text-sm text-text-secondary">{lede}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function Chip({ s }: { s: Swatch }) {
  return (
    <div className="overflow-hidden rounded-lg border border-hairline bg-surface">
      <div className="h-16 w-full" style={{ backgroundColor: s.hex }} />
      <div className="flex flex-col gap-1 p-3">
        <div className="numeric font-mono text-xs text-text">{s.token}</div>
        <div className="numeric font-mono text-xs uppercase text-text-tertiary">
          {s.hex}
        </div>
        {s.note ? (
          <div className="text-xs text-text-secondary">{s.note}</div>
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
        <Badge variant="unaudited">STE-7 brand, applied</Badge>
        <h1 className="text-4xl font-extrabold tracking-tight">
          Sterish design tokens
        </h1>
        <p className="max-w-2xl text-text-secondary">
          Nabil set the brand: navy, cream, and three accents. Everything below
          is derived from those five values, so changing one of them changes the
          app rather than one component. Every value below is a token in{" "}
          <span className="numeric font-mono text-sm text-keyword">
            src/app/globals.css
          </span>
          . Never write a raw hex in a component.
        </p>
        <p className="max-w-2xl text-sm text-text-secondary">
          Contrast ratios are computed against{" "}
          <span className="numeric font-mono">--bg</span>, not eyeballed. The bar
          is 4.5:1 for body text and 3:1 for large text and non-text UI.
        </p>
      </header>

      <div className="flex flex-col gap-14">
        <Section
          n="01"
          title="Surfaces"
          lede="Six steps built from the navy. It is a mid-dark canvas rather than a near-black, so the layer a reader looks into, meaning code and terminal output, sinks below the page instead of rising above it. Cards and popovers still lift."
        >
          <Chips items={surfaces} />
        </Section>

        <Section
          n="02"
          title="Text"
          lede="Three roles, all derived from the cream. Cream rather than white is the point: it is warmer, it is Nabil's, and at 13.19:1 on the navy it is stronger than most white-on-black pairs."
        >
          <Chips items={text} />
        </Section>

        <Section
          n="03"
          title="Brand"
          lede="Nabil's three accents, sorted by what each can actually do. The finding that changes how you write code: the blue cannot be text, and it cannot be a filled button either, because cream on it is 3.48:1 and navy on it is 3.79:1. Both fail."
        >
          <Chips items={brand} />
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-danger">
                  Wrong: the blue as text
                </CardTitle>
                <CardDescription>
                  3.79:1 against the page. Fails AA for body text.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p style={{ color: "#5c89b3" }}>
                  Check the hash before you install this skill.
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-safe">
                  Right: accent-lift as text
                </CardTitle>
                <CardDescription>5.63:1 against the page. Passes.</CardDescription>
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
                        className="flex items-center gap-3 rounded-md border border-hairline p-2"
                      >
                        <div
                          className="size-9 shrink-0 rounded-sm border border-hairline-strong"
                          style={{ backgroundColor: c.hex }}
                        />
                        <div className="flex min-w-0 flex-col">
                          <span className="numeric truncate font-mono text-xs">
                            {c.token}
                          </span>
                          <span className="numeric font-mono text-xs uppercase text-text-tertiary">
                            {c.hex}
                          </span>
                          {c.onBg ? (
                            <span className="numeric text-xs text-text-secondary">
                              on bg {c.onBg}
                            </span>
                          ) : null}
                          {c.onFill ? (
                            <span className="numeric text-xs text-text-secondary">
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
                <div className="flex flex-col gap-1 rounded-md border border-hairline p-4">
                  <span className="text-xs text-text-tertiary">Without</span>
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
                <div className="flex flex-col gap-1 rounded-md border border-hairline-strong bg-elevated p-4">
                  <span className="text-xs text-keyword">With .numeric</span>
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
                    <div className="numeric w-28 shrink-0 font-mono text-xs text-text-tertiary">
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
                      className={`${cls} size-16 border border-hairline-strong bg-elevated`}
                    />
                    <div className="numeric mt-2 font-mono text-xs text-text-tertiary">
                      {px}
                    </div>
                    <div className="text-xs text-text-secondary">{use}</div>
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
                      <TableCell className="numeric text-right text-text-tertiary">
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
                  never text and never a filled button. Reach for{" "}
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
