/**
 * The single door to the verification API.
 *
 * Every read in the dashboard goes through `apiFetch`, so swapping the mock
 * server for the live API is an env change and nothing else (STE-8). Nothing
 * outside this folder should call `fetch` against the API directly.
 */

import type {
  ApiErrorBody,
  ApiErrorCode,
  FeedResponse,
  Health,
  LicenseStatus,
  PaymentRequired,
  SettlementReceipt,
  SkillArtifact,
  SkillDetail,
  SkillList,
  VersionCheck,
} from "./types";
import { decodePaymentRequired, decodeSettlementReceipt } from "./x402";

/**
 * Where the API lives. Absolute on purpose: these calls run in server
 * components too, where a relative path has no origin to resolve against.
 */
export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

/**
 * A slow API should surface as an error state, not as a page that never paints.
 *
 * Thirty seconds looks absurd for a read, and it is: measured against the live
 * testnet API on 2026-09-09, GET /skills costs roughly 0.44s per skill because
 * it does one RPC read per row with no batching. Three skills answer in 2.5s,
 * twenty in 9.9s, fifty in 22s. Ten seconds here turned a working API into a
 * rendered error, which is a worse lie than a slow page, so the ceiling is set
 * above the real worst case until the fan-out is fixed. See the note in the
 * dashboard README.
 */
const TIMEOUT_MS = 30_000;

/**
 * A failed read, carrying enough to render a useful message.
 *
 * `code` is the spec §4 `error` string when the API produced one. A transport
 * failure (DNS, refused connection, timeout) never reaches the API at all, so
 * it gets `code: null` and `status: 0`: the UI has to tell "the registry says
 * no" apart from "we could not ask the registry", and only one of those is
 * worth a retry button.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode | string | null;
  readonly detail: string;
  readonly url: string;

  constructor(args: {
    message: string;
    status: number;
    code: ApiErrorCode | string | null;
    detail: string;
    url: string;
  }) {
    super(args.message);
    this.name = "ApiError";
    this.status = args.status;
    this.code = args.code;
    this.detail = args.detail;
    this.url = args.url;
  }

  /** True when the API was never reached, so retrying may genuinely help. */
  get isTransport(): boolean {
    return this.status === 0;
  }

  /** True when the API answered, but the thing asked about does not exist. */
  get isNotFound(): boolean {
    return this.status === 404;
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as ApiErrorBody).error === "string"
  );
}

/**
 * One fetch, one error shape.
 *
 * Not cached. Next 16 no longer caches `fetch` by default, and that default is
 * the one we want: api-spec §4 is explicit that a stale or invented verdict is
 * the worst thing this product could serve, so a verdict is re-read every time
 * rather than held for the 60 s the spec permits.
 */
async function send(
  path: string,
  init: RequestInit | undefined,
  timeoutMs: number,
): Promise<{ response: Response; url: string }> {
  const url = `${API_BASE_URL}${path}`;
  try {
    const response = await fetch(url, {
      ...init,
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
      headers: { accept: "application/json", ...init?.headers },
    });
    return { response, url };
  } catch (cause) {
    const timedOut = cause instanceof Error && cause.name === "TimeoutError";
    throw new ApiError({
      message: timedOut
        ? `The verification API did not answer within ${timeoutMs / 1000}s`
        : "The verification API is unreachable",
      status: 0,
      code: null,
      detail: cause instanceof Error ? cause.message : String(cause),
      url,
    });
  }
}

async function errorFrom(response: Response, url: string): Promise<ApiError> {
  // An error body is expected (spec §4) but never assumed: a proxy or a
  // crashed process can return HTML, and that must not turn into a parse
  // exception that hides the real status code.
  const body: unknown = await response.json().catch(() => null);
  const parsed = isErrorBody(body) ? body : null;
  return new ApiError({
    message: parsed?.detail ?? `The API answered ${response.status}`,
    status: response.status,
    code: parsed?.error ?? null,
    detail: parsed?.detail ?? response.statusText,
    url,
  });
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const { response, url } = await send(path, init, TIMEOUT_MS);
  if (!response.ok) throw await errorFrom(response, url);
  return (await response.json()) as T;
}

/** Spec §3.4. `limit` is clamped to 100 by the API. */
export function listSkills(
  params: { start?: number; limit?: number } = {},
): Promise<SkillList> {
  const query = new URLSearchParams({
    start: String(params.start ?? 0),
    limit: String(params.limit ?? 20),
  });
  return apiFetch<SkillList>(`/skills?${query}`);
}

/** Spec §3.3. Throws ApiError 404 SKILL_NOT_FOUND for an unknown id. */
export function getSkill(skillId: string): Promise<SkillDetail> {
  return apiFetch<SkillDetail>(`/skills/${encodeURIComponent(skillId)}`);
}

/**
 * Spec §3.1, the primary path. Prefer this for a security decision: asking by
 * name trusts the name, asking by hash trusts nothing.
 */
export function checkByHash(contentHash: string): Promise<VersionCheck> {
  return apiFetch<VersionCheck>(
    `/check/by-hash/${encodeURIComponent(contentHash)}`,
  );
}

