"""Stage 2 runs the skill, or admits it ran nothing (STE-40).

The test that used to live here asserted the opposite of what this stage now promises:
it pinned `_static_fallback`, which turned the manifest's own declared capabilities into
"behavioural" flags. That produced no new information and presented it as evidence. It is
gone, and so are its tests.

What is pinned instead is the distinction the stage exists to preserve: **ran and behaved**
is not the same claim as **never ran**, and only the first one may ever count as clean.
"""

import pathlib
import shutil
import subprocess

import pytest

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import (
    Capability,
    Entrypoint,
    Severity,
    SkillManifest,
    ToolDef,
)
from sterish_pipeline.stages import stage2_sandbox_check as stage2

DOCKER = shutil.which("docker") is not None
needs_docker = pytest.mark.skipif(not DOCKER, reason="docker is not available")


def _manifest(caps=(), entrypoint: Entrypoint | None = None) -> SkillManifest:
    return SkillManifest(
        skill_id="test.sandbox",
        name="Sandbox Test",
        description="Test",
        version="1.0.0",
        permissions=[],
        tools=[ToolDef(name="t", description="", input_schema={}, capabilities=list(caps))],
        entrypoint=entrypoint,
    )


NODE = Entrypoint(command="node", args=["./server.js"])


def _runner_says(monkeypatch, payload: dict) -> None:
    """Pretend the container ran and returned this report."""
    monkeypatch.setattr(stage2, "docker_available", lambda *a, **k: True)
    monkeypatch.setattr(stage2, "image_present", lambda *a, **k: True)
    monkeypatch.setattr(stage2, "_run_container", lambda *a, **k: payload)


class TestNothingToRun:
    """`applicable=False` is an answer, not a failure — and never a clean one."""

    def test_no_entrypoint_is_not_applicable(self):
        result = stage2.run_sandbox_check(_manifest([Capability.WALLET_ACCESS]))
        assert result.applicable is False
        assert result.behavioral_flags == []
        assert "does not execute" in result.detail

    def test_declared_capabilities_do_not_become_behavioural_flags(self):
        """The regression this file exists for.

        A manifest declaring WALLET_ACCESS and NETWORK_OUTBOUND used to come back with two
        HIGH "behavioural" flags without anything being executed. Declared risk is stage
        1's business; inventing observations is nobody's.
        """
        result = stage2.run_sandbox_check(
            _manifest([Capability.WALLET_ACCESS, Capability.NETWORK_OUTBOUND])
        )
        assert result.behavioral_flags == []
        assert result.applicable is False

    def test_missing_docker_is_not_applicable(self, monkeypatch):
        monkeypatch.setattr(stage2, "docker_available", lambda *a, **k: False)
        result = stage2.run_sandbox_check(_manifest(entrypoint=NODE))
        assert result.applicable is False
        assert "docker" in result.detail.lower()

    def test_missing_image_says_how_to_build_it(self, monkeypatch):
        monkeypatch.setattr(stage2, "docker_available", lambda *a, **k: True)
        monkeypatch.setattr(stage2, "image_present", lambda *a, **k: False)
        result = stage2.run_sandbox_check(_manifest(entrypoint=NODE))
        assert result.applicable is False
        assert "docker build" in result.detail

    def test_infrastructure_failure_is_not_a_verdict(self, monkeypatch):
        monkeypatch.setattr(stage2, "docker_available", lambda *a, **k: True)
        monkeypatch.setattr(stage2, "image_present", lambda *a, **k: True)

        def boom(*a, **k):
            raise RuntimeError("daemon went away")

        monkeypatch.setattr(stage2, "_run_container", boom)
        result = stage2.run_sandbox_check(_manifest(entrypoint=NODE))
        assert result.applicable is False
        assert result.behavioral_flags == []

    def test_runner_reporting_it_did_not_run_is_not_applicable(self, monkeypatch):
        _runner_says(monkeypatch, {"ran": False, "detail": "entrypoint not runnable"})
        result = stage2.run_sandbox_check(_manifest(entrypoint=NODE))
        assert result.applicable is False


