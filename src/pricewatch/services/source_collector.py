from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

from pricewatch.config import Settings, get_settings
from pricewatch.services.good_search import GoodSearchClient, GoodSearchError
from pricewatch.utils.urls import normalize_site, site_from_url, site_search_query, urls_share_site


@dataclass
class SourceListing:
    url: str
    site: str
    title: str | None
    content: str
    source_type: str  # preferred | confirmed | other
    search_snippet: str | None = None


class SourceCollector:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.good_search = GoodSearchClient(self.settings)

    async def collect(
        self,
        *,
        name: str,
        search_query: str,
        preferred_site: str | None,
        product_url: str | None,
        also_search_other_sites: bool,
        confirmed_urls: list[str],
        max_other_results: int = 4,
    ) -> tuple[list[SourceListing], str | None]:
        listings: list[SourceListing] = []
        seen_urls: set[str] = set()
        reference_context: str | None = None

        async def add_listing(
            url: str,
            *,
            source_type: str,
            title: str | None = None,
            search_snippet: str | None = None,
        ) -> None:
            nonlocal reference_context
            if url in seen_urls:
                return
            seen_urls.add(url)
            try:
                content = await self.good_search.fetch_contents(url)
            except GoodSearchError:
                return
            site = site_from_url(url) or "unknown"
            listing = SourceListing(
                url=url,
                site=site,
                title=title,
                content=content,
                source_type=source_type,
                search_snippet=search_snippet,
            )
            listings.append(listing)
            if reference_context is None and source_type in {"preferred", "confirmed"}:
                reference_context = self._reference_text(listing)

        preferred = normalize_site(preferred_site)

        if product_url:
            await add_listing(product_url, source_type="preferred", title=name)

        if preferred and not (product_url and urls_share_site(product_url, preferred)):
            site_results = await self.good_search.search(
                site_search_query(preferred, search_query),
                limit=3,
            )
            for result in site_results:
                url = result.get("url")
                if not url or not urls_share_site(url, preferred):
                    continue
                await add_listing(
                    url,
                    source_type="preferred",
                    title=result.get("title"),
                    search_snippet=result.get("snippet"),
                )
                if len([l for l in listings if l.source_type == "preferred"]) >= 2:
                    break

        for url in confirmed_urls:
            await add_listing(url, source_type="confirmed", title=name)

        if also_search_other_sites:
            general_results = await self.good_search.search(search_query, limit=max_other_results + 2)
            for result in general_results:
                url = result.get("url")
                if not url or url in seen_urls:
                    continue
                if preferred and urls_share_site(url, preferred):
                    continue
                await add_listing(
                    url,
                    source_type="other",
                    title=result.get("title"),
                    search_snippet=result.get("snippet"),
                )
                if len([l for l in listings if l.source_type == "other"]) >= max_other_results:
                    break

        if reference_context is None and listings:
            reference_context = self._reference_text(listings[0])

        return listings, reference_context

    def _reference_text(self, listing: SourceListing) -> str:
        title = listing.title or "Unknown title"
        snippet = listing.search_snippet or ""
        return (
            f"Preferred/known listing\n"
            f"Site: {listing.site}\n"
            f"URL: {listing.url}\n"
            f"Title: {title}\n"
            f"Snippet: {snippet}\n\n"
            f"{listing.content[:8000]}"
        )