/** Spec §3.2. Resolved by name. Use for display, not for a gate. */
export function checkVersion(
  skillId: string,
  version: string,
): Promise<VersionCheck> {
  return apiFetch<VersionCheck>(
    `/check/${encodeURIComponent(skillId)}/${encodeURIComponent(version)}`,
  );
}

/**
 * Indexed registry activity, newest first.
 *
 * Not in the frozen spec. The API's own docstring calls it "a convenience
 * feed, not a verdict source", and that is exactly how it is used: the feed
 * supplies the timeline and the transaction links, while any verdict rendered
 * as a claim is read from the chain through /check or /skills.
 */
export function getFeed(
  params: { limit?: number; offset?: number } = {},
): Promise<FeedResponse> {
  const query = new URLSearchParams({
    limit: String(params.limit ?? 50),
    offset: String(params.offset ?? 0),
  });
  return apiFetch<FeedResponse>(`/feed?${query}`);
}

/** Spec §3.5. Answers 503 when the API cannot reach the chain. */
export function getHealth(): Promise<Health> {
  return apiFetch<Health>("/health");
}

/**
 * Spec §3.8. Whether `agent` holds a licence for this exact version.
 *
 * A failed chain read is a 502, never `held: false`, so "no licence" and "could
 * not tell" arrive as different things and are rendered as different things.
 */
export function getLicense(
  skillId: string,
  version: string,
  agent: string,
): Promise<LicenseStatus> {
  const query = new URLSearchParams({ agent });
  return apiFetch<LicenseStatus>(
    `/license/${encodeURIComponent(skillId)}/${encodeURIComponent(version)}?${query}`,
  );
}

/**
 * A paid request can legitimately take a while: after the facilitator settles,
 * the API mints the licence and polls the ledger until the mint lands. Cutting
 * that off early would leave the buyer unsure whether they paid, which is the
 * one outcome this flow must avoid, so the ceiling is generous.
 */
const PAID_TIMEOUT_MS = 120_000;

/** What `GET /use` answered, when it answered with something other than an error. */
export type UseOutcome =
  | {
      kind: "granted";
      /** `held`: the licence already existed. `minted`: this request paid for it. */
      licence: "held" | "minted";
      /** The mint transaction, present only when `licence` is `minted`. */
      mintTx: string | null;
      settlement: SettlementReceipt | null;
      artifact: SkillArtifact;
    }
  | { kind: "payment_required"; paymentRequired: PaymentRequired };

/**
 * Spec §3.7, the paid path. Not named `useSkill`: it is not a React hook, and
 * the name would make the hooks linter treat every call site as one.
 *
 * Without `payment`, a 402 is not an error but the first half of the flow, and
 * comes back as `payment_required` with its challenge decoded. With `payment`,
 * a 402 means the facilitator refused it and is thrown like any other error.
 * The two are told apart by the `PAYMENT-REQUIRED` header, which only the
 * challenge carries.
 *
 * `agent` is sent on both legs. Before payment it is how the API recognises an
 * existing licence and serves it without charging; after payment it is a
 * fallback for identifying the payer.
 */
export async function requestSkill(
  skillId: string,
  version: string,
  opts: { agent: string; payment?: string },
): Promise<UseOutcome> {
  const path = `/use/${encodeURIComponent(skillId)}/${encodeURIComponent(version)}`;
  const headers: Record<string, string> = { "X-AGENT-ADDRESS": opts.agent };
  if (opts.payment) headers["X-PAYMENT"] = opts.payment;

  let sent: { response: Response; url: string };
  try {
    sent = await send(
      path,
      { headers },
      opts.payment ? PAID_TIMEOUT_MS : TIMEOUT_MS,
    );
  } catch (cause) {
    // A signed payment went out and no answer came back. It may have settled.
    // Saying "unreachable, try again" here is how somebody pays twice, so this
    // gets its own code and the UI tells them to check the licence first.
    if (opts.payment && cause instanceof ApiError) {
      throw new ApiError({
        message:
          "The payment was sent but no answer came back, so it may or may not have gone through",
        status: 0,
        code: "PAYMENT_OUTCOME_UNKNOWN",
        detail: cause.detail,
        url: cause.url,
      });
    }
    throw cause;
  }
  const { response, url } = sent;

  const challenge = response.headers.get("PAYMENT-REQUIRED");
  if (response.status === 402 && challenge && !opts.payment) {
    const paymentRequired = decodePaymentRequired(challenge);
    if (!paymentRequired) {
      throw new ApiError({
        message:
          "The API asked for payment in a form this dashboard cannot read",
        status: 402,
        code: "INVALID_CHALLENGE",
        detail: "PAYMENT-REQUIRED is not a usable x402 v2 challenge",
        url,
      });
    }
    return { kind: "payment_required", paymentRequired };
  }

  if (!response.ok) throw await errorFrom(response, url);

  const licence =
    response.headers.get("X-STERISH-LICENSE") === "minted" ? "minted" : "held";
  return {
    kind: "granted",
    licence,
    mintTx: response.headers.get("X-STERISH-LICENSE-TX"),
    settlement: decodeSettlementReceipt(
      response.headers.get("X-PAYMENT-RESPONSE"),
    ),
    artifact: (await response.json()) as SkillArtifact,
  };
}
