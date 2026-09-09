import type { NextRequest } from "next/server";

import { handleMockRequest } from "@/lib/mockApi";

/**
 * Routing only. The mock's behaviour, including whether it is served at all,
 * lives in src/lib/mockApi.ts.
 */
export function GET(
  request: NextRequest,
  ctx: RouteContext<"/api/mock/[...path]">,
) {
  return ctx.params.then(({ path }) => handleMockRequest(request, path));
}
