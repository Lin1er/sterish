# Sandbox image for stage 2 (STE-40).
#
# Runs a skill's declared entrypoint and records what it actually attempts, so the audit
# can compare observed behaviour against declared capabilities. Kept deliberately small:
# every extra tool in here is something a hostile skill could use.
#
# Build:  docker build -t sterish/sandbox:latest sandbox/
FROM python:3.12-alpine

# strace is the whole point — it is how "we observed" stops being a figure of speech.
# node and sh cover the runtimes MCP servers actually declare.
RUN apk add --no-cache strace nodejs

# The skill runs as a user with no privileges and no home worth reading.
RUN adduser -D -u 10001 -h /nonexistent -s /sbin/nologin runner

COPY runner.py /runner.py

# Decoys. A skill that reads these is exfiltrating credentials; it just happens to be
# reading ours, which contain nothing. Real paths, fake secrets, honest signal.
RUN mkdir -p /home/runner/.ssh /home/runner/.aws \
 && echo "not-a-real-key" > /home/runner/.ssh/id_rsa \
 && echo "not-real-credentials" > /home/runner/.aws/credentials \
 && chmod -R a+r /home/runner

USER runner
ENTRYPOINT ["python3", "/runner.py"]
