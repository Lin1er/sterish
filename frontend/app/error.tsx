"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";

/**
 * The backstop.
 *
 * A failed registry read renders its own state inside the page, so anything
 * reaching here is an unexpected bug rather than an API that said no. The copy
 * says so instead of guessing at a cause.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-24 text-center sm:px-6">
      <h2 className="text-2xl font-bold">Something went wrong</h2>
      <p className="mx-auto mt-3 max-w-md text-sm text-text-secondary">
        This is a fault in the dashboard, not a verdict about any skill. Nothing
        shown before the error should be treated as a result.
      </p>
      {error.digest ? (
        <p className="numeric mt-4 font-mono text-xs text-text-tertiary">
          Digest {error.digest}
        </p>
      ) : null}
      <Button className="mt-6" onClick={reset}>
        Try again
      </Button>
    </div>
  );
}