class TestObservedVsDeclared:
    def test_undeclared_network_is_a_finding(self, monkeypatch):
        _runner_says(monkeypatch, {
            "ran": True, "detail": "ran node for 0.4s", "calls": [],
            "violations": [{
                "syscall": "connect", "severity": "HIGH",
                "description": "Attempted an outbound network connection.",
                "capability": "NETWORK_OUTBOUND",
            }],
        })
        result = stage2.run_sandbox_check(_manifest(entrypoint=NODE))
        assert result.applicable is True
        assert len(result.behavioral_flags) == 1
        assert result.behavioral_flags[0].severity is Severity.HIGH

    def test_a_declared_capability_used_is_not_a_finding(self, monkeypatch):
        """Honesty is not punished — the same rule stage 1's exfiltration already follows.

        A skill that says it reaches the network and then does is behaving exactly as
        advertised. Flagging that would make declaring capabilities strictly worse than
        hiding them.
        """
        _runner_says(monkeypatch, {
            "ran": True, "detail": "ran", "calls": [],
            "violations": [{
                "syscall": "connect", "severity": "HIGH",
                "description": "Attempted an outbound network connection.",
                "capability": "NETWORK_OUTBOUND",
            }],
        })
        result = stage2.run_sandbox_check(
            _manifest([Capability.NETWORK_OUTBOUND], entrypoint=NODE)
        )
        assert result.applicable is True
        assert result.behavioral_flags == []

    def test_undeclared_secret_read_is_a_finding(self, monkeypatch):
        _runner_says(monkeypatch, {
            "ran": True, "detail": "ran", "calls": [],
            "violations": [{
                "syscall": "openat", "severity": "HIGH",
                "description": "Opened SSH key material at /home/runner/.ssh/id_rsa.",
                "capability": "SECRET_READ",
            }],
        })
        result = stage2.run_sandbox_check(_manifest(entrypoint=NODE))
        assert [f.syscall for f in result.behavioral_flags] == ["openat"]

    def test_observed_calls_are_carried_through(self, monkeypatch):
        _runner_says(monkeypatch, {
            "ran": True, "detail": "ran", "violations": [],
            "calls": [{"syscall": "openat", "args": {"path": "/skill/server.js"}, "ts": 0.1}],
        })
        result = stage2.run_sandbox_check(_manifest(entrypoint=NODE))
        assert result.applicable is True
        assert result.observed_calls[0].syscall == "openat"
        # Ran and observed nothing bad: this is the only shape that means "clean".
        assert result.behavioral_flags == []

    def test_outer_timeout_is_a_finding_not_an_inapplicable_run(self, monkeypatch):
        monkeypatch.setattr(stage2, "docker_available", lambda *a, **k: True)
        monkeypatch.setattr(stage2, "image_present", lambda *a, **k: True)

        def hang(*a, **k):
            raise subprocess.TimeoutExpired(cmd="docker", timeout=1)

        monkeypatch.setattr(stage2, "_run_container", hang)
        result = stage2.run_sandbox_check(_manifest(entrypoint=NODE))
        assert result.applicable is True, "something was executed; it would not stop"
        assert result.behavioral_flags[0].syscall == "timeout"


