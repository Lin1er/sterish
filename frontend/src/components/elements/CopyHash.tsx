"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";

/**
 * A content hash, short enough to read and complete enough to verify.
 *
 * The full 64 characters are always in the DOM (in the title and copied
 * value), never only the abbreviation. Somebody checking a hash against
 * stellar.expert needs all of it, and a UI that only ever shows the first
 * eight characters quietly makes the pinning claim unverifiable.
 */
export function CopyHash({
  value,
  chars = 10,
}: {
  value: string;
  chars?: number;
}) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(timer);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      // Clipboard access can be refused (insecure origin, denied permission).
      // The full value is in the title attribute either way, so selecting it
      // by hand still works and there is nothing useful to report here.
    }
  }

  return (
    <button
      type="button"
      onClick={() => void copy()}
      title={value}
      aria-label={copied ? "Hash copied" : `Copy the full hash ${value}`}
      className="numeric group inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 font-mono text-xs text-text transition-colors hover:border-hairline-strong"
    >
      <span>
        {value.slice(0, chars)}
        <span className="text-text-tertiary">...</span>
        {value.slice(-chars)}
      </span>
      {copied ? (
        <Check className="size-3 text-safe" aria-hidden />
      ) : (
        <Copy
          className="size-3 text-text-tertiary group-hover:text-text-secondary"
          aria-hidden
        />
      )}
    </button>
  );
}
