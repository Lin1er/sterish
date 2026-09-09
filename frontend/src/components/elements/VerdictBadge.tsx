import { AlertTriangle, CircleHelp, ShieldCheck, ShieldX } from "lucide-react";

import { Badge } from "@/components/ui/badge";

/**
 * The four verdicts the Registry contract can hold. Frozen in STE-10, so this
 * union is the client-side mirror of the on-chain enum, not a UI convenience.
 */
export type Verdict = "SAFE" | "WARNING" | "DANGEROUS" | "UNAUDITED";

/**
 * One place decides how a verdict looks. Colour is always joined by an icon and
 * the word itself: STE-20 requires that a verdict survives being printed in
 * greyscale or read by someone with red-green colour blindness.
 */
const VERDICT = {
  SAFE: { variant: "safe", icon: ShieldCheck, label: "Safe" },
  WARNING: { variant: "warning", icon: AlertTriangle, label: "Warning" },
  DANGEROUS: { variant: "danger", icon: ShieldX, label: "Dangerous" },
  UNAUDITED: { variant: "unaudited", icon: CircleHelp, label: "Unaudited" },
} as const;

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const { variant, icon: Icon, label } = VERDICT[verdict];
  return (
    <Badge variant={variant}>
      <Icon data-icon="inline-start" />
      {label}
    </Badge>
  );
}
