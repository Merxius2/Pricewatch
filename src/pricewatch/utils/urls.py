from __future__ import annotations

from urllib.parse import urlparse


def normalize_site(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    if not value:
        return None
    if "://" in value:
        value = urlparse(value).netloc or value
    return value.removeprefix("www.")


def site_from_url(url: str | None) -> str | None:
    if not url:
        return None
    return normalize_site(url)


def site_search_query(site: str, query: str) -> str:
    site = normalize_site(site) or site
    return f"site:{site} {query}"


def urls_share_site(a: str | None, b: str | None) -> bool:
    left = site_from_url(a) or normalize_site(a)
    right = site_from_url(b) or normalize_site(b)
    return bool(left and right and left == right)
