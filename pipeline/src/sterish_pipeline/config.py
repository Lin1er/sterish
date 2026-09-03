from pathlib import Path

from pydantic import BaseModel, Field


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
    network_passphrase: str = "Test SDF Network ; September 2015"
    rpc_url: str = "https://soroban-testnet.stellar.org:443"

    # Risk scoring deductions.
    high_risk_deduction: int = 25
    medium_risk_deduction: int = 10
    low_risk_deduction: int = 3

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
