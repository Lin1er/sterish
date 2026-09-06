# Sterish verification API (STE-25).
#
# Two stages so the runtime image carries no build tooling. The API depends on the
# pipeline package by path (it reuses that module's Soroban writer for
# mint_license), so both projects are copied in before the sync.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /src

# Dependency manifests first: they change far less often than source, so an edit
# to a route does not invalidate the dependency layer.
COPY pipeline/pyproject.toml pipeline/uv.lock ./pipeline/
COPY api/pyproject.toml api/uv.lock ./api/
COPY pipeline/src ./pipeline/src
COPY api/src ./api/src

# Runtime dependency, not documentation: sterish_pipeline.specs locates the repo
# by looking for docs/specs/verdict.schema.json and loads the frozen content_hash
# reference from docs/specs/reference/. /use hashes the artifact through that
# module before serving it, so without this the paid path raises SpecsNotFound in
# production while every offline test still passes.
COPY docs/specs ./docs/specs

WORKDIR /src/api
RUN uv sync --frozen --no-dev


FROM python:3.12-slim-bookworm AS runtime

# Runs unprivileged: the service needs no root, and a container that cannot write
# outside its volume is one less thing to reason about after an RCE in a dependency.
RUN useradd --create-home --uid 10001 sterish

COPY --from=build --chown=sterish:sterish /src /src

ENV PATH="/src/api/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    STERISH_DB_PATH=/data/sterish_index.db

# Create the mount point owned by the runtime user. Docker seeds an empty named
# volume from the image, ownership included; without this the volume arrives
# owned by root and the unprivileged process dies at startup with
# "unable to open database file".
RUN mkdir -p /data && chown sterish:sterish /data

WORKDIR /src/api
USER sterish

# The index is a cache, but it lives on a volume so a restart does not re-walk the
# whole retained ledger range every time.
VOLUME ["/data"]
EXPOSE 8000

# Fails the container when the chain cannot be read — /health returns 503 in that
# case, which is what makes this check meaningful rather than a liveness tautology.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=8).status==200 else 1)"

CMD ["uvicorn", "sterish_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
