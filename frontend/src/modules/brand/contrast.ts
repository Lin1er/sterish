/**
 * WCAG 2.1 contrast, computed in the browser from resolved token values.
 *
 * globals.css carries ratios in its comments. Those were correct when written,
 * but a comment cannot fail — if someone retunes --danger the comment keeps
 * claiming the old number. The /brand page recomputes instead, so a token that
 * drops below its threshold shows up as FAIL on the page rather than as a
 * stale comment nobody re-checked.
 */

/** Resolve a CSS custom property to a concrete rgb() the browser has computed. */
export function resolveToken(name: string, el: HTMLElement): string {
  // A bare getPropertyValue on the variable returns the *authored* text, which
  // may itself be `var(--bg)`. Painting it onto a probe forces resolution.
  const probe = document.createElement("span");
  probe.style.cssText = "position:absolute;opacity:0;pointer-events:none";
  probe.style.color = `var(--${name})`;
  el.appendChild(probe);
  const value = getComputedStyle(probe).color;
  probe.remove();
  return value;
}

function channels(color: string): [number, number, number] | null {
  const m = color.match(/rgba?\(([^)]+)\)/);
  if (!m) return null;
  const parts = m[1].split(/[,\s/]+/).filter(Boolean).map(Number);
  if (parts.length < 3 || parts.some(Number.isNaN)) return null;
  return [parts[0], parts[1], parts[2]];
}

function relativeLuminance(color: string): number | null {
  const rgb = channels(color);
  if (!rgb) return null;
  const [r, g, b] = rgb.map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(fg: string, bg: string): number | null {
  const a = relativeLuminance(fg);
  const b = relativeLuminance(bg);
  if (a === null || b === null) return null;
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

/** WCAG AA: 4.5 for body text, 3.0 for large text and non-text. */
export function threshold(role: "body" | "large" | "nontext" = "body"): number {
  return role === "body" ? 4.5 : 3;
}

export function verdict(ratio: number | null, role: "body" | "large" | "nontext" = "body") {
  if (ratio === null) return { label: "—", pass: null as boolean | null };
  const pass = ratio >= threshold(role);
  return { label: `${ratio.toFixed(2)}:1`, pass };
}
