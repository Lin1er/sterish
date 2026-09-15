#!/usr/bin/env bash
#
# STE-13 — deploy + wire the three Sterish contracts on Stellar testnet.
#
# Deterministic and repeatable: it deploys the exact WASM recorded in
# contracts/wasm-hashes.txt (STE-12) and refuses to run if those hashes drift,
# so what lands on chain is always the artifact that passed CI.
#
# Identities come from .env (never printed). Contract addresses are appended
# back to .env. See CLAUDE.md "Secret & wallet key".
#
# Usage:
#   bash scripts/deploy-testnet.sh                 # deploy all three + wire
#   bash scripts/deploy-testnet.sh --keep-escrow   # registry + tokens only
#   bash scripts/deploy-testnet.sh --verify        # read wiring back on-chain
#
# STE-44 added --keep-escrow, and it is the path any redeploy should take. The
# escrow is the only contract holding real USDC and has no upgrade path by
# design; redeploying it would strand whatever is in it and invalidate every
# request id already issued. Registry and Tokens are upgradeable, so replacing
# them is the normal, recoverable operation. Escrow is not, so it stays put.
#
# Prereqs: stellar CLI >= 27, identities created with
#   stellar keys generate sterish-{deployer,auditor,developer,reporter} --network testnet --fund
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "missing .env — see CLAUDE.md 'Secret & wallet key'"; exit 1; }
set -a; . ./.env; set +a

NET="${STELLAR_NETWORK:-testnet}"
W=contracts/target/wasm32v1-none/release
ok(){ printf '\033[32mok\033[0m    %s\n' "$*"; }

read_back() {
  q(){ stellar contract invoke --id "$1" --source-account sterish-deployer \
       --network "$NET" --send=no -- "${@:2}" 2>/dev/null; }
  echo "registry.admin        = $(q "$REGISTRY_CA" get_admin)"
  echo "registry.auditor      = $(q "$REGISTRY_CA" get_auditor)"
  echo "registry.skill_count  = $(q "$REGISTRY_CA" get_skill_count)"
  echo "escrow.usdc_token     = $(q "$ESCROW_CA" get_usdc_token)"
  echo "escrow.admin          = $(q "$ESCROW_CA" get_admin)"
  echo "tokens.admin          = $(q "$TOKENS_CA" get_admin)"
  echo "tokens.registry       = $(q "$TOKENS_CA" get_registry)"
  echo "tokens.auditor_role   = $(q "$TOKENS_CA" get_auditor_role)"
  echo "tokens.minter_role    = $(q "$TOKENS_CA" get_minter_role)"
  echo "tokens.total_supply   = $(q "$TOKENS_CA" total_supply)"
  # STE-44: the upgrade surface is part of the wiring now. If a redeploy ever
  # lands a wasm without it, that is visible here rather than on the day
  # somebody needs it.
  echo "registry.upgradeable  = $(q "$REGISTRY_CA" is_upgradeable)"
  echo "registry.delay_secs   = $(q "$REGISTRY_CA" get_upgrade_delay)"
  echo "registry.pending      = $(q "$REGISTRY_CA" get_pending_upgrade)"
  echo "tokens.upgradeable    = $(q "$TOKENS_CA" is_upgradeable)"
  echo "tokens.delay_secs     = $(q "$TOKENS_CA" get_upgrade_delay)"
  echo "tokens.pending        = $(q "$TOKENS_CA" get_pending_upgrade)"
}

if [ "${1:-}" = "--verify" ]; then read_back; exit 0; fi

KEEP_ESCROW=0
[ "${1:-}" = "--keep-escrow" ] && KEEP_ESCROW=1

# STE-44 upgrade timelock, in seconds. Testnet: 300 — long enough that the
# timelock is real and demonstrable in a demo, short enough not to block the
# team. Mainnet would pass a larger number here; the contracts take it as a
# constructor parameter precisely so the two differ by config, not by code.
UPGRADE_DELAY_SECS="${UPGRADE_DELAY_SECS:-300}"

# The deployed bytes must be the ones CI signed off on.
bash scripts/build-wasm.sh --check >/dev/null
ok "wasm matches contracts/wasm-hashes.txt (STE-12)"

# Registry first: the tokens contract needs its address to gate minting on a
# live `is_verified` cross-call.
REG=$(stellar contract deploy --wasm "$W/sterish_registry.wasm" \
      --source-account sterish-deployer --network "$NET" -- \
      --admin "$DEPLOYER_ADDRESS" --auditor "$AUDITOR_ADDRESS" \
      --upgrade_delay_secs "$UPGRADE_DELAY_SECS" | tail -1)
ok "registry deployed: $REG"

# The escrow settles in the OFFICIAL testnet USDC SAC (C…), never the classic
# issuer (G…). The address is immutable after construction by design.
if [ "$KEEP_ESCROW" = "1" ]; then
  ESC="$ESCROW_CA"
  [ -n "$ESC" ] || { echo "--keep-escrow needs ESCROW_CA in .env"; exit 1; }
  ok "escrow kept:       $ESC (not redeployed — it holds USDC and is immutable)"
else
  ESC=$(stellar contract deploy --wasm "$W/sterish_escrow.wasm" \
        --source-account sterish-deployer --network "$NET" -- \
        --usdc_token "$USDC_SAC_ADDRESS" --admin "$DEPLOYER_ADDRESS" | tail -1)
  ok "escrow deployed:   $ESC"
fi

TOK=$(stellar contract deploy --wasm "$W/sterish_tokens.wasm" \
      --source-account sterish-deployer --network "$NET" -- \
      --admin "$DEPLOYER_ADDRESS" --registry "$REG" \
      --auditor "$AUDITOR_ADDRESS" --minter "$DEPLOYER_ADDRESS" \
      --upgrade_delay_secs "$UPGRADE_DELAY_SECS" | tail -1)
ok "tokens deployed:   $TOK"

printf '\n# --- Contract addresses (scripts/deploy-testnet.sh) ---\nREGISTRY_CA=%s\nESCROW_CA=%s\nTOKENS_CA=%s\n' \
  "$REG" "$ESC" "$TOK" >> .env
ok "addresses appended to .env"

REGISTRY_CA=$REG ESCROW_CA=$ESC TOKENS_CA=$TOK read_back
