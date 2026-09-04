"""The report bytes and the on-chain evidence_hash must stay in lockstep."""

import hashlib
import json

from sterish_pipeline import reports

DOC = {"skill_id": "com.acme.demo", "version": "1.0.0", "verdict": "SAFE", "score": 88}


def test_published_hash_matches_the_bytes_on_disk(tmp_path):
    published = reports.publish(DOC, "com.acme.demo", "1.0.0", tmp_path)
    on_disk = published.path.read_bytes()
    assert hashlib.sha256(on_disk).hexdigest() == published.evidence_hash
    assert published.size == len(on_disk)


def test_a_third_party_can_recompute_the_hash(tmp_path):
    published = reports.publish(DOC, "com.acme.demo", "1.0.0", tmp_path)
    assert reports.verify(published.path, published.evidence_hash) is True


def test_one_changed_field_changes_the_hash(tmp_path):
    a = reports.publish(DOC, "com.acme.demo", "1.0.0", tmp_path)
    b = reports.publish({**DOC, "score": 87}, "com.acme.demo", "1.0.1", tmp_path)
    assert a.evidence_hash != b.evidence_hash


def test_serialisation_is_stable_across_key_order():
    """The hash must not depend on how the dict happened to be built."""
    shuffled = {k: DOC[k] for k in reversed(list(DOC))}
    assert reports.evidence_hash_of(DOC) == reports.evidence_hash_of(shuffled)


def test_published_file_is_valid_json(tmp_path):
    published = reports.publish(DOC, "com.acme.demo", "1.0.0", tmp_path)
    assert json.loads(published.path.read_text()) == DOC


def test_report_uri_falls_back_to_a_file_uri(tmp_path):
    published = reports.publish(DOC, "com.acme.demo", "1.0.0", tmp_path)
    assert published.uri().startswith("file://")
    assert published.uri("https://x.dev/reports") == "https://x.dev/reports/1.0.0.json"
