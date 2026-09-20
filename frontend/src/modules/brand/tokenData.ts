/**
 * The token inventory shown on /brand.
 *
 * Only the *names* live here. Every swatch on the page paints itself with
 * `var(--name)` and reads the resolved value back out of the DOM at runtime, so
 * this file cannot drift out of sync with `app/globals.css` the way a second
 * list of hex codes would. If a token is renamed in globals.css it shows up on
 * the page as unresolved rather than as a stale-but-plausible colour.
 *
 * Contrast ratios are likewise computed in the browser (see contrast.ts), not
 * copied from the comments in globals.css.
 */

export type Swatch = {
  /** CSS custom property name, without the leading `--`. */
  name: string;
  /** What it is for. Kept short: the page is a reference, not an essay. */
  note: string;
  /** Token to measure this one against. Defaults to --bg. */
  against?: string;
  /** How the value is used, which decides which WCAG threshold applies. */
  role?: "body" | "large" | "nontext";
};

export type Group = {
  id: string;
  title: string;
  blurb: string;
  swatches: Swatch[];
};

export const COLOR_GROUPS: Group[] = [
  {
    id: "surfaces",
    title: "Surfaces",
    blurb:
      "The navy is a mid-dark canvas, not a near-black, so the layer a reader looks INTO (code, terminal, diff) sinks below it instead of rising above it. Cards and popovers lift by mixing cream into the navy.",
    swatches: [
      { name: "bg-deep", note: "Code block, terminal", role: "nontext" },
      { name: "bg", note: "Page canvas — Nabil primary", role: "nontext" },
      { name: "surface", note: "Card, table row", role: "nontext" },
      { name: "elevated", note: "Popover, nav on scroll", role: "nontext" },
      { name: "hairline", note: "Row and section borders", role: "nontext" },
      {
        name: "hairline-strong",
        note: "Focused input, active tab",
        role: "nontext",
      },
    ],
  },
  {
    id: "text",
    title: "Text",
    blurb:
      "Three levels, each measured against the page canvas. Cream, never #ffffff — pure white on this navy is harsh and reads as a different brand.",
    swatches: [
      { name: "text", note: "Headings and body — Nabil primary", role: "body" },
      { name: "text-secondary", note: "Body copy, descriptions", role: "body" },
      {
        name: "text-tertiary",
        note: "Captions and metadata — clears AA, but by the smallest margin in the set",
        role: "body",
      },
    ],
  },
  {
    id: "accents",
    title: "Brand accents",
    blurb:
      "The blue is a fill and a graphic colour, never text: it fails against the canvas, against cream, and against navy, so it is never a filled button. --accent-lift is the same hue raised until it passes.",
    swatches: [
      { name: "accent", note: "Fill, charts, graphics — never text", role: "nontext" },
      { name: "accent-lift", note: "The blue, as text", role: "body" },
      {
        name: "keyword",
        note: "The ONE leading accent: links, active tab, focus ring, syntax keywords",
        role: "body",
      },
      { name: "tan", note: "Metadata, code comments, quiet marks", role: "body" },
    ],
  },
];

export const VERDICTS = [
  {
    key: "safe",
    label: "Safe",
    glyph: "check",
    meaning: "Audited, no findings. The only verdict that mints VERIFIED.",
  },
  {
    key: "warning",
    label: "Warning",
    glyph: "alert",
    meaning: "Audited, findings that a reader should weigh before installing.",
  },
  {
    key: "danger",
    label: "Dangerous",
    glyph: "cross",
    meaning: "Audited, disqualifying findings. Poisoned skills MUST land here.",
  },
  {
    key: "unaudited",
    label: "Unaudited",
    glyph: "dash",
    meaning: "No audit on record. Absence of a finding, not a clean bill.",
  },
] as const;

export const RADII = ["sm", "md", "lg", "xl", "2xl", "3xl", "4xl"] as const;

export const FONTS = [
  {
    token: "font-sans",
    name: "Satoshi",
    note: "Every human sentence. Loaded from the Fontshare CDN rather than next/font: the ITF licence is free commercially but its terms on self-hosting a webfont are not clear, and the CDN is unambiguous.",
    sample: "Audited skills for AI agents on Stellar",
  },
  {
    token: "font-mono",
    name: "JetBrains Mono",
    note: "Anything the machine produced or the reader could type: hashes, addresses, skill ids, code.",
    sample: "CCZJN366SV57JEBZVXGYY3ZBLJNFV4IR5ILCAI3E",
  },
];
