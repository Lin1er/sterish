#!/usr/bin/env bash
#
# STE-10 — cross-language proof for the canonical `content_hash` v1.
#
# Runs the three independent reference implementations over the SAME shared
# vector file and asserts their reports are byte-identical:
#
#   Python     docs/specs/reference/content_hash.py --vectors
#   TypeScript docs/specs/reference/contentHash.ts  --vectors   (via npx tsx)
#   Rust       contracts/registry/src/test.rs                   (env.crypto().sha256)
#
# The Rust side hardcodes its vectors and expected hashes, so it is a genuinely
# independent witness rather than a re-read of the JSON file.
#
# Exit codes: 0 = all three agree and every relation/error expectation holds.
#             1 = a real disagreement (this is the failure the ticket cares about).
#             2 = the harness itself could not run (missing tool, etc.).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY_IMPL="docs/specs/reference/content_hash.py"
TS_IMPL="docs/specs/reference/contentHash.ts"
VECTORS="docs/specs/vectors/content-hash-vectors.json"
POISONED_FIXTURE="docs/specs/vectors/fixtures/poisoned_skill"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fail()  { printf '\033[31mFAIL\033[0m  %s\n' "$1" >&2; }
ok()    { printf '\033[32mok\033[0m    %s\n' "$1"; }
info()  { printf '      %s\n' "$1"; }
die()   { printf '\033[31mHARNESS\033[0m %s\n' "$1" >&2; exit 2; }

for f in "$PY_IMPL" "$TS_IMPL" "$VECTORS"; do
  [ -f "$f" ] || die "missing $f"
done
command -v python3 >/dev/null || die "python3 not found"
command -v npx     >/dev/null || die "npx not found"
command -v cargo   >/dev/null || die "cargo not found"

STATUS=0

# ---------------------------------------------------------------------------
# 1. Collect the three reports.
# ---------------------------------------------------------------------------
info "running Python reference implementation..."
if ! python3 "$PY_IMPL" --vectors "$VECTORS" > "$WORK/python.txt" 2> "$WORK/python.err"; then
  fail "python reference implementation exited non-zero"
  cat "$WORK/python.err" >&2
  STATUS=1
fi

info "running TypeScript reference implementation..."
if ! npx --yes tsx "$TS_IMPL" --vectors "$VECTORS" > "$WORK/typescript.txt" 2> "$WORK/typescript.err"; then
  fail "typescript reference implementation exited non-zero"
  cat "$WORK/typescript.err" >&2
  STATUS=1
fi

info "running Rust reference implementation (soroban env.crypto().sha256)..."
if ! ( cd contracts && cargo test -p sterish-registry \
        test_content_hash_v1 -- --nocapture --test-threads=1 ) > "$WORK/rust.raw" 2>&1; then
  fail "rust content_hash tests exited non-zero"
  tail -40 "$WORK/rust.raw" >&2
  STATUS=1
fi
# cargo's own progress output ("running 8 tests", dots) can share a line with the
# first report line, so anchor on the marker anywhere and strip up to it.
sed -n 's/.*STERISH_HASH //p' "$WORK/rust.raw" > "$WORK/rust.txt"

for impl in python typescript rust; do
  if [ ! -s "$WORK/$impl.txt" ]; then
    fail "$impl produced an empty report"
    STATUS=1
  fi
done
[ "$STATUS" -eq 0 ] || { printf '\naborting: at least one implementation did not produce a report\n' >&2; exit 1; }

# ---------------------------------------------------------------------------
# 2. Three-way byte-exact comparison of the reports.
# ---------------------------------------------------------------------------
compare() { # compare <a> <b>
  if diff -u "$WORK/$1.txt" "$WORK/$2.txt" > "$WORK/diff-$1-$2.txt"; then
    ok "$1 report == $2 report"
  else
    fail "$1 and $2 DISAGREE:"
    cat "$WORK/diff-$1-$2.txt" >&2
    STATUS=1
  fi
}
compare python typescript
compare python rust
compare typescript rust

# ---------------------------------------------------------------------------
# 3. Independent re-check of the invariants the ticket names explicitly,
#    parsed out of the (already agreed) report rather than trusted from it.
# ---------------------------------------------------------------------------
REPORT="$WORK/python.txt"

hash_of() { awk -v id="$1" '$1=="VECTOR" && $2==id {print $3}' "$REPORT"; }

n_vectors=$(awk '$1=="VECTOR"' "$REPORT" | wc -l | tr -d ' ')
n_errors=$(awk '$1=="ERROR"'  "$REPORT" | wc -l | tr -d ' ')
info "$n_vectors vectors, $n_errors error cases"
if [ "$n_vectors" -lt 5 ]; then
  fail "the spec requires at least 5 vectors, found $n_vectors"
  STATUS=1
