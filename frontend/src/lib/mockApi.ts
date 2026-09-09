/**
 * A mock of the verification API.
 *
 * Point NEXT_PUBLIC_API_URL at http://localhost:3000/api/mock and the whole UI
 * runs on fixtures; point it back at the real API and not one line of client
 * code changes. That swap-by-env is the STE-8 acceptance check, and routing it
 * through a real HTTP endpoint rather than an import means the data layer is
 * genuinely exercised, including its error handling.
 *
 * It answers the read endpoints of docs/api-spec.md sections 3.1 to 3.5,
 * including the section 4 error bodies. The paid path (3.7) needs a
 * facilitator and belongs to STE-22.
 *
 * The logic lives here rather than in the route file because app/ is routing
 * only: the handler resolves params and delegates. That also lets the tests
 * call it directly, with no Request context to fake beyond the URL.
 */

import {
  FIXTURE_BY_HASH,
  FIXTURE_FEED,
  FIXTURE_HEALTH,
  FIXTURE_SKILL_LIST,
  FIXTURE_SKILLS,
  FIXTURE_VERSIONS,
} from "@/lib/fixtures";

/**
 * Off in production unless somebody switches it on deliberately.
 *
 * STE-20 asks for the mock path to be gone from the production build, and the
 * reason is not tidiness: a deployed dashboard that can serve fixtures is a
 * dashboard that can show an invented verdict to a real visitor. The opt-in
 * exists so a production build can still be exercised locally, which is how
 * the swap is verified before release. It is a server-side variable, not
 * NEXT_PUBLIC, so it can never be flipped from the browser.
 */
const MOCK_ENABLED =
  process.env.NODE_ENV !== "production" ||
  process.env.STERISH_ENABLE_MOCK === "1";

/** Spec section 4: every error response shares this shape. */
function fail(status: number, error: string, detail: string): Response {
  return Response.json({ error, detail }, { status });
}

/** Spec section 3.1: 64 lowercase hex, and uppercase is rejected, not fixed. */
const CONTENT_HASH = /^[0-9a-f]{64}$/;

export function handleMockRequest(request: Request, path: string[]): Response {
  if (!MOCK_ENABLED) {
    return fail(
      404,
      "NOT_FOUND",
      "the mock API is not served by production builds",
    );
  }

  const url = new URL(request.url);

  // GET /health
  if (path.length === 1 && path[0] === "health") {
    return Response.json(FIXTURE_HEALTH);
  }

  // GET /feed
  if (path.length === 1 && path[0] === "feed") {
    const rawLimit = url.searchParams.get("limit") ?? "50";
    const rawOffset = url.searchParams.get("offset") ?? "0";
    const limit = Number(rawLimit);
    const offset = Number(rawOffset);
    if (!Number.isInteger(limit) || limit < 1 || limit > 200) {
      return fail(
        400,
        "INVALID_PARAMETER",
        `limit must be an integer between 1 and 200, got '${rawLimit}'`,
      );
    }
    if (!Number.isInteger(offset) || offset < 0) {
      return fail(
        400,
        "INVALID_PARAMETER",
        `offset must be an integer >= 0, got '${rawOffset}'`,
      );
    }
    return Response.json({
      events: FIXTURE_FEED.slice(offset, offset + limit),
      total: FIXTURE_FEED.length,
      indexer_enabled: true,
      last_indexed_ledger: 4600100,
    });
  }

  // GET /skills
  if (path.length === 1 && path[0] === "skills") {
    const rawStart = url.searchParams.get("start") ?? "0";
    const rawLimit = url.searchParams.get("limit") ?? "20";
    const start = Number(rawStart);
    const limit = Number(rawLimit);

    if (!Number.isInteger(start) || start < 0) {
      return fail(
        400,
        "INVALID_PARAMETER",
        `start must be an integer >= 0, got '${rawStart}'`,
      );
    }
    if (!Number.isInteger(limit) || limit < 1) {
      return fail(
        400,
        "INVALID_PARAMETER",
        `limit must be an integer >= 1, got '${rawLimit}'`,
      );
    }

    // The real API clamps rather than rejects an oversized limit, so the mock
    // clamps identically. A mock that is stricter than production teaches the
    // client to defend against something that never happens.
    const clamped = Math.min(limit, 100);
    const page = FIXTURE_SKILL_LIST.skills.slice(start, start + clamped);
    return Response.json({
      skills: page,
      total: FIXTURE_SKILL_LIST.skills.length,
      start,
      limit: clamped,
    });
  }

  // GET /skills/{skill_id}
  if (path.length === 2 && path[0] === "skills") {
    const skill = FIXTURE_SKILLS[path[1]];
    if (!skill) {
      return fail(404, "SKILL_NOT_FOUND", `unknown skill '${path[1]}'`);
    }
    return Response.json(skill);
  }

  // GET /check/by-hash/{content_hash}
  if (path.length === 3 && path[0] === "check" && path[1] === "by-hash") {
    const hash = path[2];
    if (!CONTENT_HASH.test(hash)) {
      return fail(
        400,
        "INVALID_CONTENT_HASH",
        "content_hash must be exactly 64 lowercase hex characters",
      );
    }
    const version = FIXTURE_BY_HASH[hash];
    if (!version) {
      // Spec section 3.1 puts is_verified: false in the 404 body on purpose, so
      // a client reading only that field cannot read "unknown" as anything but
      // unverified.
      return Response.json(
        {
          error: "NOT_FOUND",
          detail: `content_hash ${hash} is not registered`,
          content_hash: hash,
          is_verified: false,
        },
        { status: 404 },
      );
    }
    return Response.json(version);
  }

  // GET /check/{skill_id}/{version}
  if (path.length === 3 && path[0] === "check") {
    const [, skillId, version] = path;
    if (!FIXTURE_SKILLS[skillId]) {
      return fail(404, "SKILL_NOT_FOUND", `unknown skill '${skillId}'`);
    }
    const record = FIXTURE_VERSIONS[`${skillId}@${version}`];
    if (!record) {
      return fail(
        404,
        "VERSION_NOT_FOUND",
        `skill '${skillId}' has no version '${version}'`,
      );
    }
    return Response.json(record);
  }

  return fail(404, "NOT_FOUND", `the mock does not serve /${path.join("/")}`);
}
