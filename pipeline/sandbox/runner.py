"""Run one skill's entrypoint under strace and report what it attempted (STE-40).

Runs *inside* the sandbox container. Reads a job on stdin, writes one JSON object on
stdout, and never raises: a runner that crashes tells the auditor nothing, and "nothing"
is the one answer stage 2 must not silently produce.

Job (stdin):
    {"command": "node", "args": ["./server.js"], "env": {...}, "timeout": 20}

Result (stdout):
    {"ran": bool, "detail": str, "exit_code": int|null, "timed_out": bool,
     "calls": [{"syscall": str, "args": {...}, "ts": float}],
     "violations": [{"syscall": str, "severity": str, "description": str,
                     "capability": str}],
     "escaped": bool}

What "observed" means here, stated plainly: strace records the syscalls the process
actually issued. A `connect` under `--network none` still appears — the attempt is the
finding, and whether the kernel refused it is not the skill's choice. That is the whole
reason this is worth more than reading stderr and guessing.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time

SKILL_DIR = "/skill"

# Traced deliberately narrowly. Every extra syscall is more parsing to get wrong, and
# these four already separate "read a config file" from "phone home with your keys".
TRACED = "connect,openat,open,execve,socket"

#: Paths whose mere opening is the finding. The container ships decoys at these paths so
#: a skill reaching for credentials finds something and reveals itself.
CREDENTIAL_PATTERNS = (
    (re.compile(r"/\.ssh/"), "SSH key material"),
    (re.compile(r"/\.aws/"), "AWS credentials"),
    (re.compile(r"/\.env\b"), "environment file"),
    (re.compile(r"id_rsa|id_ed25519"), "private key"),
    (re.compile(r"/proc/self/environ"), "own environment block"),
)

_LINE = re.compile(r"^(?:\[pid\s+\d+\]\s*)?(\w+)\((.*)$")
_PATH = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _result(**kwargs) -> dict:
    base = {
        "ran": False,
        "detail": "",
        "exit_code": None,
        "timed_out": False,
        "calls": [],
        "violations": [],
        "escaped": False,
    }
    base.update(kwargs)
    return base


def parse_trace(text: str) -> tuple[list[dict], list[dict]]:
    """Turn strace output into observed calls plus the subset that are findings."""
    calls: list[dict] = []
    violations: list[dict] = []
    seen_exec = 0

    for raw in text.splitlines():
        match = _LINE.match(raw.strip())
        if not match:
            continue
        name, rest = match.group(1), match.group(2)

        if name in ("openat", "open"):
            path_match = _PATH.search(rest)
            if not path_match:
                continue
            path = path_match.group(1)
            calls.append({"syscall": name, "args": {"path": path}, "ts": 0.0})
            for pattern, label in CREDENTIAL_PATTERNS:
                if pattern.search(path):
                    violations.append({
                        "syscall": name,
                        "severity": "HIGH",
                        "description": f"Opened {label} at {path}.",
                        "capability": "SECRET_READ",
                    })
                    break

        elif name == "connect":
            calls.append({"syscall": name, "args": {"raw": rest[:200]}, "ts": 0.0})
            # A unix-socket connect is ordinary plumbing; an inet one is reaching out.
            if "AF_INET" in rest or "AF_INET6" in rest:
                violations.append({
                    "syscall": name,
                    "severity": "HIGH",
                    "description": f"Attempted an outbound network connection: {rest[:120]}",
                    "capability": "NETWORK_OUTBOUND",
                })

        elif name == "socket":
            if "AF_INET" in rest or "AF_INET6" in rest:
                calls.append({"syscall": name, "args": {"raw": rest[:200]}, "ts": 0.0})

        elif name == "execve":
            seen_exec += 1
            path_match = _PATH.search(rest)
            path = path_match.group(1) if path_match else "?"
            calls.append({"syscall": name, "args": {"path": path}, "ts": 0.0})
            # The first execve is the entrypoint itself. Later ones are the skill
            # starting something the manifest never mentioned.
            if seen_exec > 1:
                violations.append({
                    "syscall": "execve",
                    "severity": "MEDIUM",
                    "description": f"Spawned an additional process: {path}",
                    "capability": "PROCESS_SPAWN",
                })

    return calls, violations


def main() -> None:
    try:
        job = json.load(sys.stdin)
    except Exception as exc:  # noqa: BLE001 - a bad job must still produce a result
        print(json.dumps(_result(detail=f"could not read job: {exc}")))
        return

    command = (job.get("command") or "").strip()
    if not command:
        print(json.dumps(_result(detail="no entrypoint; nothing to execute")))
        return

    args = [str(a) for a in (job.get("args") or [])]
    timeout = int(job.get("timeout") or 20)

    # The skill's own env, plus a HOME that points at the decoys. Nothing inherited:
    # whatever is in this container's environment is ours, not the skill's business.
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/home/runner",
        **{str(k): str(v) for k, v in (job.get("env") or {}).items()},
    }

    # The trace goes to stderr rather than `-o <file>`: writing to a file inside the
    # container produced an empty one while stderr carried the syscalls, and a file is a
    # moving part this does not need. The child's own stderr mixes in, which is harmless —
    # the parser only matches syscall-shaped lines.
    argv = [
        "strace", "-f", "-qq", "-s", "200",
        "-e", f"trace={TRACED}",
        command, *args,
    ]

    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv, cwd=SKILL_DIR, env=env, timeout=timeout,
            capture_output=True, text=True,
        )
        exit_code, timed_out = proc.returncode, False
        stderr = proc.stderr
        trace = proc.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code, timed_out, stderr = None, True, ""
        # Even a run that had to be killed produced observations up to that point, and
        # those are exactly the observations most worth keeping.
        trace = (exc.stderr or b"").decode("utf-8", "replace") if exc.stderr else ""
    except FileNotFoundError as exc:
        print(json.dumps(_result(detail=f"entrypoint not runnable: {exc}")))
        return
    except Exception as exc:  # noqa: BLE001
        print(json.dumps(_result(detail=f"sandbox run failed: {exc}")))
        return

    elapsed = time.monotonic() - started

    calls, violations = parse_trace(trace)

    if timed_out:
        violations.append({
            "syscall": "timeout",
            "severity": "HIGH",
            "description": f"Did not terminate within {timeout}s.",
            "capability": "",
        })

    detail = f"ran {command} for {elapsed:.1f}s"
    if timed_out:
        detail += " (timed out)"
    elif exit_code:
        # A non-zero exit is not a finding by itself — a server told to run without its
        # files will exit non-zero, and that says nothing about its intent.
        detail += f" (exit {exit_code}: {stderr.strip()[:160]})"

    print(json.dumps(_result(
        ran=True, detail=detail, exit_code=exit_code, timed_out=timed_out,
        calls=calls[:200], violations=violations, escaped=False,
    )))


if __name__ == "__main__":
    main()
