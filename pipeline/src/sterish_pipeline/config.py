from pathlib import Path

from pydantic import BaseModel, Field

#: Canonical Stellar **testnet** network passphrase. Verified against RPC ``getNetwork``
#: during STE-13. Any other value makes signed transactions rejected by the network.
TESTNET_PASSPHRASE = "Test SDF Network ; September 2015"
PUBNET_PASSPHRASE = "Public Global Stellar Network ; September 2015"


class PipelineConfig(BaseModel):
    """Configuration for the audit pipeline."""

    # Weights for trust score computation (must sum to 100).
    stage1_weight: int = Field(ge=0, le=100, default=40)
    stage2_weight: int = Field(ge=0, le=100, default=60)

    # Score thresholds for verdicts.
    safe_threshold: int = Field(ge=0, le=100, default=70)
    warning_threshold: int = Field(ge=0, le=100, default=40)

    # Sandbox settings.
    sandbox_timeout: int = Field(default=30, description="Seconds before killing sandbox")
    sandbox_image: str = "sterish/sandbox:latest"

    # On-chain settings.
    registry_contract_id: str = ""
    # NOTE: the Stellar testnet passphrase is "... September 2015". The scaffold said 2024,
    # which makes every signed transaction fail network validation. Locked by test_config.py.
    network_passphrase: str = TESTNET_PASSPHRASE
    rpc_url: str = "https://soroban-testnet.stellar.org:443"

    # Risk scoring deductions for DECLARED capabilities (stage 1a).
    high_risk_deduction: int = 25
    medium_risk_deduction: int = 10
    low_risk_deduction: int = 3

    # Risk scoring deductions for INJECTION findings (stage 1b). Heavier than the declared
    # ones on purpose: a declared WALLET_ACCESS is a disclosed risk a user can weigh, while
    # an instruction hidden in prose is an attempt to act without the user knowing at all.
    injection_high_deduction: int = 40
    injection_medium_deduction: int = 15
    injection_low_deduction: int = 5

    # Ceiling applied to the score when a critical-class pattern fires (policy.py).
    critical_max_score: int = Field(ge=0, le=100, default=10)

    # Stage 3 LLM synthesis. The key is read from the ANTHROPIC_API_KEY environment
    # variable only and is never written to config files or to the verdict document.
    use_llm: bool = True
    llm_model: str = "claude-sonnet-5"
    llm_timeout_s: int = 60
    llm_max_tokens: int = 2048

    @classmethod
    def load(cls, path: Path | str | None = None) -> "PipelineConfig":
        """Load config from a JSON file, falling back to defaults."""
        if path is None:
            return cls()
        p = Path(path)
        if not p.exists():
            return cls()
        import json

        with p.open() as f:
            data = json.load(f)
        return cls(**data)
