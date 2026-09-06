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
  check "/use unpaid -> 402"       402 "$(code "$BASE/use/$SAFE_SKILL_ID/1.0.0")"
  hdr=$(curl -sS -D - -o /dev/null --max-time 30 "$BASE/use/$SAFE_SKILL_ID/1.0.0" \
        | grep -ci '^payment-required:' || true)
  check "  payment challenge sent"   1 "$hdr"
fi
if [ -n "${POISON_SKILL_ID:-}" ]; then
  # A DANGEROUS version must never be offered for sale, not even at a price.
  check "/use DANGEROUS -> 403"    403 "$(code "$BASE/use/$POISON_SKILL_ID/1.0.0")"
fi

echo
if [ "$fail" -eq 0 ]; then echo "All checks passed."; else echo "FAILED"; exit 1; fi
