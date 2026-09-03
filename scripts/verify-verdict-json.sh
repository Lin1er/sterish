#!/usr/bin/env bash
# Verdict-JSON schema gate for docs/specs/.
#
# Runs every example in docs/specs/examples/ against docs/specs/verdict.schema.json
# and asserts each one lands on its expected side: valid-* accepted,
# invalid-* rejected, submittable-* accepted by the base schema but rejected by
# the SubmittableVerdict profile (the UNAUDITED invariant the contract enforces
# as RegistryError::InvalidVerdict).
#
# Exit 0 only when every expectation holds.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 docs/specs/examples/validate_examples.py "$@"
