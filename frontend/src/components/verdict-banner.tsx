import { AlertTriangle, CircleHelp, ShieldCheck, ShieldX } from "lucide-react";

import type { Verdict } from "@/lib/api/types";

/**
 * What this verdict means for somebody about to install the skill.
 *
 * The badge says what the verdict is; this says what to do about it, which is
 * the part a non-technical reviewer actually needs. DANGEROUS is deliberately
 * the loudest thing on the page rather than a small red pill, because "poisoned
 * skill visibly blocked" is a claim this project makes and has to show.
 *
 * Every line here is a fact the API or the contract guarantees. There is no
 * findings summary because the API does not serve one: GET /reports is still
 * PLANNED and report_uri is null on every live version. Inventing a reason
 * would be exactly the unverifiable claim Sterish exists to remove.
 */
const BANNER = {
  DANGEROUS: {
    icon: ShieldX,
    title: "Do not install this version",
    body: "The audit found this version dangerous. It holds no VERIFIED badge, and the API refuses to sell or serve it: a version the registry did not call SAFE answers 403 NOT_VERIFIED. The tokens contract enforces the same rule, so the refusal does not depend on the API behaving.",
    className: "border-danger-border bg-danger-surface text-danger",
  },
  WARNING: {
    icon: AlertTriangle,
    title: "Read the evidence before installing",
    body: "The audit raised concerns short of dangerous. This version is not VERIFIED and cannot be licensed, because only SAFE mints a badge. Treat the trust score as a summary, not a permission.",
    className: "border-warning-border bg-warning-surface text-warning",
  },
  UNAUDITED: {
    icon: CircleHelp,
    title: "Never audited",
    body: "No auditor has ever given this exact version a verdict. That is not a mild SAFE and not a soft pass, it is the absence of any claim at all. Another version of the same skill being SAFE says nothing about these bytes.",
    className: "border-unaudited-border bg-unaudited-surface text-unaudited",
  },
  SAFE: {
    icon: ShieldCheck,
    title: "Audited safe, for exactly these bytes",
    body: "This version carries a VERIFIED badge on chain. The verdict is pinned to its content hash, so a single changed byte is a different version with no verdict of its own. Check the audit transaction below to confirm it yourself.",
    className: "border-safe-border bg-safe-surface text-safe",
  },
} as const satisfies Record<
  Verdict,
  { icon: typeof ShieldX; title: string; body: string; className: string }
>;

export function VerdictBanner({
  verdict,
  version,
  trustScore,
}: {
  verdict: Verdict;
  version: string;
  trustScore: number | null;
}) {
  const { icon: Icon, title, body, className } = BANNER[verdict];

  return (
    <div
      // Colour is never the only carrier: an icon, a heading and a full
      // sentence say the same thing, so the banner survives greyscale and
      // colour blindness.
      role={verdict === "DANGEROUS" ? "alert" : undefined}
      className={`rounded-lg border px-5 py-4 ${className}`}
    >
      <div className="flex items-start gap-3">
        <Icon className="mt-0.5 size-5 shrink-0" aria-hidden />
        <div>
          <p className="font-bold">
            {title}
            <span className="numeric ml-2 font-mono text-xs opacity-80">
              {version}
              {trustScore === null ? null : ` - trust ${trustScore}/100`}
            </span>
          </p>
          <p className="mt-1.5 max-w-2xl text-sm text-text-secondary">{body}</p>
        </div>
      </div>
    </div>
  );
}
