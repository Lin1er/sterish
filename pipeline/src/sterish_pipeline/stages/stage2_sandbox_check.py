"""Stage 2: run the skill and compare what it does against what it declared (STE-40).

Before STE-40 this stage could not have worked. `SkillManifest` had no entrypoint field,
so the container was handed a manifest with no code in it; the image it named was never
built; and when the run failed it fell back to re-listing the capabilities the manifest
had already declared — zero new information, dressed up as behavioural evidence.

The honest shape is narrower and says so:

* **MCP servers execute a process.** Running it under strace with no network, a read-only
  root and no capabilities produces real evidence: a `connect` to AF_INET is an attempt to
  reach the network whether or not the kernel allowed it, and an `openat` of `~/.ssh/id_rsa`
  is an attempt to read a key whether or not one was there.
* **Agent Skills published as markdown execute nothing.** Their danger is what they
  *instruct the agent* to do, which stage 1 reads. A sandbox adds nothing there.

So `applicable=False` is a first-class outcome, not a failure. Nothing ran, therefore
nothing is known — and that must never be scored as good behaviour. Rewarding the absence
of code with a clean result is the same category error this project fixed in the regex
scanner (STE-36) and found again in the model's own reasoning (STE-39). This is the third
place it could have appeared, and the one place it is cheapest to get wrong.
"""

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

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

#: Capability a violation implies, so observed behaviour can be checked against what the
#: manifest admitted to. Declaring a capability and then using it is not a finding —
#: honesty must not be punished, the same rule stage 1's `exfiltration` already follows.
_VIOLATION_CAPABILITY = {
    "SECRET_READ": Capability.SECRET_READ,
    "NETWORK_OUTBOUND": Capability.NETWORK_OUTBOUND,
    "FILE_WRITE": Capability.FILE_WRITE,
    "ENV_READ": Capability.ENV_READ,
}


def not_applicable(reason: str) -> Stage2Result:
    """Nothing was executed. Say so, and score nothing."""
    return Stage2Result(applicable=False, detail=reason)


def docker_available(binary: str = "docker") -> bool:
    return shutil.which(binary) is not None


