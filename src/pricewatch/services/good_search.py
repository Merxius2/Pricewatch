from __future__ import annotations

import httpx

from pricewatch.config import Settings


class GoodSearchError(Exception):
    pass


class GoodSearchClient:
    """Client for Damn Good Search (search + page contents)."""

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.good_search_base_url.rstrip("/")
        self.api_key = settings.good_search_api_key

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise GoodSearchError(
                "Good Search API key is not configured. Set PRICEWATCH_GOOD_SEARCH_API_KEY."
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        payload = {"query": query, "limit": limit}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/search",
                headers=self._headers(),
                json=payload,
            )
            if response.status_code >= 400:
                raise GoodSearchError(f"Search failed ({response.status_code}): {response.text}")
            data = response.json()
            return data.get("results", data.get("items", []))

    async def fetch_contents(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                f"{self.base_url}/contents",
                headers=self._headers(),
                json={"url": url},
            )
            if response.status_code >= 400:
                raise GoodSearchError(f"Contents failed ({response.status_code}): {response.text}")
            data = response.json()
            return data.get("text") or data.get("markdown") or data.get("content") or ""

    async def gather_product_context(
        self,
        *,
        search_query: str,
        product_url: str | None = None,
        max_results: int = 3,
    ) -> tuple[str, str | None]:
        if product_url:
            text = await self.fetch_contents(product_url)
            return text, product_url

        results = await self.search(search_query, limit=max_results)
        if not results:
            raise GoodSearchError(f"No search results for query: {search_query}")

        snippets: list[str] = []
        primary_url: str | None = None
        for index, result in enumerate(results):
            title = result.get("title") or result.get("name") or "Untitled"
            url = result.get("url") or result.get("link")
            snippet = result.get("snippet") or result.get("description") or ""
            snippets.append(f"Result {index + 1}: {title}\nURL: {url}\nSnippet: {snippet}")
            if index == 0 and url:
                primary_url = url

        combined = "\n\n".join(snippets)

        if primary_url:
            try:
                page_text = await self.fetch_contents(primary_url)
                if page_text:
                    combined += f"\n\n--- Full page content from {primary_url} ---\n{page_text[:12000]}"
            except GoodSearchError:
                pass

        return combined, primary_url
