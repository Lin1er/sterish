/**
 * A mock of the verification API.
 *
 * Point NEXT_PUBLIC_API_URL at http://localhost:3000/api/mock and the whole UI
 * runs on fixtures; point it back at the real API and not one line of client
 * code changes. That swap-by-env is the STE-8 acceptance check, and routing it
 * through a real HTTP endpoint rather than an import means the data layer is
 * genuinely exercised, including its error handling.
 *
 * It answers the read endpoints of docs/api-spec.md sections 3.1 to 3.5 and
 * 3.9, the licence read (3.8) and the paid path (3.7), including the section 4
 * error bodies.
 *
 * The paid path is the one place the mock cannot be faithful. There is no
 * facilitator behind it, so a payment is checked for shape only, never
 * verified or settled, and the "mint" is an entry in this process's memory.
 * What it does exercise for real is everything on the client side: the 402,
 * the decoded terms, the wallet signature over a genuine simulation of the
 * USDC transfer, and the 200 that follows.
 *
 * The logic lives here rather than in the route file because app/ is routing
 * only: the handler resolves params and delegates. That also lets the tests
 * call it directly, with no Request context to fake beyond the URL.
 */

import {
  FIXTURE_ARTIFACTS,
  FIXTURE_BY_HASH,
  FIXTURE_FEED,
  FIXTURE_HEALTH,
  FIXTURE_PAYMENT_TERMS,
  FIXTURE_SKILL_LIST,
  FIXTURE_SKILLS,
  FIXTURE_TOKENS_CONTRACT_ID,
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

/** Spec section 3.8 accepts a classic `G...` account and nothing else. */
const ACCOUNT = /^G[A-Z2-7]{55}$/;

/**
 * Licences the mock has "minted", as `agent|skill@version`. Module state, so
 * it lasts as long as the dev server process, which is long enough to show
 * that a second request is served without paying.
 */
const mintedLicences = new Set<string>();

/** Tests start from no licences. Not reachable over HTTP. */
export function resetMockLicences(): void {
  mintedLicences.clear();
}

function licenceKey(agent: string, skillId: string, version: string): string {
  return `${agent}|${skillId}@${version}`;
}

function toBase64Json(value: unknown): string {
  return Buffer.from(JSON.stringify(value)).toString("base64");
}

function fromBase64Json(value: string): unknown {
  // Buffer's decoder skips characters that are not base64 instead of failing,
  // so the alphabet is checked first. The API decodes with validate=True, and a
  // mock that accepted garbage the API refuses would hide a client bug.
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(value)) {
    throw new Error("not base64");
  }
  return JSON.parse(Buffer.from(value, "base64").toString("utf8"));
}

/** A deterministic stand-in for a transaction hash, clearly not a real one. */
function fakeTxHash(seed: string): string {
  let hash = 0x811c9dc5;
  for (const char of seed) {
    hash = Math.imul(hash ^ char.charCodeAt(0), 0x01000193) >>> 0;
  }
  return `00000000mock${hash.toString(16).padStart(8, "0")}`.padEnd(64, "0");
}

function agentOf(request: Request, url: URL): string | null {
  return (
    (
      url.searchParams.get("agent") ?? request.headers.get("X-AGENT-ADDRESS")
    )?.trim() || null
  );
}

/** Resolve a version the way both 3.7 and 3.2 do, or say which part is unknown. */
function versionOr404(skillId: string, version: string) {
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
  return record;
}

function handleLicense(
  request: Request,
  url: URL,
  skillId: string,
  version: string,
): Response {
  const agent = agentOf(request, url);
  if (!agent) {
    return fail(400, "MISSING_AGENT", "send ?agent=G... or X-AGENT-ADDRESS");
  }
  if (!ACCOUNT.test(agent)) {
    return fail(400, "INVALID_AGENT", `'${agent}' is not a G... account`);
  }
  // Spec 3.8: an unregistered skill and a never-licensed one both answer
  // held: false, because that is the contract's own answer. And it does not
  // look at the verdict at all.
  return Response.json({
    skill_id: skillId,
    version,
    agent,
    held: mintedLicences.has(licenceKey(agent, skillId, version)),
    tokens_contract_id: FIXTURE_TOKENS_CONTRACT_ID,
    contract_url: `https://stellar.expert/explorer/testnet/contract/${FIXTURE_TOKENS_CONTRACT_ID}`,
  });
}

