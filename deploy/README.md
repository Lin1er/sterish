# Deploying the Sterish backend (STE-25)

API + indexer + reverse proxy with automatic TLS, as a Docker Compose stack.

## What runs

| Service | Purpose |
|---|---|
| `api` | FastAPI: `/check`, `/skills`, `/feed`, `/use` (x402), `/health`. The indexer runs inside this process as an asyncio task. |
| `caddy` | TLS termination and reverse proxy. Certificates are obtained and renewed from Let's Encrypt automatically — no cron job, no renewal step. |

**No separate indexer service and no database server.** The indexer is a task in the
API's lifespan, so splitting it out would mean two processes sharing one SQLite
file for no gain. The cache stays SQLite because it *is* a cache: every verdict is
read from the chain per request, and the documented recovery is "delete the file
and restart". A Postgres service would add a failure mode without adding an answer
the chain does not already hold.

## Deploying

```bash
git clone https://github.com/Lin1er/sterish && cd sterish/deploy
cp .env.example .env      # fill it in; see below
chmod 600 .env
mkdir -p artifacts        # <skill_id>/<version>/ trees served by /use

docker compose --env-file .env up -d --build
bash verify.sh https://your.domain
```

`restart: unless-stopped` on both services means a crash or a host reboot brings
them back without intervention.

### Required settings

| | |
|---|---|
| `REGISTRY_CONTRACT_ID`, `TOKENS_CONTRACT_ID` | from `docs/deployments.md` |
| `STERISH_DOMAIN` | the public hostname Caddy serves and gets a certificate for. Use `:80` for a local run — Caddy then serves plain HTTP and skips ACME entirely. |
| `X402_PAY_TO` | classic `G…` account that receives USDC. **Not** the SAC address, and it needs a USDC trustline. |
| `MINTER_SECRET` | signs `mint_license`; must hold the tokens contract's minter role |
| `OZ_API_KEY` | facilitator key. Testnet needs no authentication: `curl https://channels.openzeppelin.com/testnet/gen` |

DNS for `STERISH_DOMAIN` must resolve to the host before the first start, and
ports 80 and 443 must be reachable — ACME validates over both.

### Running reads only

Leave `OZ_API_KEY` empty. `/check`, `/skills` and `/feed` work normally and
existing licence holders are still served; only new purchases are unavailable, and
`/health` reports `facilitator_reachable: false` while `rpc_reachable` stays true.
That separation is deliberate: an operator can tell "Sterish is down" from "nobody
can buy right now".

## Verifying

`verify.sh` checks that the deployment *answers*, not that a container is running —
a process can be up while unable to read the chain. `/health` returns 503 in that
case, which is what makes the check meaningful.

It asserts the error paths too, because those are the ones that rot quietly: an
unknown hash is 404, a malformed one is 400, an unpaid `/use` is 402 **with a
payment challenge attached**, and a DANGEROUS version is 403 — never offered for
sale, not even at a price.

## Operating

```bash
docker compose logs -f api          # application log
docker compose ps                   # health status
docker compose up -d --build        # deploy a new revision
```

**Rebuilding the index.** It is a cache, so this is safe at any time:

```bash
docker compose down
docker volume rm deploy_index
docker compose up -d
```

The next poll refills it from the chain. Verdicts are unaffected while it is
empty — only the transaction links in `evidence` and the `/feed` list are, and
they come back as `null` rather than wrong.

## Two things that will bite otherwise

**The build context is the repo root.** Without `.dockerignore` every build ships
`contracts/target` (3.3 GB) and two virtualenvs to the daemon. With it the context
is ~340 kB. If a build suddenly takes minutes, check that file first.

**`docs/specs/` is a runtime dependency, not documentation.**
`sterish_pipeline.specs` locates the repo by looking for
`docs/specs/verdict.schema.json` and loads the frozen `content_hash` reference from
`docs/specs/reference/`. `/use` hashes the artifact through that module before
serving it. Excluding `docs/` from the image leaves the paid path raising
`SpecsNotFound` in production while every offline test still passes.
