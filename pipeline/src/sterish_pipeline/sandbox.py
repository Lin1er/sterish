"""Docker/WASM sandbox runner for skill execution."""

import json
import logging
import subprocess

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import SkillManifest

logger = logging.getLogger(__name__)


def run_in_docker(
    manifest: SkillManifest,
    image: str | None = None,
    timeout: int = 30,
) -> dict:
    """Run a skill in an isolated Docker container and return structured output.

    Returns a dict with keys: calls (list), violations (list), escaped (bool).
    """
    cfg = PipelineConfig.load()
    effective_image = image or cfg.sandbox_image

    cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--memory", "128m",
        "--cpus", "0.5",
        "--mount", "type=tmpfs,destination=/tmp,tmpfs-size=64m",
        effective_image,
        "sterish-sandbox-runner",
        json.dumps(manifest.model_dump()),
    ]

    logger.info("Running sandbox: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    if proc.returncode != 0:
        raise RuntimeError(
            f"Sandbox failed (exit {proc.returncode}): {proc.stderr[:500]}"
        )

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Sandbox produced invalid JSON: {proc.stdout[:200]}") from exc


def prepare_sandbox_image(image: str = "sterish/sandbox:latest") -> None:
    """Build or pull the sandbox Docker image."""
    logger.info("Ensuring sandbox image %s is available", image)
    subprocess.run(
        ["docker", "pull", image],
        capture_output=True,
        text=True,
        timeout=120,
    )


def cleanup_sandbox() -> None:
    """Remove dangling sandbox containers and images."""
    subprocess.run(
        ["docker", "container", "prune", "--force", "--filter", "label=sterish-sandbox"],
        capture_output=True,
        text=True,
        timeout=30,
    )
