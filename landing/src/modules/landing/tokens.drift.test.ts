import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * The landing and the dashboard are two deployments now, so they carry two
 * copies of the design tokens. A copy is the arrangement that goes wrong
 * quietly: somebody retunes --danger in one app, both keep building, and the
 * two faces of the product drift apart over a month with nothing to catch it.
 *
 * So the copy is not defended by anyone remembering. This reads both files and
 * fails the build the moment they disagree, which is the same trick /brand
 * plays with contrast: make the wrong state loud rather than trusting care.
 *
 * The landing drops two imports whose packages it does not install. Everything
 * else must match byte for byte.
 */

const DROPPED = ['@import "shadcn/tailwind.css";', '@import "tw-animate-css";'];

function read(rel: string): string {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

/** Everything after the landing copy's own explanatory header. */
function landingBody(text: string): string {
  const end = text.indexOf("========= */");
  return end === -1 ? text : text.slice(end + "========= */".length).trimStart();
}

function normalise(text: string): string {
  return text
    .split(/\r?\n/)
    .filter((line) => !DROPPED.includes(line.trim()))
    .join("\n")
    .trim();
}

describe("design tokens stay identical across the two apps", () => {
  const dashboard = read("../../../../frontend/app/globals.css");
  const landing = read("../../../app/globals.css");

  it("the landing copy is the dashboard file minus the two dropped imports", () => {
    expect(normalise(landingBody(landing))).toBe(normalise(dashboard));
  });

  it("still drops exactly the imports it claims to, and nothing else", () => {
    for (const line of DROPPED) {
      expect(dashboard).toContain(line);
      expect(landingBody(landing)).not.toContain(line);
    }
  });

  it("carries the five brand values, so a gutted file cannot pass", () => {
    // normalise() would happily compare two empty strings. These pin the
    // content itself, in case the files are ever both emptied or moved.
    for (const value of ["#122c4f", "#fbf9e4", "#5c89b3", "#bf8ce5", "#bda094"]) {
      expect(landing.toLowerCase()).toContain(value);
      expect(dashboard.toLowerCase()).toContain(value);
    }
  });

  it("carries all four verdict colours", () => {
    for (const token of ["--safe:", "--warning:", "--danger:", "--unaudited:"]) {
      expect(landing).toContain(token);
    }
  });
});
