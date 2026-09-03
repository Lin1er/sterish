#!/usr/bin/env bash
#
# STE-13 — exercise BOTH escrow economic paths on Stellar testnet and print a
# tx-hash table ready to paste into docs/deployments.md.
#
#   Path 1 (settle): create_audit_request -> post_bond -> settle
#                    => auditor receives fee + bond back
#   Path 2 (slash):  create_audit_request -> post_bond -> slash(reporter)
#                    => reporter receives the bond, developer is refunded the fee
#
# The script is asset-agnostic on purpose: the same code proves the mechanics
# against the rehearsal asset AND against the canonical USDC escrow once the
# accounts hold real testnet USDC (Circle's faucet is web-only + Captcha, so
# that funding step cannot be scripted).
#
# Usage:
#   ESCROW=<escrow contract id> ASSET=<SAC contract id> bash scripts/testnet-economic-flows.sh
#
# Reads identities from .env (never prints secrets). Requires: stellar CLI, python3.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "missing .env — see CLAUDE.md 'Secret & wallet key'"; exit 1; }
set -a; . ./.env; set +a

ESCROW="${ESCROW:-${ESCROW_CA:-}}"
ASSET="${ASSET:-${USDC_SAC_ADDRESS:-}}"
NET="${STELLAR_NETWORK:-testnet}"
FEE="${FEE:-50000000}"    # 5.0000000 units (7 decimals)
BOND="${BOND:-100000000}" # 10.0000000 units

[ -n "$ESCROW" ] || { echo "set ESCROW=<contract id>"; exit 1; }
[ -n "$ASSET" ]  || { echo "set ASSET=<SAC contract id>"; exit 1; }

bold(){ printf '\033[1m%s\033[0m\n' "$*"; }
ok(){ printf '\033[32mok\033[0m    %s\n' "$*"; }
bad(){ printf '\033[31mFAIL\033[0m  %s\n' "$*"; }

bal(){ # bal <G-address> -> integer stroops
  stellar contract invoke --id "$ASSET" --source-account sterish-deployer \
    --network "$NET" --send=no -- balance --id "$1" 2>/dev/null | tr -d '"'
}

TXLOG=$(mktemp)
call(){ # call <label> <alias> <contract> <args...>  -> echoes result, logs tx hash
  local label=$1 alias=$2 id=$3; shift 3
  local errf out tx
  errf=$(mktemp)
  out=$(stellar contract invoke --id "$id" --source-account "$alias" \
        --network "$NET" -- "$@" 2>"$errf") || true
  tx=$(grep -oE '[0-9a-f]{64}' "$errf" | head -1 || true)
  printf '%s\t%s\n' "$label" "${tx:-<no-tx>}" >> "$TXLOG"
  printf '  %-32s tx=%s\n' "$label" "${tx:-<no-tx>}" >&2
  rm -f "$errf"
  printf '%s' "$out"
}

DEV=$DEVELOPER_ADDRESS; AUD=$AUDITOR_ADDRESS; REP=$REPORTER_ADDRESS

bold "escrow=$ESCROW"
bold "asset =$ASSET"
echo "fee=$FEE bond=$BOND (stroops, 7 decimals)"
echo

# ---------------------------------------------------------------- path 1: settle
bold "PATH 1 — SETTLE (honest auditor is paid)"
d0=$(bal "$DEV"); a0=$(bal "$AUD"); e0=$(bal "$ESCROW")
echo "  before: developer=$d0 auditor=$a0 escrow=$e0"

ID1=$(call "create_audit_request #1" sterish-developer "$ESCROW" create_audit_request \
      --requestor "$DEV" --skill_id "$SAFE_SKILL_ID" --version 1.0.0 \
      --fee_amount "$FEE" --bond_amount "$BOND")
ID1=$(printf '%s' "$ID1" | tr -d '"')
call "post_bond #$ID1" sterish-auditor "$ESCROW" post_bond --auditor "$AUD" --request_id "$ID1" >/dev/null
call "settle #$ID1" sterish-deployer "$ESCROW" settle --request_id "$ID1" >/dev/null

d1=$(bal "$DEV"); a1=$(bal "$AUD"); e1=$(bal "$ESCROW")
echo "  after : developer=$d1 auditor=$a1 escrow=$e1"
[ "$((d0 - d1))" -eq "$FEE" ] && ok "developer paid exactly the fee ($FEE)" || bad "developer delta $((d0-d1)) != $FEE"
[ "$((a1 - a0))" -eq "$FEE" ] && ok "auditor net +fee (bond returned, fee earned)" || bad "auditor delta $((a1-a0)) != $FEE"
[ "$e1" -eq "$e0" ] && ok "escrow holds nothing extra" || bad "escrow leaked: $e0 -> $e1"
echo

# ----------------------------------------------------------------- path 2: slash
bold "PATH 2 — SLASH (dishonest auditor forfeits the bond to the reporter)"
d2=$(bal "$DEV"); a2=$(bal "$AUD"); r2=$(bal "$REP"); e2=$(bal "$ESCROW")
echo "  before: developer=$d2 auditor=$a2 reporter=$r2 escrow=$e2"

ID2=$(call "create_audit_request #2" sterish-developer "$ESCROW" create_audit_request \
      --requestor "$DEV" --skill_id "$POISON_SKILL_ID" --version 1.0.0 \
      --fee_amount "$FEE" --bond_amount "$BOND")
ID2=$(printf '%s' "$ID2" | tr -d '"')
call "post_bond #$ID2" sterish-auditor "$ESCROW" post_bond --auditor "$AUD" --request_id "$ID2" >/dev/null
call "slash #$ID2 -> reporter" sterish-deployer "$ESCROW" slash --request_id "$ID2" --reporter "$REP" >/dev/null

d3=$(bal "$DEV"); a3=$(bal "$AUD"); r3=$(bal "$REP"); e3=$(bal "$ESCROW")
echo "  after : developer=$d3 auditor=$a3 reporter=$r3 escrow=$e3"
[ "$((r3 - r2))" -eq "$BOND" ] && ok "reporter received the bond ($BOND)" || bad "reporter delta $((r3-r2)) != $BOND"
[ "$d3" -eq "$d2" ]            && ok "developer fully refunded the fee"      || bad "developer delta $((d3-d2)) != 0"
[ "$((a2 - a3))" -eq "$BOND" ] && ok "auditor lost exactly the bond"         || bad "auditor delta $((a2-a3)) != $BOND"
[ "$e3" -eq "$e2" ]            && ok "escrow holds nothing extra"            || bad "escrow leaked: $e2 -> $e3"
echo

bold "tx hashes (paste into docs/deployments.md)"
while IFS=$'\t' read -r label tx; do
  printf '| `%s` | [`%s`](https://stellar.expert/explorer/testnet/tx/%s) |\n' "$label" "${tx:0:16}…" "$tx"
done < "$TXLOG"
rm -f "$TXLOG"
