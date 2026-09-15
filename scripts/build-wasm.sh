#!/usr/bin/env bash
#
# STE-12 — build the three Sterish contracts for wasm32v1-none and record, for
# each artifact, the exact bytes that will be uploaded to the network.
#
# The sha256 printed here IS the Soroban wasm hash: `stellar contract upload`
# stores the wasm under sha256(file) and every `stellar contract deploy` refers
# to it by that hash. So this file is what lets a third party check that the
# contract deployed in docs/deployments.md (STE-13) was built from this commit.
#
# Usage:
#   bash scripts/build-wasm.sh            build + (re)write contracts/wasm-hashes.txt
#   bash scripts/build-wasm.sh --check    build + compare against the recorded file
#   bash scripts/build-wasm.sh --help
#
# Exit codes: 0 = success (or, with --check, hashes match)
#             1 = --check found a mismatch, or the manifest is missing
#             2 = the harness itself could not run (missing tool, build failed)
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TARGET_DIR="contracts/target/wasm32v1-none/release"
MANIFEST="contracts/wasm-hashes.txt"
CRATES=(sterish-registry sterish-escrow sterish-tokens)
WASMS=(sterish_registry.wasm sterish_escrow.wasm sterish_tokens.wasm)

fail() { printf '\033[31mFAIL\033[0m  %s\n' "$1" >&2; }
ok()   { printf '\033[32mok\033[0m    %s\n' "$1"; }
info() { printf '      %s\n' "$1"; }
die()  { printf '\033[31mHARNESS\033[0m %s\n' "$1" >&2; exit 2; }

MODE="write"
case "${1:-}" in
  --check) MODE="check" ;;
  --help|-h)
    sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  "") ;;
  *) die "unknown argument: $1 (try --help)" ;;
esac

command -v cargo   >/dev/null || die "cargo not found"
command -v rustc   >/dev/null || die "rustc not found"
command -v stellar >/dev/null || die "stellar CLI not found (needed for 'contract info interface')"

# macOS ships `shasum`, Linux ships `sha256sum`; both are fine.
if command -v sha256sum >/dev/null; then
  sha256_of() { sha256sum "$1" | awk '{print $1}'; }
elif command -v shasum >/dev/null; then
  sha256_of() { shasum -a 256 "$1" | awk '{print $1}'; }
else
  die "no sha256 tool found (need sha256sum or shasum)"
fi

# --- the build host is part of the artifact identity ------------------------
# Measured in STE-12, on four independent machines across three host triples:
# the same source, the same pinned rustc 1.93.0, the same soroban-sdk and the
# same flags produce wasm that is byte-identical within a host triple and
# DIFFERENT across host triples. Every section keeps its exact size; what moves
# is the order in which the linker lays out the read-only data symbols, which
# shifts every pointer constant in the code section. See the manifest header.
#
# So a row is only meaningful next to the host that produced it, and --check
# compares against the rows for the host it is running on.
HOST_TRIPLE="$(rustc -vV | awk '/^host: /{print $2}')"
[ -n "$HOST_TRIPLE" ] || die "could not read the host triple out of 'rustc -vV'"

# Number of entrypoints exported by the built contract, read out of the wasm
# itself with the same command an auditor would run against a deployed id.
entrypoints_of() {
  local wasm="$1" spec
  spec="$(stellar contract info interface --wasm "$wasm" 2>/dev/null)" || return 1
  printf '%s\n' "$spec" \
    | awk '/pub trait Contract \{/{inside=1; next} inside && /^\}/{exit} inside' \
    | grep -cE '^[[:space:]]*fn [A-Za-z_][A-Za-z0-9_]*'
}