function handleUse(
  request: Request,
  url: URL,
  skillId: string,
  version: string,
): Response {
  const record = versionOr404(skillId, version);
  if (record instanceof Response) return record;

  if (!record.is_verified) {
    return fail(
      403,
      "NOT_VERIFIED",
      `${skillId}@${version} is ${record.verdict}; only SAFE versions are licensable`,
    );
  }

  const artifact = FIXTURE_ARTIFACTS[`${skillId}@${version}`];
  if (!artifact) {
    // STE-42's order: an artifact that cannot be delivered is refused before
    // any challenge, so nobody is invited to pay for nothing.
    return fail(
      404,
      "ARTIFACT_NOT_FOUND",
      `no artifact on disk for ${skillId}@${version}`,
    );
  }

  const agent = agentOf(request, url);
  const payment = request.headers.get("X-PAYMENT");

  if (agent && mintedLicences.has(licenceKey(agent, skillId, version))) {
    return Response.json(artifact, {
      headers: { "X-STERISH-LICENSE": "held" },
    });
  }

  if (!payment) {
    return new Response("{}", {
      status: 402,
      headers: {
        "content-type": "application/json",
        "Cache-Control": "no-store",
        "PAYMENT-REQUIRED": toBase64Json({
          x402Version: 2,
          error: "Payment required",
          resource: {
            url: request.url,
            description: `License for ${skillId}@${version}`,
            mimeType: "application/json",
          },
          accepts: [FIXTURE_PAYMENT_TERMS],
        }),
      },
    });
  }

  let decoded: unknown;
  try {
    decoded = fromBase64Json(payment);
  } catch (cause) {
    return fail(
      400,
      "INVALID_PAYMENT",
      `X-PAYMENT is not base64 JSON: ${cause instanceof Error ? cause.message : String(cause)}`,
    );
  }

  // The shape a real facilitator would go on to verify: a v2 payload with the
  // accepted terms and a signed transaction. The signature itself cannot be
  // checked here, and the mock says so rather than pretending.
  const body = decoded as {
    accepted?: { amount?: string; payTo?: string };
    payload?: { transaction?: unknown };
  };
  if (
    typeof body.payload?.transaction !== "string" ||
    body.accepted?.amount !== FIXTURE_PAYMENT_TERMS.amount ||
    body.accepted?.payTo !== FIXTURE_PAYMENT_TERMS.payTo
  ) {
    return fail(
      402,
      "PAYMENT_REJECTED",
      "payment does not carry a signed transaction for the advertised terms",
    );
  }

  if (!agent) {
    return fail(
      400,
      "UNKNOWN_PAYER",
      "cannot tell who paid; send X-AGENT-ADDRESS with the request",
    );
  }

  mintedLicences.add(licenceKey(agent, skillId, version));
  const seed = `${agent}|${skillId}@${version}`;
  return Response.json(artifact, {
    headers: {
      "X-STERISH-LICENSE": "minted",
      "X-STERISH-LICENSE-TX": fakeTxHash(`mint|${seed}`),
      "X-PAYMENT-RESPONSE": toBase64Json({
        success: true,
        transaction: fakeTxHash(`settle|${seed}`),
        network: FIXTURE_PAYMENT_TERMS.network,
        payer: agent,
      }),
    },
  });
}

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

  // GET /license/{skill_id}/{version}
  if (path.length === 3 && path[0] === "license") {
    return handleLicense(request, url, path[1], path[2]);
  }

  // GET /use/{skill_id}/{version}
  if (path.length === 3 && path[0] === "use") {
    return handleUse(request, url, path[1], path[2]);
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
    const record = versionOr404(path[1], path[2]);
    return record instanceof Response ? record : Response.json(record);
  }

  return fail(404, "NOT_FOUND", `the mock does not serve /${path.join("/")}`);
}
