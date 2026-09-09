import { PlugZap, ServerCrash } from "lucide-react";

import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import type { ApiError } from "@/lib/api";

/**
 * A failed read, told apart from an empty result.
 *
 * Takes an `ApiError`, never a raw string, so the component can tell "the API
 * said no" from "the API was never reached" and word itself accordingly. Those
 * are two different facts and the old scaffold blurred them: "no skills are
 * registered" and "we could not ask" must never look alike, because only one of
 * them means the registry is trustworthy and quiet.
 *
 * It names the URL that failed, since the usual cause is NEXT_PUBLIC_API_URL
 * pointing somewhere that is not running.
 */
export function ErrorNotice({ error }: { error: ApiError }) {
  const transport = error.isTransport;
  return (
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          {transport ? <PlugZap /> : <ServerCrash />}
        </EmptyMedia>
        <EmptyTitle>
          {transport
            ? "Cannot reach the verification API"
            : "The verification API returned an error"}
        </EmptyTitle>
        <EmptyDescription>
          {error.message}
          {error.code ? ` (${error.code})` : null}
        </EmptyDescription>
      </EmptyHeader>
      <p className="numeric mt-2 font-mono text-xs text-text-tertiary">
        {error.url}
      </p>
      <p className="mt-4 max-w-md text-sm text-text-secondary">
        Nothing is shown above rather than a cached or default verdict. An
        unreachable registry is not evidence that a skill is safe.
      </p>
    </Empty>
  );
}
