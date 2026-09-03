#!/usr/bin/env bash
#
# STE-11 — third-party proof that the Sterish tokens are SOULBOUND.
#
# The claim being verified is deliberately narrow and mechanical: the built
# `sterish_tokens.wasm` does not EXPORT any function that could move, delegate
# or destroy a token. Not "the transfer function reverts" — the function is not
# in the contract spec at all, so there is nothing to call and nothing to trust.
#
# How it is checked:
#   1. build  contracts/ for wasm32v1-none --release
#   2. read   the contract spec straight out of the wasm with
#             `stellar contract info interface` (the same command an auditor or
#             an exchange would run against the deployed contract id)
#   3. parse  the exported function names out of the `pub trait Contract { ... }`
#             block that command prints
#   4. fail   if any forbidden name is exported, or if the expected mint/view
#             surface is missing (an empty or unparsable spec must not pass)
#
# Exit codes: 0 = the contract is soulbound and complete.
#             1 = a forbidden entrypoint is exported, or the required surface is
#                 missing — this is the failure the ticket cares about.
#             2 = the harness itself could not run (missing tool, build failed).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

WASM="contracts/target/wasm32v1-none/release/sterish_tokens.wasm"

# Entrypoints that would make a token transferable, delegable or destructible.
FORBIDDEN=(
  transfer
  transfer_from
  approve
  allowance
  set_approval_for_all
  burn
  burn_from
)

# The surface that MUST be present. Guards against the trivially-passing failure
# mode where the spec is empty, truncated or read from the wrong artifact.
REQUIRED=(
  mint_verified
  mint_license
  has_license
  is_verified_token
  owner_of
  get_token
  total_supply
)

fail() { printf '\033[31mFAIL\033[0m  %s\n' "$1" >&2; }
ok()   { printf '\033[32mok\033[0m    %s\n' "$1"; }
info() { printf '      %s\n' "$1"; }
die()  { printf '\033[31mHARNESS\033[0m %s\n' "$1" >&2; exit 2; }

command -v cargo   >/dev/null || die "cargo not found"
command -v stellar >/dev/null || die "stellar CLI not found (needed for 'contract info interface')"

echo "STE-11 soulbound verification"
echo "============================="
echo

info "building $WASM"
if ! (cd contracts && cargo build -p sterish-tokens --target wasm32v1-none --release) >/dev/null 2>&1; then
  # Re-run noisily so the operator sees the compiler error.
  (cd contracts && cargo build -p sterish-tokens --target wasm32v1-none --release)
  die "wasm build failed"
fi
[ -f "$WASM" ] || die "expected artifact not produced: $WASM"
info "wasm size: $(wc -c < "$WASM" | tr -d ' ') bytes"
echo

INTERFACE="$(stellar contract info interface --wasm "$WASM" 2>/dev/null)" \
  || die "'stellar contract info interface' failed on $WASM"
[ -n "$INTERFACE" ] || die "empty contract spec read from $WASM"

# Exported functions live in the generated `pub trait Contract { ... }` block;
# everything after it is type/error definitions, which must not be scanned (a
# struct field called `transfer_count` is not an entrypoint).
EXPORTS="$(printf '%s\n' "$INTERFACE" \
  | awk '/pub trait Contract \{/{inside=1; next} inside && /^\}/{exit} inside' \
  | grep -oE '^[[:space:]]*fn [A-Za-z_][A-Za-z0-9_]*' \
  | awk '{print $2}' \
  | sort -u)"

if [ -z "$EXPORTS" ]; then
  die "could not parse any exported function from the contract spec"
fi

echo "Exported entrypoints ($(printf '%s\n' "$EXPORTS" | wc -l | tr -d ' ')):"
printf '%s\n' "$EXPORTS" | sed 's/^/        /'
echo

status=0

for name in "${FORBIDDEN[@]}"; do
  if printf '%s\n' "$EXPORTS" | grep -qx "$name"; then
    fail "forbidden entrypoint exported: $name — the token is NOT soulbound"
    status=1
  fi
done
if [ "$status" -eq 0 ]; then
  ok "none of the ${#FORBIDDEN[@]} forbidden entrypoints is exported"
  info "checked: ${FORBIDDEN[*]}"
fi

for name in "${REQUIRED[@]}"; do
  if ! printf '%s\n' "$EXPORTS" | grep -qx "$name"; then
    fail "required entrypoint missing: $name — spec read from the wrong artifact?"
    status=1
  fi
done
if [ "$status" -eq 0 ]; then
  ok "the expected mint/view surface is present (${#REQUIRED[@]} entrypoints)"
fi

echo
if [ "$status" -eq 0 ]; then
  ok "sterish_tokens.wasm is SOULBOUND: tokens can be minted and read, never moved."
else
  fail "soulbound verification FAILED"
fi
exit "$status"
