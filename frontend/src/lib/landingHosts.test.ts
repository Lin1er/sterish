import { describe, expect, it } from "vitest";

import {
  DEFAULT_LANDING_HOSTS,
  LANDING_PATH,
  landingHostPattern,
  landingRewriteConfig,
  landingRewrites,
  parseLandingHosts,
} from "@/lib/landingHosts";

/**
 * Mirrors how Next evaluates a `has: [{ type: "host" }]` rule: it takes the
 * Host header, drops the port, lowercases it, and tests it against
 * `^<value>$`. Reproduced here (node_modules/next/dist/shared/lib/router/
 * utils/prepare-destination.js) because the rules are compiled into the routes
 * manifest at build time, so an anchoring mistake would only show up in
 * production.
 */
function matches(pattern: string, hostHeader: string): boolean {
  const hostname = hostHeader.split(":", 1)[0].toLowerCase();
  return new RegExp(`^${pattern}$`).test(hostname);
}

describe("parseLandingHosts", () => {
  it("falls back to the brand hosts when LANDING_HOSTS is unset", () => {
    expect(parseLandingHosts(undefined)).toEqual(DEFAULT_LANDING_HOSTS);
    expect(parseLandingHosts(null)).toEqual(DEFAULT_LANDING_HOSTS);
  });

  it("does not let a caller mutate the default list", () => {
    parseLandingHosts(undefined).push("evil.example");
    expect(parseLandingHosts(undefined)).toEqual(["sterish.xyz", "www.sterish.xyz"]);
  });

  it("normalises whitespace, case and ports", () => {
    expect(parseLandingHosts(" Localhost:3000 , STERISH.xyz ")).toEqual([
      "localhost",
      "sterish.xyz",
    ]);
  });

  it("treats an explicitly empty value as 'no landing host'", () => {
    expect(parseLandingHosts("")).toEqual([]);
    expect(parseLandingHosts(" , ")).toEqual([]);
  });
});

describe("landingHostPattern", () => {
  const pattern = landingHostPattern(DEFAULT_LANDING_HOSTS);

  it("matches the brand hosts", () => {
    expect(matches(pattern, "sterish.xyz")).toBe(true);
    expect(matches(pattern, "www.sterish.xyz")).toBe(true);
    expect(matches(pattern, "STERISH.XYZ")).toBe(true);
    expect(matches(pattern, "sterish.xyz:443")).toBe(true);
  });

  it("leaves the dashboard, previews and local development alone", () => {
    expect(matches(pattern, "app.sterish.xyz")).toBe(false);
    expect(matches(pattern, "sterish-frontend.vercel.app")).toBe(false);
    expect(matches(pattern, "localhost:3000")).toBe(false);
  });

  it("escapes the dot, so a lookalike host is not the brand host", () => {
    expect(matches(pattern, "sterishaxyz")).toBe(false);
    expect(matches(pattern, "not-sterish.xyz")).toBe(false);
    expect(matches(pattern, "sterish.xyz.attacker.example")).toBe(false);
  });
});

describe("landingRewrites", () => {
  it("rewrites only '/' and only for the landing hosts", () => {
    expect(landingRewrites(undefined)).toEqual([
      {
        source: "/",
        destination: LANDING_PATH,
        has: [{ type: "host", value: "(?:sterish\\.xyz|www\\.sterish\\.xyz)" }],
      },
    ]);
  });

  it("emits nothing when no host should serve the landing page", () => {
    expect(landingRewrites("")).toEqual([]);
  });

  it("can be pointed at a single host for local verification", () => {
    const [rewrite] = landingRewrites("localhost");
    expect(rewrite.has[0].value).toBe("(?:localhost)");
    expect(matches(rewrite.has[0].value, "localhost:3000")).toBe(true);
  });
});

describe("landingRewriteConfig", () => {
  it("puts the rule in beforeFiles, because '/' is a real route", () => {
    const config = landingRewriteConfig(undefined);
    expect(config.beforeFiles).toEqual(landingRewrites(undefined));
    expect(config.afterFiles).toEqual([]);
    expect(config.fallback).toEqual([]);
  });

  it("stays empty everywhere when no host serves the landing page", () => {
    expect(landingRewriteConfig("")).toEqual({
      beforeFiles: [],
      afterFiles: [],
      fallback: [],
    });
  });
});
