# Sandbox — stage 2

Runs a skill's declared entrypoint and records what it actually attempts, so the audit can
compare observed behaviour against declared capabilities.

```bash
docker build -t sterish/sandbox:latest pipeline/sandbox/
```

Without the image, stage 2 reports `applicable: false` with a reason. It does **not** report
a clean result — nothing ran, so nothing is known.

## What it takes away

| | |
|---|---|
| `--network none` | A `connect()` is still traced. The attempt is the finding; the packet never leaves. |
| `--read-only` | Root filesystem is immutable; only `/tmp` is writable, and it is a 64M tmpfs. |
| `--cap-drop ALL` | Plus `--security-opt no-new-privileges`. |
| `--cap-add SYS_PTRACE` | The one exception, and only because `strace` cannot work without it. |
| `--pids-limit 128`, `--memory 256m`, `--cpus 0.5` | A fork bomb hits a wall rather than the host. |
| bind mount, `readonly` | The skill's own bytes at `/skill`. Nothing else from the host is visible. |
| uid 10001, `/sbin/nologin` | No privileges, no home worth reading. |

## The decoys

The image ships fake credentials at `~/.ssh/id_rsa` and `~/.aws/credentials`. Real paths,
worthless contents. A skill that reads them is reaching for keys, and now says so out loud.

## Why strace and not stderr

Because "we observed" should not be a figure of speech. `strace` records the syscalls the
process actually issued: a `connect` to `AF_INET` is an attempt to reach the network whether
or not the kernel allowed it, and an `openat` of a private key is an attempt to read one
whether or not a real key was there. Inferring the same from stderr would be guessing.

The trace is read from stderr rather than `-o <file>`: writing to a file inside the container
produced an empty one while stderr carried the syscalls, and a file is a moving part this does
not need. The child's own stderr mixes in, which is harmless — only syscall-shaped lines parse.

## What it cannot tell you

An Agent Skill published as markdown executes nothing, so there is nothing here to observe.
Its risk is what it *instructs the agent* to do, which stage 1 reads. For those skills stage 2
answers `applicable: false`, and that is the honest answer rather than a gap.
