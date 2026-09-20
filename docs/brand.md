# Sterish brand

The written half of STE-7. The visual half is the `/brand` page in the dashboard,
which renders the real tokens and recomputes every contrast ratio in the browser.

**Source of truth for values is `frontend/app/globals.css`, not this file.** If a number
here and a number there disagree, globals.css wins and this file is out of date. Nothing
in the product reads this document; it exists so that a decision made once does not have
to be re-argued, and so a third party can check the work without asking Nabil.

Every ratio below was computed (`docs/brand.md` was written alongside a script that
measures them), not eyeballed. WCAG 2.1 AA is **4.5:1** for body text and **3:1** for
large text and non-text elements.

---

## 1. The five values

Everything else is derived from these. Change one and the app changes; change a
component and you have created a fork.

| Role | Hex | Token |
|---|---|---|
| Navy — the canvas | `#122C4F` | `--bg` |
| Cream — the ink | `#FBF9E4` | `--text` |
| Blue — graphics | `#5C89B3` | `--accent` |
| Violet — the one UI accent | `#BF8CE5` | `--keyword` |
| Tan — quiet marks | `#BDA094` | `--tan` |

The navy is a **mid-dark** canvas, not a near-black. That is deliberate: it lets the
surface a reader looks *into* — a code block, a terminal, a diff — sink **below** the page
with `--bg-deep`, while cards and popovers lift **above** it by mixing cream into the navy.
A near-black canvas can only ever lift.

The ink is cream, **never `#FFFFFF`**. Pure white on this navy is harsh, and at a glance it
reads as a different product.

---

## 2. Two rules that are not negotiable

**1. No raw values in components.** Never write a hex code, a font name, or a pixel radius
in a component. If the value you need does not exist, add a token to `globals.css` and use
it. This is what makes the five values above actually control the app.

**2. Verdict is never colour alone.** Every verdict surface pairs the colour with an icon
*and* the verdict word. A verdict rendered as a bare coloured dot is a bug, not a style
choice — it disappears for a colour-blind reader, in greyscale, and in a screenshot pasted
into a black-and-white doc. Sterish sells trust in an audit result; the audit result must
survive being looked at.

---

## 3. Colour, measured

Against `--bg` (`#122C4F`) unless stated.

### Text

| Token | Hex | Ratio | AA body |
|---|---|---|---|
| `--text` | `#FBF9E4` | 13.19:1 | pass |
| `--text-secondary` | `#BAC0BA` | 7.56:1 | pass |
| `--text-tertiary` | `#8B979C` | 4.67:1 | pass, by the thinnest margin in the set |

`--text-tertiary` clears AA, but only just. It is for captions and metadata. Anything a
reader has to *read* belongs in `--text-secondary` or above.

### Accents

| Token | Hex | vs navy | vs cream | Verdict |
|---|---|---|---|---|
| `--accent` | `#5C89B3` | 3.79:1 | 3.48:1 | **Never text. Never a filled button.** |
| `--accent-lift` | `#89A8C1` | 5.63:1 | — | the blue, as text |
| `--keyword` | `#BF8CE5` | 5.40:1 | — | links, active tab, focus ring, syntax keywords |
| `--tan` | `#BDA094` | 5.75:1 | — | metadata, code comments, quiet marks |

The blue is worth dwelling on, because it is the trap in this palette. It fails as body
text on the navy (3.79:1) **and** it fails with cream text on top of it (3.48:1) **and** with
navy text on top of it (3.79:1). There is no combination in which the blue carries a
readable label. So it is a fill and a graphic colour only — charts, icons, dividers.

That is also why **the primary button is cream with a navy label** (13.19:1), not a blue
button. If you find yourself reaching for a blue button, you are about to ship something
that fails AA.

`--keyword` is the single leading UI accent. One accent, used consistently, is what makes
an interface feel deliberate; three accents used interchangeably is what makes it feel
templated.

### Surfaces

Surfaces are non-text, so the 3:1 threshold applies to the borders, not the fills. What
matters is that cream stays readable on each one.

| Token | Hex | Cream on it |
|---|---|---|
| `--bg-deep` | `#0C1C32` | 16.10:1 |
| `--bg` | `#122C4F` | 13.19:1 |
| `--surface` | `#1F3757` | 11.35:1 |
| `--elevated` | `#29405E` | 9.94:1 |
| `--hairline` | `#374D67` | border only |
| `--hairline-strong` | `#536579` | focused input, active tab |

---

## 4. Verdict colours

Four values, and the only place in the palette where colour carries **meaning** rather
than style. Each ships as colour + icon + word.