# --- deterministic paths ---------------------------------------------------
# soroban-sdk embeds `core::panic::Location` strings, so without this the built
# wasm contains the ABSOLUTE path of the machine's cargo registry
# (/Users/<me>/.cargo/registry/... locally, /home/runner/.cargo/... in CI) and
# the sha256 would differ per machine for identical source.
#
# Cargo's own `profile.trim-paths` would be the clean fix, but it is still
# unstable in Cargo 1.93 ("feature `trim-paths` is required"), so the equivalent
# rustc flags are set here, with $CARGO_HOME resolved at run time — a literal
# path in .cargo/config.toml could not be portable by definition.
#
# This is why the recorded hashes must be produced by THIS script: a bare
# `cargo build --target wasm32v1-none --release` omits the remapping and yields
# a different (machine-specific) sha256.
CARGO_HOME_DIR="${CARGO_HOME:-$HOME/.cargo}"
export RUSTFLAGS="--remap-path-prefix=${CARGO_HOME_DIR}/registry/src=/cargo/registry/src --remap-path-prefix=${CARGO_HOME_DIR}/git/checkouts=/cargo/git/checkouts${RUSTFLAGS:+ $RUSTFLAGS}"

echo "STE-12 wasm build"
echo "================="
echo

info "cargo build --target wasm32v1-none --release"
info "host:     $HOST_TRIPLE"
info "RUSTFLAGS=$RUSTFLAGS"
for crate in "${CRATES[@]}"; do
  if ! (cd contracts && cargo build -p "$crate" --target wasm32v1-none --release) >/dev/null 2>&1; then
    (cd contracts && cargo build -p "$crate" --target wasm32v1-none --release)
    die "wasm build failed for $crate"
  fi
done

# --- collect the body (the part --check compares) --------------------------
BODY=""
for wasm in "${WASMS[@]}"; do
  path="$TARGET_DIR/$wasm"
  [ -f "$path" ] || die "expected artifact not produced: $path"
  size="$(wc -c < "$path" | tr -d ' ')"
  sum="$(sha256_of "$path")"
  eps="$(entrypoints_of "$path")" || die "'stellar contract info interface' failed on $path"
  [ "$eps" -gt 0 ] || die "read 0 entrypoints from $path — wrong or truncated artifact?"
  BODY+="$(printf '%-22s %8s  %s  %2s  %s' "$wasm" "$size" "$sum" "$eps" "$HOST_TRIPLE")"$'\n'
done

printf '%s' "$BODY" | sed 's/^/      /'
echo

# --- toolchain header ------------------------------------------------------
SDK_VERSION="$(awk '/^name = "soroban-sdk"$/{found=1; next} found && /^version = /{gsub(/[",]/,"",$3); print $3; exit}' contracts/Cargo.lock)"
HEADER="$(cat <<EOF
# Sterish contract wasm manifest — generated by scripts/build-wasm.sh (STE-12)
#
# The sha256 below IS the Soroban wasm hash: \`stellar contract upload\` stores a
# contract under sha256(file), so a row pins exactly the bytes that a deploy of
# that build would put on chain.
# Re-verify with:  bash scripts/build-wasm.sh --check
#
# WHAT IS REPRODUCIBLE, AND WHAT YOU MUST PIN TO REPRODUCE IT
# -----------------------------------------------------------------------------
# Pin all of: this commit, rustc 1.93.0 (rust-toolchain.toml), the Cargo.lock in
# contracts/, the release profile in contracts/Cargo.toml, the \$CARGO_HOME path
# remapping this script exports — AND THE HOST TRIPLE.
#
# The host triple is not a formality. Measured in STE-12 on four independent
# machines across three host triples, with every one of the above held equal:
# the wasm is byte-identical within a host triple and different across host
# triples. Every wasm section keeps its exact size; what changes is the order in
# which the linker lays out the read-only data symbols, which shifts the pointer
# constants in the code section. Rust does not promise byte-identical output
# across host platforms, only across builds on the same one.
#
# So every row below carries the host that produced it, and \`--check\` compares
# only against the rows for the host it runs on. A host with no row here cannot
# verify these artifacts — it can only produce its own, equally valid, build.
#
# generated:   $(date -u +%Y-%m-%dT%H:%M:%SZ)
# rustc:       $(rustc --version)
# cargo:       $(cargo --version)
# soroban-sdk: $SDK_VERSION (contracts/Cargo.lock)
# stellar-cli: $(stellar --version 2>/dev/null | head -1)
# target:      wasm32v1-none, profile release (opt-level=z, lto, strip=symbols,
#              codegen-units=1, panic=abort, overflow-checks=on)
# toolchain:   pinned by rust-toolchain.toml
# build:       bare \`cargo build --target wasm32v1-none --release\`, NOT
#              \`stellar contract build\` — the latter runs the wasm optimizer by
#              default and would produce different bytes.
# paths:       \$CARGO_HOME remapped to /cargo (see build-wasm.sh) so the hash does
#              not depend on where the cargo registry of the builder lives
#
# columns: <file> <size_bytes> <sha256> <exported_entrypoints> <host_triple>
EOF
)"