def image_present(image: str, binary: str = "docker") -> bool:
    try:
        proc = subprocess.run(
            [binary, "image", "inspect", image],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def run_sandbox_check(
    manifest: SkillManifest,
    timeout: int | None = None,
    config: PipelineConfig | None = None,
    files: dict[str, bytes] | None = None,
) -> Stage2Result:
    """Execute the skill's entrypoint in an isolated container and report what it did.

    Every path that does not produce observations returns `applicable=False` with a
    reason, so a report can distinguish "ran and behaved" from "never ran".
    """
    cfg = config or PipelineConfig()
    effective_timeout = timeout or cfg.sandbox_timeout

    if manifest.entrypoint is None:
        return not_applicable("no entrypoint; this skill does not execute anything")

    if not docker_available():
        return not_applicable("docker is not available; nothing was executed")

    if not image_present(cfg.sandbox_image):
        return not_applicable(
            f"sandbox image {cfg.sandbox_image} is not built; nothing was executed. "
            f"Build it with: docker build -t {cfg.sandbox_image} pipeline/sandbox/"
        )

    try:
        raw = _run_container(manifest, files or {}, cfg, effective_timeout)
    except subprocess.TimeoutExpired:
        # The container outlived even the outer deadline. That is a finding, not an
        # inapplicable run: something was executed and it would not stop.
        return Stage2Result(
            applicable=True,
            detail=f"sandbox exceeded the outer {effective_timeout + 15}s deadline",
            escaped_sandbox=False,
            behavioral_flags=[
                BehavioralFlag(
                    syscall="timeout",
                    expected=False,
                    severity=Severity.HIGH,
                    description="Skill did not terminate inside the sandbox.",
                )
            ],
        )
    except Exception as exc:  # noqa: BLE001 - infrastructure failure is not a verdict
        logger.warning("sandbox run failed: %s", exc)
        return not_applicable(f"sandbox run failed ({exc}); nothing was observed")

    return _to_result(raw, manifest)


def _run_container(
    manifest: SkillManifest,
    files: dict[str, bytes],
    cfg: PipelineConfig,
    timeout: int,
) -> dict:
    """Materialise the skill's bytes and run them with everything taken away."""
    entrypoint = manifest.entrypoint
    assert entrypoint is not None  # guarded by the caller

    with tempfile.TemporaryDirectory(prefix="sterish-sandbox-") as tmp:
        root = Path(tmp)
        for name, blob in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)

        # The container runs as an unprivileged uid that is not the invoking one, and a
        # tempdir is 0700 by default — so the mount would be there and unreadable. Made
        # world-readable rather than running the sandbox as root, which would trade a
        # permission bug for a much worse one. The bytes are public audit material and
        # the directory is deleted when this block exits.
        root.chmod(0o755)
        for path in root.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)

        job = json.dumps({
            "command": entrypoint.command,
            "args": entrypoint.args,
            "env": entrypoint.env,
            "timeout": timeout,
        })

        cmd = [
            "docker", "run", "--rm", "-i",
            # No network at all: a connect() still shows up in the trace, which is the
            # attempt we want to see, without the packet ever leaving.
            "--network", "none",
            "--read-only",
            "--cap-drop", "ALL",
            # The one capability added back, and only because strace cannot work without
            # it. Everything else is still dropped, there is no network, the root
            # filesystem is read-only and nothing from the host is mounted.
            "--cap-add", "SYS_PTRACE",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "128",
            "--memory", "256m",
            "--cpus", "0.5",
            "--mount", "type=tmpfs,destination=/tmp,tmpfs-size=64m",
            # The skill's own bytes, read-only. This is the only thing it can see.
            "--mount", f"type=bind,source={root},destination=/skill,readonly",
            cfg.sandbox_image,
        ]

        proc = subprocess.run(
            cmd, input=job, capture_output=True, text=True,
            # Outer deadline sits above the runner's own, so a wedged container is
            # still reaped rather than hanging the audit.
            timeout=timeout + 15,
        )

    if proc.returncode != 0 and not proc.stdout.strip():
        raise RuntimeError(f"container exited {proc.returncode}: {proc.stderr[:300]}")

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"runner produced no usable JSON: {proc.stdout[:200]}") from exc


def _to_result(raw: dict, manifest: SkillManifest) -> Stage2Result:
    """Turn the runner's report into a stage result, dropping declared behaviour."""
    if not raw.get("ran"):
        return not_applicable(raw.get("detail") or "nothing was executed")

    # Explicit only: the normaliser adds an implied `:server` tool carrying
    # NETWORK_OUTBOUND to any manifest with a command. Comparing against that would mean
    # a skill promising "local only" and then phoning home comes back clean.
    declared = manifest.declared_capabilities(explicit_only=True)

    calls = [
        ObservedCall(
            syscall=call.get("syscall", ""),
            args=call.get("args", {}),
            timestamp=float(call.get("ts", 0.0) or 0.0),
        )
        for call in raw.get("calls", [])
    ]

    flags: list[BehavioralFlag] = []
    for violation in raw.get("violations", []):
        capability = _VIOLATION_CAPABILITY.get(violation.get("capability") or "")
        was_declared = capability is not None and capability in declared
        if was_declared:
            # Declared and then used: disclosed risk, already priced in by stage 1.
            # Recording it as a behavioural finding would punish an honest manifest.
            continue
        flags.append(
            BehavioralFlag(
                syscall=violation.get("syscall", ""),
                expected=False,
                severity=Severity(violation.get("severity", "MEDIUM")),
                description=violation.get("description", ""),
            )
        )

    return Stage2Result(
        applicable=True,
        detail=raw.get("detail", ""),
        behavioral_flags=flags,
        observed_calls=calls,
        escaped_sandbox=bool(raw.get("escaped", False)),
    )
