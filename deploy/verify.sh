#!/usr/bin/env bash
# Post-deploy verification (STE-25). Proves the deployment answers, not that a
# container is running: a process can be up while unable to read the chain.
#
#   bash deploy/verify.sh https://sterish.example.com
set -euo pipefail

BASE="${1:-http://127.0.0.1:8088}"
fail=0

say() { printf '%-46s %s\n' "$1" "$2"; }
check() { # name expected actual
  if [ "$2" = "$3" ]; then say "$1" "OK ($3)"; else say "$1" "FAIL (want $2, got $3)"; fail=1; fi
}

code() { curl -sS -o /dev/null -w '%{http_code}' --max-time 30 "$1"; }

echo "Verifying $BASE"
echo

# /health returns 503 when the chain cannot be read, so a 200 here means the
# service can actually answer, not merely that it booted.
check "/health"                    200 "$(code "$BASE/health")"
body=$(curl -sS --max-time 30 "$BASE/health")
for field in rpc_reachable network registry_contract_id; do
  value=$(printf '%s' "$body" | python3 -c "import json,sys;print(json.load(sys.stdin).get('$field'))")
  say "  $field" "$value"
done

check "/skills"                    200 "$(code "$BASE/skills?limit=1")"
check "/check unknown hash -> 404" 404 "$(code "$BASE/check/by-hash/$(printf '0%.0s' {1..64})")"
check "/check bad hash -> 400"     400 "$(code "$BASE/check/by-hash/nope")"

if [ -n "${SAFE_SKILL_ID:-}" ]; then
  SAFE_SKILL_VERSION="${SAFE_SKILL_VERSION:-1.0.0}"
  check "/use unpaid -> 402"       402 "$(code "$BASE/use/$SAFE_SKILL_ID/$SAFE_SKILL_VERSION")"
  hdr=$(curl -sS -D - -o /dev/null --max-time 30 "$BASE/use/$SAFE_SKILL_ID/$SAFE_SKILL_VERSION" \
        | grep -ci '^payment-required:' || true)
  check "  payment challenge sent"   1 "$hdr"
fi
if [ -n "${POISON_SKILL_ID:-}" ]; then
  # A DANGEROUS version must never be offered for sale, not even at a price.
  check "/use DANGEROUS -> 403"    403 "$(code "$BASE/use/$POISON_SKILL_ID/${POISON_SKILL_VERSION:-1.0.0}")"
fi

# STE-42: nothing is priced that cannot be handed over. Every SAFE row in the registry
# must answer /use with 402 + a challenge (for sale) or 404 ARTIFACT_NOT_FOUND with NO
# challenge (not offered). Anything else — a 500 hash mismatch above all — means a
# buyer could be charged for bytes the API cannot serve.
sale=$(BASE="$BASE" python3 - <<'PY'
import json, os, sys, urllib.error, urllib.request

base = os.environ["BASE"]
# An explicit User-Agent: Cloudflare in front of the public URL answers the default
# "Python-urllib/x" agent with an HTML block page, which is not an answer about /use.
UA = {"User-Agent": "sterish-verify/1.0"}

def get(url):
    request = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(request, timeout=60) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()

def as_json(raw, what):
    try:
        return json.loads(raw)
    except ValueError:
        print(f"{what} did not answer JSON: {raw[:120]!r}", file=sys.stderr)
        return None

status, _, body = get(f"{base}/skills?limit=100")
listing = as_json(body, f"/skills ({status})")
if status != 200 or not isinstance(listing, dict) or "skills" not in listing:
    # Could not enumerate: report it as a failure, never as "0 bad rows".
    print("0 0 1")
    sys.exit(0)

for_sale = not_offered = bad = 0
for row in listing["skills"]:
    if not row.get("latest_audited_is_verified"):
        continue
    target = f"{row['skill_id']}@{row['latest_audited_version']}"
    status, headers, raw = get(f"{base}/use/{row['skill_id']}/{row['latest_audited_version']}")
    challenged = any(k.lower() == "payment-required" for k in headers)
    error = (as_json(raw, f"/use {target}") or {}).get("error") if status == 404 else None
    if status == 402 and challenged:
        for_sale += 1
    elif status == 404 and not challenged and error == "ARTIFACT_NOT_FOUND":
        not_offered += 1
    else:
        print(f"  {target}: {status} challenged={challenged}", file=sys.stderr)
        bad += 1
print(f"{for_sale} {not_offered} {bad}")
PY
)
read -r for_sale not_offered bad <<<"${sale:-0 0 1}"
say "/use across every SAFE row" "$for_sale for sale, $not_offered not offered"
check "  undeliverable rows priced"   0 "$bad"
if [ -n "${MIN_FOR_SALE:-}" ]; then
  if [ "$for_sale" -ge "$MIN_FOR_SALE" ]; then say "  for sale >= $MIN_FOR_SALE" "OK ($for_sale)"
  else say "  for sale >= $MIN_FOR_SALE" "FAIL (got $for_sale)"; fail=1; fi
fi

# STE-32: the report endpoint is the last link of the verification chain, so the check
# that matters is not "does it 200" but "do the bytes still hash to the ledger".
check "/reports missing -> 404"    404 "$(code "$BASE/reports/com.does.not.exist/1.0.0")"

if [ -n "${EVIDENCE_SKILL_ID:-}" ] && [ -n "${EVIDENCE_VERSION:-}" ]; then
  report_url="$BASE/reports/$EVIDENCE_SKILL_ID/$EVIDENCE_VERSION"
  check "/reports served"          200 "$(code "$report_url")"
  served=$(curl -sS --max-time 30 "$report_url" | sha256sum | cut -d' ' -f1)
  onchain=$(curl -sS --max-time 30 "$BASE/check/$EVIDENCE_SKILL_ID/$EVIDENCE_VERSION" \
            | tr ',' '\n' | grep -o '"evidence_hash":"[0-9a-f]*"' | cut -d'"' -f4)
  check "  sha256(report) == evidence_hash" "$onchain" "$served"
fi

echo
if [ "$fail" -eq 0 ]; then echo "All checks passed."; else echo "FAILED"; exit 1; fi
