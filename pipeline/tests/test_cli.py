"""The CLI must run the same pipeline as the library, not an older copy of it."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from sterish_pipeline import specs
from sterish_pipeline.cli import cli

FIXTURES = Path(__file__).parent / "fixtures"
POISONED_PDF = str(FIXTURES / "poisoned_pdf_skill")
SAFE_SKILL = str(FIXTURES / "safe_skill")


@pytest.fixture
def runner():
    return CliRunner()


class TestAuditCommand:
    def test_poisoned_pdf_exits_nonzero_and_says_dangerous(self, runner):
        result = runner.invoke(cli, ["audit", POISONED_PDF, "--skip-sandbox"])
        assert result.exit_code == 1
        assert "DANGEROUS" in result.output

    def test_safe_skill_exits_zero(self, runner):
        result = runner.invoke(cli, ["audit", SAFE_SKILL, "--skip-sandbox"])
        assert result.exit_code == 0
        assert "SAFE" in result.output

    def test_cli_uses_the_new_scanner(self, runner):
        """The regression that matters: the CLI must report the injection findings."""
        result = runner.invoke(cli, ["audit", POISONED_PDF, "--skip-sandbox"])
        assert "injection finding" in result.output
        assert "credential_path" in result.output

    def test_json_output_validates_against_the_frozen_schema(self, runner):
        result = runner.invoke(cli, ["audit", SAFE_SKILL, "--skip-sandbox", "--json"])
        assert specs.schema_error(json.loads(result.output)) is None

    def test_out_writes_a_valid_document(self, runner, tmp_path):
        out = tmp_path / "verdict.json"
        runner.invoke(cli, ["audit", POISONED_PDF, "--skip-sandbox", "-o", str(out)])
        assert specs.schema_error(json.loads(out.read_text())) is None

    def test_manifest_alias_still_works(self, runner):
        result = runner.invoke(
            cli, ["audit", "--manifest", f"{SAFE_SKILL}/manifest.json", "--skip-sandbox"]
        )
        assert result.exit_code == 0

    def test_mismatched_skill_id_is_an_error(self, runner):
        result = runner.invoke(
            cli, ["audit", SAFE_SKILL, "--skip-sandbox", "--skill-id", "com.other.thing"]
        )
        assert result.exit_code == 2

    def test_no_argument_is_a_usage_error(self, runner):
        assert runner.invoke(cli, ["audit"]).exit_code != 0

    def test_no_llm_flag_disables_the_model(self, runner):
        result = runner.invoke(cli, ["audit", SAFE_SKILL, "--skip-sandbox", "--no-llm"])
        assert result.exit_code == 0


class TestHashCommand:
    def test_hash_matches_the_frozen_reference(self, runner):
        result = runner.invoke(cli, ["hash", str(Path(__file__).parent / "poisoned_skill")])
        assert result.output.strip() == (
            "c2bd4a316415b4919e3f1f40d9925f4052d020cf3dc2ecabe0e7c9dd28cc87f0"
        )