if [ "$MODE" = "check" ]; then
  [ -f "$MANIFEST" ] || { fail "$MANIFEST is missing — run 'bash scripts/build-wasm.sh' first"; exit 1; }

  RECORDED="$(grep -v '^#' "$MANIFEST" | grep -v '^[[:space:]]*$' | awk -v h="$HOST_TRIPLE" '$5 == h')"
  CURRENT="$(printf '%s' "$BODY" | grep -v '^[[:space:]]*$')"

  if [ -z "$RECORDED" ]; then
    KNOWN="$(grep -v '^#' "$MANIFEST" | awk 'NF {print $5}' | sort -u | paste -sd', ' -)"
    fail "no rows recorded for this host in $MANIFEST"
    info "this host: $HOST_TRIPLE"
    info "recorded hosts: ${KNOWN:-none}"
    info "A Soroban wasm build is byte-reproducible per host triple, not across"
    info "host triples (see the manifest header), so the rows above cannot verify"
    info "a build made here. Either verify on one of the recorded hosts, or run"
    info "'bash scripts/build-wasm.sh' here to add a row for $HOST_TRIPLE."
    exit 1
  fi

  if [ "$RECORDED" = "$CURRENT" ]; then
    ok "rebuilt wasm matches $MANIFEST byte for byte (same size, same sha256)"
    info "host: $HOST_TRIPLE"
    exit 0
  fi

  fail "rebuilt wasm does NOT match $MANIFEST for host $HOST_TRIPLE"
  echo "--- recorded ---"; printf '%s\n' "$RECORDED"
  echo "--- rebuilt  ---"; printf '%s\n' "$CURRENT"
  echo
  info "Same host, different bytes: this is a real drift in the source, the"
  info "Cargo.lock, the release profile or the toolchain — not a host difference."
  exit 1
fi

# --- write: refresh this host's rows, keep every other host's verbatim -------
# A build on Linux must never silently drop the aarch64-apple-darwin rows that
# pin what is live on testnet.
OTHER_BLOCKS=""
CUR_NOTE=""
if [ -f "$MANIFEST" ]; then
  CUR_NOTE="$(awk -F' --- ' -v h="$HOST_TRIPLE" '/^# --- / && $2 == h {print $4; exit}' "$MANIFEST")"
  OTHER_BLOCKS="$(awk -F' --- ' -v h="$HOST_TRIPLE" '
    /^# --- / { keep = ($2 != h); if (keep) print; next }
    /^#/      { next }
    /^[[:space:]]*$/ { next }
    keep      { print }
  ' "$MANIFEST")"
fi

CUR_BLOCK="# --- $HOST_TRIPLE --- recorded $(date -u +%Y-%m-%dT%H:%M:%SZ)${CUR_NOTE:+ --- $CUR_NOTE}"

{
  printf '%s\n\n' "$HEADER"
  printf '%s\n' "$CUR_BLOCK"
  printf '%s' "$BODY"
  if [ -n "$OTHER_BLOCKS" ]; then
    printf '\n%s\n' "$OTHER_BLOCKS"
  fi
} > "$MANIFEST"

ok "wrote $MANIFEST (rows for $HOST_TRIPLE refreshed, other hosts kept)"
exit 0
