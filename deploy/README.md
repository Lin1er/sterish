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
mkdir -p artifacts        # <skill_id>/<version>/ trees served by /use — NOT in git;
                          # fill it with "What is for sale" below

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

**Never remove `deploy_payments`.** It is not the cache. It records every x402
settlement that is still owed a licence (STE-42): `/use` settles the payment and
then mints, and if the mint fails in between, this is the only record that the
buyer paid. Their next request finishes the mint from it without charging again.
Delete it and those buyers have paid for nothing. To see anything still owed:

```bash
docker compose exec api python -c "import sqlite3; c=sqlite3.connect('/payments/sterish_payments.db'); \
print(c.execute('select payer, skill_id, version, settle_tx, last_error from payments where minted_at is null').fetchall())"
```

A row that stays owed with `NotSafeVerdict` means the version was re-audited away
from SAFE between settlement and mint. That buyer is owed a refund, which is a
manual USDC transfer back to `payer`.

## What is for sale

`/use` prices a version only when its artifact is on disk **and** hashes to the
on-chain `content_hash` (STE-42). Everything else answers `404 ARTIFACT_NOT_FOUND`
with no payment challenge, so nobody can pay for bytes the API cannot hand over.

`deploy/artifacts/` is operator-supplied and gitignored (STE-25), so a fresh clone
sells nothing until it is filled. Fill it from the corpus, never by hand — on the
host, from `deploy/`, with the same image and `.env` the API uses:

```bash
docker compose --env-file .env --profile tools run --rm publish-artifacts
```

Run it after every redeploy that brings a new corpus or a new seed run. It writes a
skill only when the bytes, the corpus index and the registry agree on the hash and
the on-chain verdict is SAFE, and it is idempotent: an artifact that already
matches is left alone. Directories are written `0755` and files `0644`, so the API's
unprivileged user can read what a root-run publish wrote.

The same command from a checkout, without Docker:

```bash
cd pipeline && set -a && . ../.env && set +a
uv run sterish intake publish-artifacts --corpus corpus --out ../deploy/artifacts
```

Then check the result from outside: `verify.sh` fails if any SAFE row is priced
without being deliverable.

## Publishing on a public hostname

Two paths are wired, and they can run together:

| | |
|---|---|
| **Cloudflare Tunnel** | `https://api-sterish.jameshub.fun` — `docker compose --profile tunnel up -d` |
| **Tailscale** | `https://pve02.tail4d50d6.ts.net` — `tailscale serve`/`funnel` on the host |

Both terminate at Caddy, so request handling, health checks and logging stay
defined in one place rather than drifting apart depending on how a client
arrived.

The tunnel is locally managed: `deploy/cloudflared-config.yml` decides the
routing, not the Cloudflare dashboard. Creating one needs an origin certificate
(`cloudflared tunnel login`), then:

```bash
cloudflared tunnel create sterish-api
cloudflared tunnel route dns sterish-api api-sterish.jameshub.fun
# copy the generated credentials JSON to deploy/secrets/, then:
chown 65532:65532 deploy/secrets/cloudflared-credentials.json
```

**That chown is not optional.** The official cloudflared image runs as nonroot
(uid 65532); a root-owned 0600 file yields "permission denied" and a container
that restarts forever while every other service looks healthy.

**One level of subdomain.** Cloudflare's Universal SSL covers `jameshub.fun` and
`*.jameshub.fun` — a single level. `api.sterish.jameshub.fun` would need a
wildcard that is not covered, so the name is `api-sterish.jameshub.fun`.

## Client address and scheme behind the proxies (STE-53)

Requests arrive as **Cloudflare → cloudflared → Caddy → API**. Two settings make the API see the
visitor rather than the last proxy, and both are needed:

- `Caddyfile` sets `trusted_proxies static private_ranges`, so Caddy keeps the `X-Forwarded-For`
  and `X-Forwarded-Proto` that cloudflared (or `tailscale serve`) sends instead of overwriting them
  with its own view.
- The API applies those headers only when its direct peer is in `STERISH_TRUSTED_PROXIES`
  (private ranges by default) — uvicorn's own handling is off (`--no-proxy-headers`), so there is
  one rule in one place.

Without the first, every public request reaches the API from Caddy's container address: the
per-IP rate limit becomes a single bucket for the whole internet, and the x402 challenge advertises
`http://`. Measured on 17 Sep 2026 with a real Caddy in front of the API: with the old Caddyfile a
second visitor got `429` because of the first visitor's traffic and `resource.url` was `http://`;
with the new one, `200` and `https://`.

Trust is limited to private ranges, so it also covers anything on the LAN that can reach the
published port 80 directly. That is acceptable on the homelab network; tighten
`STERISH_TRUSTED_PROXIES` to the compose subnet if the host moves somewhere shared.

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
