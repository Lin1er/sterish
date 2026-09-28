/**
 * Which hostnames serve the landing page at "/".
 *
 * One Vercel project answers on every Sterish hostname, so the dashboard and
 * the landing page are the same deployment. What separates them is the host:
 *
 *   sterish.xyz, www.sterish.xyz -> the landing page (this module)
 *   app.sterish.xyz              -> the dashboard, the app's real "/"
 *   *.vercel.app, localhost      -> the dashboard, so previews and `next dev`
 *                                   keep showing the page being worked on
 *
 * `/landing` keeps answering on every host. The report, docs/deployments.md and
 * the links already shared point at it, and a rewrite adds a second entrance
 * rather than moving the first one.
 *
 * Kept out of next.config.ts so the host matching is testable: the rules are
 * baked into the routes manifest at build time, which makes a mistake here
 * invisible until it is deployed.
 */

/**
 * The brand hosts. Both are listed because the apex -> www redirect is a Vercel
 * domain setting, not something this repo controls: matching both means the
 * landing page stays at "/" whichever way that redirect points.
 */
export const DEFAULT_LANDING_HOSTS = ["sterish.xyz", "www.sterish.xyz"];

/** The route the landing page is authored at, and keeps answering on. */
export const LANDING_PATH = "/landing";

/** A Next.js rewrite, narrowed to the one shape this module emits. */
export type LandingRewrite = {
  source: string;
  destination: string;
  has: { type: "host"; value: string }[];
};

/**
 * Read the host list from `LANDING_HOSTS`.
 *
 * Unset falls back to the brand hosts. Set but empty disables the rewrite
 * entirely, which is how a deploy can serve the dashboard everywhere without a
 * code change.
 *
 * Ports are dropped because Next compares against the hostname only, so
 * `localhost:3000` would never match anything; `LANDING_HOSTS=localhost` is how
 * the rewrite is exercised against a local `next start`.
 */
export function parseLandingHosts(raw?: string | null): string[] {
  if (raw === undefined || raw === null) {
    return [...DEFAULT_LANDING_HOSTS];
  }
  return raw
    .split(",")
    .map((host) => host.trim().toLowerCase().split(":")[0])
    .filter((host) => host.length > 0);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * The `has` value for a host rule: an alternation of literal hostnames.
 *
 * Next wraps this in `^...$` and matches it against the lowercased hostname, so
 * every metacharacter is escaped. An unescaped dot would make `sterishaxyz` a
 * match for `sterish.xyz`.
 */
export function landingHostPattern(hosts: string[]): string {
  return `(?:${hosts.map(escapeRegExp).join("|")})`;
}

/**
 * The rewrite rules themselves.
 *
 * Only "/" is rewritten. Every other path resolves the same on every host, so
 * a link to /skills/{id} or /check keeps working whether it was copied from the
 * apex or from app.sterish.xyz.
 */
export function landingRewrites(raw?: string | null): LandingRewrite[] {
  const hosts = parseLandingHosts(raw);
  if (hosts.length === 0) {
    return [];
  }
  return [
    {
      source: "/",
      destination: LANDING_PATH,
      has: [{ type: "host", value: landingHostPattern(hosts) }],
    },
  ];
}

/**
 * What `next.config.ts` returns from `rewrites()`.
 *
 * `beforeFiles`, not the plain array: the array form becomes `afterFiles`,
 * which Next only consults once nothing else has matched the path. "/" is a
 * real route (app/page.tsx, the registry), so it always matches first and an
 * `afterFiles` rule never fires. Verified by serving a production build and
 * sending both Host headers.
 */
export function landingRewriteConfig(raw?: string | null): {
  beforeFiles: LandingRewrite[];
  afterFiles: LandingRewrite[];
  fallback: LandingRewrite[];
} {
  return { beforeFiles: landingRewrites(raw), afterFiles: [], fallback: [] };
}