fi

for h in $(awk '$1=="VECTOR" {print $3}' "$REPORT"); do
  if ! printf '%s' "$h" | grep -Eq '^[0-9a-f]{64}$'; then
    fail "hash '$h' is not 64 lowercase hex chars"
    STATUS=1
  fi
done

# crlf-equals-lf MUST equal single-file.
a=$(hash_of crlf-equals-lf); b=$(hash_of single-file)
if [ -n "$a" ] && [ "$a" = "$b" ]; then
  ok "crlf-equals-lf == single-file  ($a)"
else
  fail "crlf-equals-lf ($a) must equal single-file ($b)"
  STATUS=1
fi

# one-byte-flip MUST differ from single-file.
a=$(hash_of one-byte-flip)
if [ -n "$a" ] && [ "$a" != "$b" ]; then
  ok "one-byte-flip != single-file  ($a)"
else
  fail "one-byte-flip ($a) must differ from single-file ($b)"
  STATUS=1
fi

# Length prefixing: ("a","bc") must not collide with ("ab","c").
a=$(hash_of concat-ambiguity-a); c=$(hash_of concat-ambiguity-b)
if [ -n "$a" ] && [ "$a" != "$c" ]; then
  ok "concat-ambiguity-a != concat-ambiguity-b"
else
  fail "length prefixing is broken: $a vs $c"
  STATUS=1
fi

# Every RELATION line must be OK, every ERROR line must not be NO_ERROR.
if awk '$1=="RELATION" && $NF!="OK"' "$REPORT" | grep -q .; then
  fail "some RELATION expectations failed:"
  awk '$1=="RELATION" && $NF!="OK"' "$REPORT" >&2
  STATUS=1
else
  ok "all RELATION expectations hold"
fi
if awk '$1=="ERROR" && $3=="NO_ERROR"' "$REPORT" | grep -q .; then
  fail "some error cases were silently hashed instead of rejected:"
  awk '$1=="ERROR" && $3=="NO_ERROR"' "$REPORT" >&2
  STATUS=1
else
  ok "all $n_errors error cases rejected with the expected error kind"
fi

# ---------------------------------------------------------------------------
# 4. The vector file's frozen expected_sha256 values must match what was just
#    computed (the impls already assert this internally; re-check it here so a
#    hand-edited JSON cannot slip through).
# ---------------------------------------------------------------------------
if python3 - "$VECTORS" "$REPORT" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
frozen = {v["id"]: v.get("expected_sha256") for v in doc["vectors"]}
bad = []
for line in open(sys.argv[2], encoding="utf-8"):
    parts = line.split()
    if len(parts) == 3 and parts[0] == "VECTOR":
        _, vid, got = parts
        if frozen.get(vid) != got:
            bad.append(f"{vid}: file says {frozen.get(vid)}, computed {got}")
for b in bad:
    print(b, file=sys.stderr)
sys.exit(1 if bad else 0)
PY
then
  ok "expected_sha256 in $VECTORS matches every computed hash"
else
  fail "the frozen expected_sha256 values do not match the computed hashes"
  STATUS=1
fi

# ---------------------------------------------------------------------------
# 5. Directory-packager cross-check: hashing the real on-disk poisoned fixture
#    must reproduce the poisoned-token-drainer vector in both Python and TS.
# ---------------------------------------------------------------------------
if [ -d "$POISONED_FIXTURE" ]; then
  want=$(hash_of poisoned-token-drainer)
  got_py=$(python3 "$PY_IMPL" "$POISONED_FIXTURE")
  got_ts=$(npx --yes tsx "$TS_IMPL" "$POISONED_FIXTURE")
  if [ "$got_py" = "$want" ] && [ "$got_ts" = "$want" ]; then
    ok "directory packager reproduces the poisoned fixture vector ($want)"
  else
    fail "packager drift: vector=$want python=$got_py typescript=$got_ts"
    STATUS=1
  fi
else
  fail "missing fixture directory $POISONED_FIXTURE"
  STATUS=1
fi

printf '\n'
if [ "$STATUS" -eq 0 ]; then
  printf '\033[32mPASS\033[0m  Python, TypeScript and Rust agree on all %s content_hash vectors.\n' "$n_vectors"
  printf '      Frozen hashes:\n'
  awk '$1=="VECTOR" {printf "        %-26s %s\n", $2, $3}' "$REPORT"
else
  printf '\033[31mFAIL\033[0m  content_hash implementations disagree — see above.\n' >&2
fi
exit "$STATUS"
