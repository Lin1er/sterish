"""The API behind Cloudflare -> cloudflared -> Caddy sees the client, not the proxy (STE-53).

Found on production: every public request reached the API from Caddy's container
address, so the per-IP rate limit was one bucket shared by every visitor, and URLs built
from the request (the x402 `resource.url`, the STE-48 `challenge_url`) said `http://`.
"""

import base64
import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from sterish_api.ratelimit import RateLimitMiddleware

PROXY = "172.18.0.3"          # Caddy on the compose network
CLIENT_A = "203.0.113.10"     # documentation ranges: two real visitors
CLIENT_B = "198.51.100.20"


def _app(limit, trusted, peer):
    """The production middleware order, with the TCP peer address under test control."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit_per_minute=limit)
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted)

    @app.get("/who")
    def who(request: Request):
        return {"client": request.client.host, "url": str(request.url)}

    return TestClient(app, client=(peer, 50000))


def fwd(client, proto="https"):
    return {"X-Forwarded-For": client, "X-Forwarded-Proto": proto}


def test_two_visitors_behind_the_same_proxy_get_their_own_buckets():
    c = _app(2, "172.16.0.0/12", PROXY)
    assert [c.get("/who", headers=fwd(CLIENT_A)).status_code for _ in range(2)] == [200, 200]
    assert c.get("/who", headers=fwd(CLIENT_A)).status_code == 429
    # Before STE-53 this was 429 too: B was counted in A's bucket, because both were PROXY.
    assert c.get("/who", headers=fwd(CLIENT_B)).status_code == 200


def test_the_route_sees_the_real_client_and_scheme():
    body = _app(0, "172.16.0.0/12", PROXY).get("/who", headers=fwd(CLIENT_A)).json()
    assert body["client"] == CLIENT_A
    assert body["url"].startswith("https://")


def test_an_untrusted_peer_cannot_choose_its_own_address():
    """A client talking to the API directly must not dodge the limit with a fake header."""
    c = _app(1, "172.16.0.0/12", CLIENT_A)
    assert c.get("/who", headers=fwd("1.1.1.1")).status_code == 200
    r = c.get("/who", headers=fwd("8.8.8.8"))
    assert r.status_code == 429  # still keyed on CLIENT_A, the real peer


def test_a_spoofed_left_entry_is_ignored_when_the_chain_is_trusted():
    """X-Forwarded-For: <what the client typed>, <what Cloudflare saw>, <cloudflared>.
    The rightmost untrusted entry is the client; anything to its left is theirs to invent."""
    c = _app(0, "172.16.0.0/12", PROXY)
    body = c.get("/who", headers=fwd(f"6.6.6.6, {CLIENT_A}, 172.18.0.2")).json()
    assert body["client"] == CLIENT_A


def test_the_app_is_wired_with_the_proxy_middleware_outermost():
    from sterish_api.main import app

    names = [m.cls.__name__ for m in app.user_middleware]
    assert names[0] == "ProxyHeadersMiddleware"  # first in this list = outermost
    assert names.index("ProxyHeadersMiddleware") < names.index("RateLimitMiddleware")


def test_the_default_trust_covers_the_compose_network_and_not_the_internet():
    from uvicorn.middleware.proxy_headers import _TrustedHosts

    from sterish_api.config import settings

    trusted = _TrustedHosts(settings.trusted_proxies)
    assert PROXY in trusted and "172.18.0.2" in trusted and "127.0.0.1" in trusted
    assert CLIENT_A not in trusted and "8.8.8.8" not in trusted


@pytest.fixture
def behind_proxy(monkeypatch, client):
    """The real app, reached as Caddy forwarding an https request."""
    return TestClient(client.app, client=(PROXY, 50000))


def test_the_x402_challenge_advertises_https_behind_the_proxy(behind_proxy, monkeypatch, tmp_path):
    from sterish_pipeline.content_hash import content_hash

    from sterish_api import chain
    from sterish_api.config import settings

    root = tmp_path / "artifacts" / "com.acme.pdf-suite" / "1.0.0"
    root.mkdir(parents=True)
    (root / "manifest.json").write_bytes(b"{}\n")
    digest = content_hash({"manifest.json": b"{}\n"})
    record = {"skill_id": "com.acme.pdf-suite", "version": "1.0.0", "content_hash": digest,
              "verdict": "SAFE", "is_verified": True}
    monkeypatch.setattr(chain, "get_version", lambda s, v: record)
    previous = settings.skills_dir
    object.__setattr__(settings, "skills_dir", str(tmp_path / "artifacts"))
    try:
        r = behind_proxy.get("/use/com.acme.pdf-suite/1.0.0",
                             headers={**fwd(CLIENT_A), "Host": "api-sterish.jameshub.fun"})
    finally:
        object.__setattr__(settings, "skills_dir", previous)
    assert r.status_code == 402
    challenge = json.loads(base64.b64decode(r.headers["PAYMENT-REQUIRED"]))
    assert challenge["resource"]["url"] == (
        "https://api-sterish.jameshub.fun/use/com.acme.pdf-suite/1.0.0"
    )


def test_the_ownership_challenge_url_is_https_behind_the_proxy(behind_proxy, monkeypatch, tmp_path):
    from sterish_pipeline.content_hash import content_hash

    from sterish_api import chain
    from sterish_api.config import settings

    holder = "GD73M4F7RN74KBLFGJP4WKBMCBJWBOA4SFNOP5HG4NBCDQUQCC2ARSZU"
    root = tmp_path / "artifacts" / "com.acme.pdf-suite" / "1.0.0"
    root.mkdir(parents=True)
    (root / "manifest.json").write_bytes(b"{}\n")
    digest = content_hash({"manifest.json": b"{}\n"})
    monkeypatch.setattr(chain, "get_version", lambda s, v: {
        "skill_id": s, "version": v, "content_hash": digest, "verdict": "SAFE",
        "is_verified": True})
    monkeypatch.setattr(chain, "has_license", lambda a, s, v: True)
    previous = settings.skills_dir
    object.__setattr__(settings, "skills_dir", str(tmp_path / "artifacts"))
    try:
        r = behind_proxy.get("/use/com.acme.pdf-suite/1.0.0", headers={
            **fwd(CLIENT_A), "Host": "api-sterish.jameshub.fun", "X-AGENT-ADDRESS": holder})
    finally:
        object.__setattr__(settings, "skills_dir", previous)
    assert r.status_code == 401
    assert r.json()["challenge_url"].startswith(
        "https://api-sterish.jameshub.fun/use/com.acme.pdf-suite/1.0.0/challenge"
    )
