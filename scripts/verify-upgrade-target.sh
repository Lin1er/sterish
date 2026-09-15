#!/usr/bin/env bash
#
# STE-44 — the guard Soroban cannot give us.
#
# Two claims are checked against the BUILT wasm, with the same command an
# auditor would run against a deployed contract id:
#
#   1. sterish_registry.wasm and sterish_tokens.wasm still export the whole
#      upgrade surface.
#   2. sterish_escrow.wasm exports NONE of it.
#
# Why (1) has to be checked here and not in the contract
# -----------------------------------------------------------------------------
# `update_current_contract_wasm` takes a hash. There is no host function that
# can read a wasm's exports, so a contract CANNOT refuse to upgrade into a
# replacement that has no upgrade function — and the moment it does, that
# contract is frozen forever with no way back. `contracts/tests/tests/upgrade.rs`
# demonstrates exactly that, on real artifacts.
#
# The one place the check CAN live is before the bytes are ever published. So it
# lives here, and runs in CI on every change, which is why no Sterish wasm can
# reach `stellar contract upload` without having been looked at.
#
# This is a narrower promise than an on-chain guard and it is stated as such:
# it protects the artifacts this repository builds. It cannot stop an operator
# who uploads a wasm from somewhere else. What protects against that is the
# timelock — the proposed hash is public for the whole delay — and, permanently,
# `renounce_upgradeability`.
#
# Why (2) is checked at all
# -----------------------------------------------------------------------------
# The escrow is the only contract holding real USDC, and an admin who can swap
# the logic of a fund-holding contract can drain it. "Escrow is not upgradeable"
# is load-bearing for the whole design, so it is verified rather than trusted:
# if somebody ever adds an upgrade path to it, this job goes red.
#
# Exit codes: 0 = both claims hold.
#             1 = a claim failed — the failure this script exists for.
#             2 = the harness itself could not run (missing tool, build failed).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

W="contracts/target/wasm32v1-none/release"

# The whole surface, not just `execute_upgrade`. A wasm that could execute a
# proposal but never accept one, or that dropped `renounce_upgradeability`, is
# just as stuck — and the read-backs are what make the timelock observable from
# outside, which is the only reason it is worth anything.
UPGRADEABLE=(
  propose_upgrade
  execute_upgrade
  cancel_upgrade
  renounce_upgradeability
  get_pending_upgrade
  get_upgrade_delay
  is_upgradeable
)

fail() { printf '\033[31mFAIL\033[0m  %s\n' "$1" >&2; }
ok()   { printf '\033[32mok\033[0m    %s\n' "$1"; }
info() { printf '      %s\n' "$1"; }
die()  { printf '\033[31mHARNESS\033[0m %s\n' "$1" >&2; exit 2; }

command -v cargo   >/dev/null || die "cargo not found"
command -v stellar >/dev/null || die "stellar CLI not found (needed for 'contract info interface')"

# Exported functions live in the generated `pub trait Contract { ... }` block;
# everything after it is type and error definitions, which must not be scanned.
exports_of() {
  local wasm="$1" spec
  spec="$(stellar contract info interface --wasm "$wasm" 2>/dev/null)" || return 1
  [ -n "$spec" ] || return 1
  printf '%s\n' "$spec" \
    | awk '/pub trait Contract \{/{inside=1; next} inside && /^\}/{exit} inside' \
    | grep -oE '^[[:space:]]*fn [A-Za-z_][A-Za-z0-9_]*' \
    | awk '{print $2}' \
    | sort -u
}

echo "STE-44 upgrade-surface verification"
echo "==================================="
echo

info "building the three contracts for wasm32v1-none"
if ! (cd contracts && cargo build -p sterish-registry -p sterish-escrow -p sterish-tokens \
        --target wasm32v1-none --release) >/dev/null 2>&1; then
  (cd contracts && cargo build -p sterish-registry -p sterish-escrow -p sterish-tokens \
     --target wasm32v1-none --release)
  die "wasm build failed"
fi
echo

status=0

for wasm in sterish_registry.wasm sterish_tokens.wasm; do
  path="$W/$wasm"
  [ -f "$path" ] || die "expected artifact not produced: $path"
  exports="$(exports_of "$path")" \
    || die "could not read a contract spec out of $path"

  missing=()
  for name in "${UPGRADEABLE[@]}"; do
    printf '%s\n' "$exports" | grep -qx "$name" || missing+=("$name")
  done

  if [ ${#missing[@]} -eq 0 ]; then
    ok "$wasm exports the full upgrade surface (${#UPGRADEABLE[@]} entrypoints)"
  else
    fail "$wasm is MISSING: ${missing[*]}"
    info "Upgrading a live contract into this artifact would freeze it forever:"
    info "there is no host function that can read a wasm's exports, so the"
    info "contract cannot refuse, and after the swap there is no way back."
    status=1
  fi
done

path="$W/sterish_escrow.wasm"
[ -f "$path" ] || die "expected artifact not produced: $path"
exports="$(exports_of "$path")" || die "could not read a contract spec out of $path"

found=()
for name in "${UPGRADEABLE[@]}"; do
  if printf '%s\n' "$exports" | grep -qx "$name"; then found+=("$name"); fi
done

if [ ${#found[@]} -eq 0 ]; then
  ok "sterish_escrow.wasm exports no upgrade entrypoint — it is immutable"
else
  fail "sterish_escrow.wasm exports: ${found[*]}"
  info "The escrow is the only contract holding real USDC. An admin who can"
  info "replace the logic of a fund-holding contract can drain it, so this"
  info "contract must have no upgrade path at all (STE-44, docs/SYSTEM_DESIGN.md)."
  status=1
fi

echo
if [ "$status" -eq 0 ]; then
  ok "upgrade surfaces are as designed: registry and tokens upgradeable, escrow not."
else
  fail "upgrade-surface verification FAILED"
fi
exit "$status"