| Verdict | Token | Hex | vs navy | On its own surface |
|---|---|---|---|---|
| Safe | `--safe` | `#3DDC84` | 7.85:1 | 7.45:1 |
| Warning | `--warning` | `#F5B301` | 7.56:1 | 7.11:1 |
| Dangerous | `--danger` | `#FF7A6B` | 5.50:1 | 5.65:1 |
| Unaudited | `--unaudited` | `#A3ADB8` | 6.16:1 | 5.90:1 |

Each has three tokens: `--<verdict>`, `--<verdict>-surface` (the tinted background) and
`--<verdict>-border`.

**Two of these were retuned and it matters why.** The verdict colours were first chosen
against a near-black canvas. The navy is roughly 7.5× lighter, which ate their margin:
`--unaudited` fell to 4.16:1 and failed outright, and `--danger` sat at 4.60:1 — nominally
passing, but with no room for a future adjustment. Both were lifted. The lesson to carry
forward: **a colour is only accessible against a specific background.** Moving the canvas
invalidates the whole set, so re-measure rather than assume.

On meaning, one point of care: **Unaudited is not a mild Warning.** It means no audit
exists on record — the absence of a finding, not a clean bill and not a soft negative. It
is deliberately the greyest, least alarming colour in the set, because implying a judgement
that was never made is the one failure mode this product cannot afford.

---

## 5. Typography

Two families, no more.

| Token | Family | Carries |
|---|---|---|
| `--font-sans` | Satoshi | every human sentence |
| `--font-heading` | → `--font-sans` | headings share the family, not a third font |
| `--font-mono` | JetBrains Mono | anything the machine produced or a reader could type |

The split is functional, not decorative: hashes, contract addresses, skill ids, CLI output
and code go in mono; prose goes in sans. A reader should be able to tell at a glance
whether a string is something they are meant to read or something they are meant to copy.

**Licence note.** Satoshi loads from the Fontshare CDN rather than `next/font`. The ITF
licence is free for commercial use, but its terms on self-hosting a webfont are not clear,
and the CDN is unambiguous. This is a deliberate trade of a network request for a licence
question nobody wants to answer later.

---

## 6. Radius

One base value, `--radius: 0.625rem`, with every step a multiplier of it:

| Token | Multiplier |
|---|---|
| `--radius-sm` | 0.6× |
| `--radius-md` | 0.8× |
| `--radius-lg` | 1× (the base) |
| `--radius-xl` | 1.4× |
| `--radius-2xl` | 1.8× |
| `--radius-3xl` | 2.2× |
| `--radius-4xl` | 2.6× |

Do not introduce a literal `border-radius`. Changing `--radius` should retune the whole
app's softness in one edit; a hardcoded value silently opts a component out of that.

---

## 7. Logo

### Files

All under `frontend/public/brand/logo/`.

| File | Use |
|---|---|
| `sterish-lockup-cream.svg` | **default**, on navy or any dark surface |
| `sterish-lockup-navy.svg` | on cream or any light surface |
| `sterish-mark-cream.svg` / `-navy.svg` | mark alone |
| `sterish-lockup-{cream,navy}-{1200,2400}.png` | raster, where SVG is not accepted |
| `sterish-mark-{cream,navy}-{512,1024}.png` | raster mark |
| `sterish-avatar-navy-tight-1024.png` | **profile pictures** (see below) |
| `sterish-header-navy-1500x500.png` | X header |
| `frontend/app/icon.svg` | browser tab — lens crop, vector |
| `frontend/app/apple-icon.png` | home-screen icon, 180px, generated from `icon.svg` |

SVG is the master in every case. The PNGs are generated from it, so regenerate rather
than edit them; a PNG edited by hand becomes a second source of truth that drifts.

### Geometry, measured

| Asset | Canvas | Actual ink |
|---|---|---|
| Lockup | viewBox `692×138` (5.01:1) | `2363×388` of a 2400px render |
| Mark | `400×400` square | **`1024×198` of a 1024px render** |

That second row is the thing to know about this logo. **The mark is not square artwork in
a square file — it is a 5.2:1 horizontal band with ~40% empty space above and below, and
it bleeds to both left and right edges with zero horizontal padding.**

Two consequences:

- **The mark has no built-in clear space horizontally.** Whatever margin it needs must be
  added by the layout.
- **Do not drop `sterish-mark-*.svg` into a square avatar slot.** Rendered at 48px — the
  size X actually shows in a timeline — it collapses into an illegible sliver. Use
  `sterish-avatar-navy-tight-1024.png`, which crops to the lens so the eye and starburst
  still read at 48px.

**Square placements crop to the lens. This is the agreed approach, not a stopgap.**
Nabil's decision, 20 Sep 2026: the asset set is complete as drawn, and square placements
should crop rather than wait for a separate square mark. So both the favicon
(`app/icon.svg`) and the avatar (`sterish-avatar-navy-tight-1024.png`) frame the lens and
starburst and let the swoosh run out of frame.

