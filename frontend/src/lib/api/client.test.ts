import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, checkByHash, getHealth, listSkills } from "./client";

/**
 * The data layer is the only thing between a wrong answer and a badge that
 * claims a skill is safe, so these tests care most about what happens when the
 * API does not cooperate. A read that fails must fail loudly and specifically;
 * it must never resolve to something a caller could render as a verdict.
 */

function respondWith(body: unknown, init?: ResponseInit) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(Response.json(body, init));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("a successful read", () => {
  it("returns the parsed body", async () => {
    respondWith({ skills: [], total: 0, start: 0, limit: 20 });
    await expect(listSkills()).resolves.toEqual({
      skills: [],
      total: 0,
      start: 0,
      limit: 20,
    });
  });

  it("sends the pagination the caller asked for", async () => {
    const fetchSpy = respondWith({ skills: [], total: 0, start: 5, limit: 10 });
    await listSkills({ start: 5, limit: 10 });
    const [url] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("start=5");
    expect(String(url)).toContain("limit=10");
  });

  it("never serves a cached verdict", async () => {
    const fetchSpy = respondWith({ status: "ok" });
    await getHealth();
    const [, init] = fetchSpy.mock.calls[0];
    expect(init?.cache).toBe("no-store");
  });
});

describe("an error the API reported", () => {
  it("keeps the status and the spec error code", async () => {
    respondWith(
      { error: "SKILL_NOT_FOUND", detail: "unknown skill 'com.nope'" },
      { status: 404 },
    );

    const error = await listSkills().catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 404,
      code: "SKILL_NOT_FOUND",
      detail: "unknown skill 'com.nope'",
    });
    expect((error as ApiError).isNotFound).toBe(true);
    // The API answered, so retrying changes nothing.
    expect((error as ApiError).isTransport).toBe(false);
  });

  it("survives an error body that is not the documented shape", async () => {
    // A crashed process or a proxy in front of the API can answer with HTML.
    // That must surface as a 502, not as a JSON parse exception that hides the
    // status code from the UI.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("<html>502 Bad Gateway</html>", {
        status: 502,
        headers: { "content-type": "text/html" },
      }),
    );

    const error = (await checkByHash("a".repeat(64)).catch(
      (cause: unknown) => cause,
    )) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(502);
    expect(error.code).toBeNull();
  });
});

describe("an error that never reached the API", () => {
  it("is marked as transport, so the UI can offer a retry", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new TypeError("fetch failed"),
    );

    const error = (await listSkills().catch(
      (cause: unknown) => cause,
    )) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(0);
    expect(error.isTransport).toBe(true);
    expect(error.message).toContain("unreachable");
  });

  it("says so when the API is merely too slow", async () => {
    const timeout = new Error("The operation was aborted due to timeout");
    timeout.name = "TimeoutError";
    vi.spyOn(globalThis, "fetch").mockRejectedValue(timeout);

    const error = (await listSkills().catch(
      (cause: unknown) => cause,
    )) as ApiError;
    // Distinguished from an unreachable host on purpose: a slow API is up, and
    // the fix is different.
    expect(error.message).toContain("did not answer");
    expect(error.isTransport).toBe(true);
  });
});

describe("path building", () => {
  it("escapes a skill id so a slash cannot forge a path", async () => {
    const fetchSpy = respondWith({});
    await checkByHash("../../health");
    expect(String(fetchSpy.mock.calls[0][0])).toContain(
      "/check/by-hash/..%2F..%2Fhealth",
    );
  });
});
