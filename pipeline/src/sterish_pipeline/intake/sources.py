"""Fetch skills from upstream catalogs into corpus snapshots.

The only network access in the pipeline lives here, and it runs from
`sterish-pipeline intake fetch` — never from an audit. Audits read snapshots.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

CATALOG_BASE = "https://skills.stellar.org"
LLMS_TXT = f"{CATALOG_BASE}/llms.txt"
SITEMAP = f"{CATALOG_BASE}/sitemap.xml"

_SKILL_URL = re.compile(r"https://skills\.stellar\.org/skills/([a-z0-9-]+)/([a-z0-9._-]+\.md)")
_SITEMAP_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")

USER_AGENT = "sterish-intake/0.1 (+https://github.com/Lin1er/sterish)"


@dataclass(frozen=True)
class FetchedDocument:
    """One document pulled from a catalog, with the headers that date it."""

    url: str
    category: str
    filename: str
    body: bytes
    etag: str
    last_modified: str
    fetched_at: str

    @property
    def slug(self) -> str:
        """`agentic-payments/x402.md` -> `agentic-payments.x402`."""
        stem = self.filename.rsplit(".", 1)[0]
        return f"{self.category}.{stem.lower()}"

    @property
    def skill_id(self) -> str:
        return f"org.stellar.skills.{self.slug}"

    @property
    def version(self) -> str:
        """`YYYY.MM.DD` from the upstream Last-Modified, else the fetch date.

        A date version is derivable by anyone re-fetching the same document, so
        two people snapshotting the catalog independently agree.
        """
        if self.last_modified:
            try:
                return parsedate_to_datetime(self.last_modified).strftime("%Y.%m.%d")
            except (TypeError, ValueError):
                pass
        return self.fetched_at[:10].replace("-", ".")


def discover_catalog_urls(client: httpx.Client) -> list[tuple[str, str, str]]:
    """Return `(url, category, filename)` for every markdown skill in the catalog.

    `llms.txt` lists entry points and their companion files; the sitemap lists
    the entry points. Both are read so a document missing from one is still
    found through the other.
    """
    urls: dict[str, tuple[str, str, str]] = {}

    for source in (LLMS_TXT, SITEMAP):
        try:
            response = client.get(source)
            response.raise_for_status()
        except httpx.HTTPError:
            continue
        text = response.text
        candidates = _SITEMAP_LOC.findall(text) if source.endswith(".xml") else [text]
        for candidate in candidates:
            for match in _SKILL_URL.finditer(candidate):
                url, category, filename = match.group(0), match.group(1), match.group(2)
                urls[url] = (url, category, filename)

    if not urls:
        raise RuntimeError(
            f"no skill documents discovered at {CATALOG_BASE}; the catalog layout may have changed"
        )
    return sorted(urls.values())


def fetch_document(client: httpx.Client, url: str, category: str, filename: str) -> FetchedDocument:
    response = client.get(url)
    response.raise_for_status()
    return FetchedDocument(
        url=url,
        category=category,
        filename=filename,
        body=response.content,
        etag=response.headers.get("etag", ""),
        last_modified=response.headers.get("last-modified", ""),
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def fetch_catalog(timeout: float = 30.0, limit: int | None = None) -> list[FetchedDocument]:
    """Fetch every markdown skill the Stellar catalog publishes."""
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        targets = discover_catalog_urls(client)
        if limit is not None:
            targets = targets[:limit]
        return [fetch_document(client, *target) for target in targets]