The two use different ratios on purpose. The avatar is cropped to a **circle**, which eats
the corners, so the lens is 55% of the frame. The favicon keeps its **rounded-square**
corners, and at 55% the lens ran off the right edge, so it is 40%. Candidates at 34, 40,
46 and 55 percent were rendered at 16, 32 and 48px before picking.

To be exact about what this permits: cropping the **mark**, in a square or circular
frame, using the measured window. Don't #7 below still stands for the lockup, which is
never cropped.

### Clear space

Let **x** = the height of the lockup's ink (`138` units in the lockup's own coordinate
system; the cap height of the *S* is a close enough proxy by eye).

- **Lockup:** keep at least **0.5x** clear on all four sides. Nothing — text, rule, image
  edge, button — enters that box.
- **Mark:** keep at least **0.5×** the mark's *ink height* on all sides, which must be
  added manually since the file provides none.

### Minimum size

- **Lockup:** 120px wide on screen, 25mm in print. Below that the wordmark's thin strokes
  break up and the starburst fills in.
- **Mark:** 24px. Below 24px use the avatar crop, not the mark.

### Don'ts

Each of these is a real failure mode, not a formality:

1. **Do not recolour.** Cream or navy only. The mark is not a `--keyword` violet mark.
2. **Do not put the cream lockup on a light background**, or the navy one on a dark
   background — both drop to roughly 1:1 and vanish.
3. **Do not place the lockup on the blue** (`--accent`). Cream on blue is 3.48:1 and navy
   on blue is 3.79:1; neither is readable.
4. **Do not stretch, skew, rotate or outline.** Scale proportionally.
5. **Do not add effects** — no shadow, glow, gradient or bevel.
6. **Do not rebuild the wordmark in Satoshi.** It is drawn artwork, not set type; typing
   "Sterish" in Satoshi gives a visibly different result. It is also not a separable
   element: the wordmark was drawn to sit beside the mark and merge with it, so there is
   no wordmark-only asset and pulling one out means redrawing (§10).
7. **Do not crop the lockup.** Use the mark when space is tight — that is what it is for.
   Cropping the *mark* for a square or circular frame is allowed and is how the favicon
   and avatar are built (§7, above); cropping the lockup is not.

---

## 8. The X account

Live at **[@sterishxyz](https://x.com/sterishxyz)**.

Bio follows the convention this team already uses on its other projects:
`Instawards by @StellarOrg.` plus one sentence of positioning.

Positioning language — audited skills, an audit registry for AI agents on Stellar.
**Avoid "official app store"** or any phrasing that implies Stellar endorsement or an
exclusive/official role. Sterish is a registry with an audit pipeline; claiming more is
both untrue and the kind of claim that is expensive to walk back.

Post drafts live in `docs/brand-posts.md`. Per Axel, the introduction post ships **after
deploy**, not before.

---

## 9. Changing a token

1. Edit `frontend/app/globals.css`. That is the only place a value changes.
2. Open `/brand` and check the recomputed ratio. The page marks AA pass/fail live — if
   your change fails, you will see it there rather than in review.
3. If the change moves a **surface**, re-check every colour measured against it. Section 4
   is a worked example of what happens when the canvas moves and the palette does not
   follow.
4. Update this file if a *rule* changed. If only a value changed, `/brand` already tells
   the truth and this file's tables are the thing to correct.

---

## 10. Asset decisions (20 Sep 2026)

Nabil reviewed the asset set and closed this out. Recorded here so it is not reopened by
someone reading §7 and assuming something is missing.

**The asset set is complete as drawn.** No compact square mark, no separate one-colour
mark, no editable source hand-off. Square placements crop to the lens instead (§7).

**There is no wordmark-only lockup, by design.** The wordmark was drawn to sit beside the
mark and merge with it — they are one composition, not two elements that happen to be
adjacent. Asking for the wordmark alone asks for a different piece of artwork, not an
export of this one. Where the lockup will not fit, use the mark.

**Consequences worth knowing, so nobody is surprised later:**

- **One-colour contexts are unsolved.** The mark is two-tone: a cream swoosh with a navy
  lens cut into it. A greyscale print, a stamp, an embroidered patch or a partner's
  monochrome logo strip has no correct asset today. If one of those comes up, it is a new
  request to Nabil, not something to improvise.
- **Edits mean a redraw.** The repo holds flattened SVG paths, not live shapes. A change
  to the artwork goes back to the designer.

Derivatives are still generated, never hand-made: PNG exports, favicons, app icons and
social crops all come from the SVG masters by script. If the mark artwork ever changes,
regenerate `icon.svg`'s crop and the tight avatar together, using the measurements in §7.
