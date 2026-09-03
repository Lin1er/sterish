"""The skill registered on testnet must stay reproducible from committed bytes.

STE-13 registered `com.sterish.weather-lookup` v1.0.0 on Stellar testnet under
content_hash 4bf3f90c…, but the manifest it was computed from lived only in a
scratch directory. That made the on-chain record impossible for a third party to
re-derive — the exact failure `docs/specs/content-hash.md` exists to prevent.

The bytes are committed here, and this test fails the moment they drift away
from what the chain records.
"""

import json
import pathlib
import subprocess
import sys

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "weather_lookup_onchain"
REFERENCE = (
    pathlib.Path(__file__).resolve().parents[2]
    / "docs" / "specs" / "reference" / "content_hash.py"
)
DEPLOYMENTS = pathlib.Path(__file__).resolve().parents[2] / "docs" / "deployments.md"

# Recorded on-chain by STE-13; see docs/deployments.md.
ONCHAIN_HASH = "4bf3f90c4047ca2b6c950e127296da95b2ace4f99c8d777eac921358811e42dd"
ONCHAIN_SKILL_ID = "com.sterish.weather-lookup"
ONCHAIN_VERSION = "1.0.0"


def _reference_hash(path: pathlib.Path) -> str:
    """Hash via the frozen reference implementation, as a subprocess.

    Deliberately not an import: the on-chain value must be reproducible by
    anyone running the documented command, not only by this package.
    """
    out = subprocess.run(
        [sys.executable, str(REFERENCE), str(path)],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def test_committed_manifest_reproduces_the_onchain_hash():
    assert _reference_hash(FIXTURE) == ONCHAIN_HASH


def test_manifest_identity_matches_the_registered_record():
    manifest = json.loads((FIXTURE / "manifest.json").read_text())
    assert manifest["skill_id"] == ONCHAIN_SKILL_ID
    assert manifest["version"] == ONCHAIN_VERSION


def test_deployments_doc_still_cites_this_hash():
    assert ONCHAIN_HASH in DEPLOYMENTS.read_text()
