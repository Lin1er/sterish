"""Stage 2: Sandboxed behavior monitoring."""

import json
import logging
import subprocess

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import (
    BehavioralFlag,
    Capability,
    ObservedCall,
    Severity,
    SkillManifest,
    Stage2Result,
)

logger = logging.getLogger(__name__)


_high_caps = {Capability.WALLET_ACCESS, Capability.SECRET_READ, Capability.NETWORK_OUTBOUND}
_medium_caps = {Capability.FILE_WRITE, Capability.ENV_READ}


def run_sandbox_check(
    manifest: SkillManifest,
    timeout: int | None = None,
    config: PipelineConfig | None = None,
) -> Stage2Result:
    """Run a skill in a sandboxed Docker container and monitor its behaviour.

    If Docker is not available, falls back to a static analysis mode that flags
    capabilities declared in the manifest as potential risks.
    """
    cfg = config or PipelineConfig()
    effective_timeout = timeout or cfg.sandbox_timeout

    declared_caps: set[Capability] = set()
    for tool in manifest.tools:
        declared_caps.update(tool.capabilities)

    try:
        result = _run_docker_sandbox(manifest, cfg.sandbox_image, effective_timeout)
        observed_calls, behavioral_flags, escaped = _parse_sandbox_output(result)
    except FileNotFoundError:
        logger.warning("Docker not available, falling back to static analysis")
        behavioral_flags = _static_fallback(declared_caps)
        observed_calls = []
        escaped = False
    except subprocess.TimeoutExpired:
        logger.warning("Sandbox timed out after %d seconds", effective_timeout)
        behavioral_flags = [
            BehavioralFlag(
                syscall="timeout",
                expected=False,
                severity=Severity.HIGH,
                description="Skill did not terminate within the allowed timeout.",
            )
        ]
        observed_calls = []
        escaped = True
    except Exception as exc:
        logger.error("Sandbox execution failed: %s", exc)
        behavioral_flags = _static_fallback(declared_caps)
        observed_calls = []
        escaped = False

    return Stage2Result(
        behavioral_flags=behavioral_flags,
        observed_calls=observed_calls,
        escaped_sandbox=escaped,
    )


def _run_docker_sandbox(manifest: SkillManifest, image: str, timeout: int) -> str:
    """Execute the skill manifest in a sandboxed Docker container."""
    cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--memory", "128m",
        "--cpus", "0.5",
        image,
        "sterish-sandbox-runner",
        json.dumps(manifest.model_dump()),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"Sandbox exited with code {proc.returncode}: {proc.stderr}")
    return proc.stdout


def _parse_sandbox_output(
    output: str,
) -> tuple[list[ObservedCall], list[BehavioralFlag], bool]:
    """Parse the JSON output from the sandbox runner."""
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return [], [], False

    calls = [
        ObservedCall(
            syscall=c.get("syscall", ""),
            args=c.get("args", {}),
            timestamp=c.get("ts", 0.0),
        )
        for c in data.get("calls", [])
    ]

    flags: list[BehavioralFlag] = []
    escaped = data.get("escaped", False)
    for violation in data.get("violations", []):
        flags.append(
            BehavioralFlag(
                syscall=violation.get("syscall", ""),
                expected=False,
                severity=Severity(violation.get("severity", "MEDIUM")),
                description=violation.get("description", ""),
            )
        )

    return calls, flags, escaped


def _static_fallback(declared_caps: set[Capability]) -> list[BehavioralFlag]:
    """When Docker is unavailable, produce behavioral flags from declared caps."""
    flags: list[BehavioralFlag] = []
    for cap in declared_caps:
        if cap in _high_caps:
            sev = Severity.HIGH
        elif cap in _medium_caps:
            sev = Severity.MEDIUM
        else:
            sev = Severity.LOW
        flags.append(
            BehavioralFlag(
                syscall=cap.value,
                expected=True,
                severity=sev,
                description=(
                    f"Declared {cap.value} could not be sandbox-verified "
                    "(Docker unavailable)."
                ),
            )
        )
    return flags