class TestRunnerParsing:
    """The trace parser, exercised directly — it decides what counts as observed."""

    @staticmethod
    def _parse(text: str):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "sandbox" / "runner.py"
        spec = importlib.util.spec_from_file_location("sterish_sandbox_runner", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.parse_trace(text)

    def test_inet_connect_is_a_violation(self):
        _, violations = self._parse('connect(3, {sa_family=AF_INET, sin_port=htons(443)}, 16)')
        assert violations[0]["capability"] == "NETWORK_OUTBOUND"

    def test_unix_socket_connect_is_ordinary_plumbing(self):
        _, violations = self._parse('connect(3, {sa_family=AF_UNIX, sun_path="/tmp/x"}, 110)')
        assert violations == []

    @pytest.mark.parametrize(
        "path",
        ["/home/runner/.ssh/id_rsa", "/home/runner/.aws/credentials",
         "/skill/.env", "/proc/self/environ"],
    )
    def test_credential_paths_are_violations(self, path):
        _, violations = self._parse(f'openat(AT_FDCWD, "{path}", O_RDONLY) = 3')
        assert violations and violations[0]["capability"] == "SECRET_READ"

    def test_ordinary_file_reads_are_not_violations(self):
        calls, violations = self._parse('openat(AT_FDCWD, "/skill/server.js", O_RDONLY) = 3')
        assert violations == []
        assert calls[0]["args"]["path"] == "/skill/server.js"

    def test_the_first_execve_is_the_entrypoint_not_a_finding(self):
        _, violations = self._parse('execve("/usr/bin/node", ["node"], 0x7ffd) = 0')
        assert violations == []

    def test_a_second_execve_is_a_spawned_process(self):
        trace = (
            'execve("/usr/bin/node", ["node"], 0x1) = 0\n'
            'execve("/bin/sh", ["sh", "-c", "curl evil"], 0x2) = 0'
        )
        _, violations = self._parse(trace)
        assert [v["capability"] for v in violations] == ["PROCESS_SPAWN"]

    def test_pid_prefixed_lines_from_forked_children_are_parsed(self):
        _, violations = self._parse(
            '[pid  1234] connect(3, {sa_family=AF_INET, sin_port=htons(80)}, 16)'
        )
        assert violations[0]["capability"] == "NETWORK_OUTBOUND"

    def test_noise_is_ignored(self):
        calls, violations = self._parse("+++ exited with 0 +++\n--- SIGCHLD ---\ngarbage")
        assert calls == [] and violations == []


@needs_docker
class TestAgainstRealDocker:
    """Opt-in. Proves the container arguments are accepted by a real daemon.

    Skipped in CI, which has no daemon — and that skip is exactly why the stage returns
    `applicable=False` there rather than a clean pass.
    """

    def test_image_present_is_honest_about_a_missing_image(self):
        assert stage2.image_present("sterish/definitely-not-built:latest") is False

    def test_docker_available_agrees_with_the_path(self):
        assert stage2.docker_available() is True


SANDBOX_FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "sandbox"
IMAGE_BUILT = DOCKER and stage2.image_present(PipelineConfig().sandbox_image)
needs_sandbox = pytest.mark.skipif(
    not IMAGE_BUILT,
    reason="sandbox image not built (docker build -t sterish/sandbox:latest pipeline/sandbox/)",
)


def _fixture(name: str):
    """Normalise a sandbox fixture the way intake would."""
    from sterish_pipeline.intake.normalize import normalize_mcp_server

    root = SANDBOX_FIXTURES / name
    files = {f.name: f.read_bytes() for f in root.iterdir() if f.is_file()}
    return normalize_mcp_server(f"com.fixtures.sandbox.{name}", "1.0.0", files), files


@needs_sandbox
class TestRealSandbox:
    """The claim "sandboxed behavior check" being literally true, against real containers.

    These are the tests that stop stage 2 from being a description of an intention. They
    need a built image and are skipped without one — which is also why the stage reports
    `applicable=False` in that situation rather than a clean pass.
    """

    def test_an_honest_skill_produces_observations_and_no_findings(self):
        skill, files = _fixture("honest")
        result = stage2.run_sandbox_check(skill.manifest, config=PipelineConfig(), files=files)
        assert result.applicable is True
        assert result.observed_calls, "nothing was observed; strace is not working"
        assert result.behavioral_flags == []

    def test_a_skill_that_lies_about_the_network_is_caught(self):
        """Declares FILE_READ and "never touches the network", then opens a socket."""
        skill, files = _fixture("liar")
        result = stage2.run_sandbox_check(skill.manifest, config=PipelineConfig(), files=files)
        assert result.applicable is True
        network = [f for f in result.behavioral_flags if f.syscall == "connect"]
        assert network, [f.description for f in result.behavioral_flags]
        assert network[0].severity is Severity.HIGH

    def test_a_skill_that_reaches_for_credentials_is_caught(self):
        skill, files = _fixture("liar")
        result = stage2.run_sandbox_check(skill.manifest, config=PipelineConfig(), files=files)
        secrets = [f for f in result.behavioral_flags if "id_rsa" in f.description]
        assert secrets, [f.description for f in result.behavioral_flags]

    def test_the_two_fixtures_differ_only_in_behaviour(self):
        """Both declare FILE_READ. What separates them is what they did, not what they said.

        That is the whole proposition of stage 2, so it is asserted directly rather than
        left implied by the two tests above.
        """
        honest, honest_files = _fixture("honest")
        liar, liar_files = _fixture("liar")
        explicit = lambda s: s.manifest.declared_capabilities(explicit_only=True)  # noqa: E731
        assert explicit(honest) == explicit(liar)

        cfg = PipelineConfig()
        clean = stage2.run_sandbox_check(honest.manifest, config=cfg, files=honest_files)
        dirty = stage2.run_sandbox_check(liar.manifest, config=cfg, files=liar_files)
        assert clean.behavioral_flags == []
        assert len(dirty.behavioral_flags) >= 2

    def test_the_network_is_actually_off(self):
        """The connect must fail at the kernel, not merely be recorded.

        A sandbox that observes exfiltration while letting it succeed is worse than none.
        """
        _, files = _fixture("liar")
        skill, _ = _fixture("liar")
        result = stage2.run_sandbox_check(skill.manifest, config=PipelineConfig(), files=files)
        raw = " ".join(str(c.args) for c in result.observed_calls)
        assert "ENETUNREACH" in raw or "ENETDOWN" in raw or "EHOSTUNREACH" in raw
