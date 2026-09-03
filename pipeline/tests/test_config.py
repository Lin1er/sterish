"""Locks the values in PipelineConfig that a wrong constant would silently break."""

import json
from pathlib import Path

from sterish_pipeline.config import PUBNET_PASSPHRASE, TESTNET_PASSPHRASE, PipelineConfig


class TestNetworkPassphrase:
    def test_testnet_passphrase_is_september_2015(self):
        # Verified against Stellar RPC getNetwork during STE-13. The scaffold shipped
        # "September 2024", which makes every signed transaction fail network validation.
        assert TESTNET_PASSPHRASE == "Test SDF Network ; September 2015"

    def test_default_config_uses_testnet_passphrase(self):
        assert PipelineConfig().network_passphrase == TESTNET_PASSPHRASE

    def test_passphrase_is_not_the_broken_2024_value(self):
        assert "2024" not in PipelineConfig().network_passphrase

    def test_pubnet_passphrase_is_distinct(self):
        assert PUBNET_PASSPHRASE != TESTNET_PASSPHRASE
        assert PUBNET_PASSPHRASE.startswith("Public Global Stellar Network")


class TestConfigLoading:
    def test_load_none_returns_defaults(self):
        assert PipelineConfig.load(None) == PipelineConfig()

    def test_load_missing_file_returns_defaults(self, tmp_path: Path):
        assert PipelineConfig.load(tmp_path / "nope.json") == PipelineConfig()

    def test_load_overrides_from_file(self, tmp_path: Path):
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps({"safe_threshold": 88}))
        assert PipelineConfig.load(p).safe_threshold == 88
