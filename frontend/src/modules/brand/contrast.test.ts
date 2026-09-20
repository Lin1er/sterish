import { describe, expect, it } from "vitest";

import { contrastRatio, threshold, verdict } from "./contrast";

/**
 * /brand tells a reader whether a token clears WCAG AA. If this maths is wrong
 * the page does not merely look odd, it certifies an unreadable colour as
 * accessible -- which is worse than having no page at all, because someone
 * would act on it.
 *
 * The expected ratios below are the ones recorded in docs/brand.md and in the
 * comments in globals.css, so a drift in either direction shows up here.
 *
 * resolveToken is not covered: it needs a real DOM (this suite runs in node,
 * see vitest.config.mts) and is a thin wrapper over getComputedStyle. It is
 * exercised by loading /brand, which is how the ratios in brand.md were
 * checked in the first place.
 */

const NAVY = "rgb(18, 44, 79)"; // --bg, #122c4f
const CREAM = "rgb(251, 249, 228)"; // --text, #fbf9e4

/** Same shape the browser hands back from getComputedStyle().color. */
function rgb(hex: string): string {
  const n = parseInt(hex.replace("#", ""), 16);
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
}

describe("contrastRatio", () => {
  it("reproduces the ratios brand.md publishes", () => {
    // Each of these is a number a reader can check against the document.
    const cases: Array<[string, string, number]> = [
      ["#fbf9e4", NAVY, 13.19], // --text
      ["#bac0ba", NAVY, 7.56], // --text-secondary
      ["#8b979c", NAVY, 4.67], // --text-tertiary, the tightest pass
      ["#5c89b3", NAVY, 3.79], // --accent, fails body on purpose
      ["#3ddc84", NAVY, 7.85], // --safe
      ["#f5b301", NAVY, 7.56], // --warning
      ["#ff7a6b", NAVY, 5.5], // --danger
      ["#a3adb8", NAVY, 6.16], // --unaudited
    ];
    for (const [hex, bg, expected] of cases) {
      expect(contrastRatio(rgb(hex), bg), hex).toBeCloseTo(expected, 2);
    }
  });

  it("is symmetric: order of the pair cannot change the answer", () => {
    expect(contrastRatio(CREAM, NAVY)).toBeCloseTo(
      contrastRatio(NAVY, CREAM)!,
      10,
    );
  });

  it("anchors on the two extremes WCAG defines", () => {
    expect(contrastRatio("rgb(255,255,255)", "rgb(0,0,0)")).toBeCloseTo(21, 10);
    expect(contrastRatio("rgb(120,120,120)", "rgb(120,120,120)")).toBeCloseTo(
      1,
      10,
    );
  });

  it("catches the accent trap: the blue fails against navy AND against cream", () => {
    // The whole reason the primary button is cream with a navy label.
    expect(contrastRatio(rgb("#5c89b3"), NAVY)).toBeLessThan(4.5);
    expect(contrastRatio(rgb("#5c89b3"), CREAM)).toBeLessThan(4.5);
  });

  it("reads the spellings a browser can return", () => {
    const expected = contrastRatio("rgb(18, 44, 79)", CREAM);
    for (const spelling of [
      "rgb(18 44 79)", // space-separated, CSS Color 4
      "rgba(18, 44, 79, 1)", // alpha form
      "rgb(18 44 79 / 1)", // slash alpha
    ]) {
      expect(contrastRatio(spelling, CREAM), spelling).toBeCloseTo(
        expected!,
        10,
      );
    }
  });

  it("returns null rather than a number when a value did not resolve", () => {
    // An unresolved var() leaves the property empty or literal. Returning null
    // makes /brand show a dash; returning 0 or NaN would render as a ratio and
    // be believed.
    for (const bad of ["", "var(--nope)", "transparent", "rebeccapurple"]) {
      expect(contrastRatio(bad, NAVY), bad).toBeNull();
      expect(contrastRatio(NAVY, bad), bad).toBeNull();
    }
  });
});

describe("threshold", () => {
  it("uses 4.5 for body and 3 for everything held to the looser bar", () => {
    expect(threshold("body")).toBe(4.5);
    expect(threshold("large")).toBe(3);
    expect(threshold("nontext")).toBe(3);
    expect(threshold()).toBe(4.5); // defaulting must be the strict one
  });
});

describe("verdict", () => {
  it("passes and fails on the right side of the body bar", () => {
    expect(verdict(4.5, "body")).toEqual({ label: "4.50:1", pass: true });
    expect(verdict(4.49, "body").pass).toBe(false);
  });

  it("lets a non-text token through at a ratio that fails as body text", () => {
    // --accent at 3.79 is the live example: correct as a fill, wrong as a label.
    expect(verdict(3.79, "nontext").pass).toBe(true);
    expect(verdict(3.79, "body").pass).toBe(false);
  });

  it("shows a dash, not a verdict, when the ratio is unknown", () => {
    expect(verdict(null)).toEqual({ label: "—", pass: null });
  });

  it("formats to two decimals so the page matches the document", () => {
    expect(verdict(13.1857, "body").label).toBe("13.19:1");
    expect(verdict(7, "body").label).toBe("7.00:1");
  });
});
