from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote_plus

import httpx

from pricewatch.config import Settings


class GoodSearchError(Exception):
    pass


DEFAULT_MCP_CANDIDATES = (
    "http://127.0.0.1:8765/mcp",
    "http://127.0.0.1:8420/mcp",
)

_resolved_mcp_url: str | None = None
_resolved_health: dict[str, Any] | None = None


def mcp_url_candidates(settings: Settings) -> list[str]:
    configured = settings.good_search_mcp_url.strip().rstrip("/")
    if configured and not settings.good_search_auto_discover:
        return [configured]

    if settings.good_search_mcp_url_candidates.strip():
        custom = [
            url.strip().rstrip("/")
            for url in settings.good_search_mcp_url_candidates.split(",")
            if url.strip()
        ]
        ordered = ([configured] if configured else []) + custom
    else:
        ordered = ([configured] if configured else []) + list(DEFAULT_MCP_CANDIDATES)

    seen: set[str] = set()
    unique: list[str] = []
    for url in ordered:
        if url and url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


class GoodSearchClient:
    """Client for the Good-search MCP service (stealth browser scrape + browse tools)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mcp_url = (_resolved_mcp_url or settings.good_search_mcp_url).strip().rstrip("/")
        self.scrape_tool = settings.good_search_scrape_tool or "scrape"
        self.timeout = settings.good_search_timeout_seconds
        self._session_id: str | None = None
        self._request_id = 0

    @classmethod
    def cached_health(cls) -> dict[str, Any] | None:
        return _resolved_health

    async def ensure_connected(self) -> dict[str, Any]:
        global _resolved_mcp_url, _resolved_health

        if _resolved_health is not None:
            return _resolved_health

        if not mcp_url_candidates(self.settings):
            raise GoodSearchError(
                "Good-search MCP URL is not configured. Set PRICEWATCH_GOOD_SEARCH_MCP_URL in .env"
            )

        last_error: Exception | None = None
        for candidate in mcp_url_candidates(self.settings):
            probe = GoodSearchClient(self.settings)
            probe.mcp_url = candidate
            try:
                health = await probe.health_check()
                self.mcp_url = candidate
                _resolved_mcp_url = candidate
                _resolved_health = health
                return health
            except GoodSearchError as exc:
                last_error = exc

        raise GoodSearchError(
            "Good-search MCP is not reachable. "
            f"Tried: {', '.join(mcp_url_candidates(self.settings))}. "
            f"Last error: {last_error}"
        ) from last_error

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        await self.ensure_connected()
        search_url = self.settings.good_search_search_url_template.format(
            query=quote_plus(query)
        )
        payload = await self._scrape(search_url)
        results = self._parse_search_page(payload)
        return results[:limit]

    async def fetch_contents(self, url: str) -> str:
        await self.ensure_connected()
        payload = await self._scrape(url)
        if payload.get("blocked"):
            raise GoodSearchError(
                f"Good-search could not access {url} (blocked by anti-bot protection)"
            )
        content = payload.get("content") or ""
        if not content.strip():
            raise GoodSearchError(f"No content returned for {url}")
        return content

    async def health_check(self) -> dict[str, Any]:
        if not self.mcp_url:
            raise GoodSearchError("Good-search MCP URL is not configured")

        tools = await self._list_tools()
        tool_names = [tool.get("name") for tool in tools if tool.get("name")]
        if self.scrape_tool not in tool_names:
            raise GoodSearchError(
                f"Expected scrape tool '{self.scrape_tool}' not found. Available: {', '.join(tool_names)}"
            )

        return {
            "reachable": True,
            "mcp_url": self._safe_mcp_url(),
            "tools": tool_names,
            "scrape_tool": self.scrape_tool,
        }

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

    async def _scrape(self, url: str) -> dict[str, Any]:
        result = await self._call_tool(
            self.scrape_tool,
            {
                "url": url,
                "format": "text",
                "maxChars": self.settings.good_search_max_chars,
                "maxAgeSec": 0,
                "maxTier": self.settings.good_search_max_tier,
            },
        )
        payload = self._parse_scrape_payload(result)
        if payload.get("blocked"):
            raise GoodSearchError(
                f"Good-search was blocked loading {url}. "
                "The site refused the browser — price could not be verified."
            )
        return payload

    def _parse_scrape_payload(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict) and "blocked" in payload and isinstance(payload.get("content"), str):
            return payload

        text = self._extract_text(payload)
        if not text:
            return {}

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"content": text}

        if isinstance(parsed, dict):
            return parsed
        return {"content": text}

    def _parse_search_page(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_content = payload.get("content") or ""
        if isinstance(raw_content, list):
            content = "\n".join(str(part) for part in raw_content)
        else:
            content = str(raw_content)
        if not content.strip():
            return []

        results: list[dict[str, Any]] = []
        url_pattern = re.compile(r"(?:https?://|www\.)[^\s)>\"']+")

        for match in url_pattern.finditer(content):
            raw_url = match.group(0).rstrip(".,;")
            url = raw_url if raw_url.startswith("http") else f"https://{raw_url}"
            prefix = content[max(0, match.start() - 140) : match.start()].strip()
            title = prefix.split("\n")[-1].strip(" -:\t") or "Result"
            if len(title) < 3 or "duckduckgo.com" in url:
                continue
            snippet = content[match.start() : min(len(content), match.end() + 120)].strip()
            results.append({"title": title, "url": url, "snippet": snippet})

        deduped: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for result in results:
            if result["url"] in seen_urls:
                continue
            seen_urls.add(result["url"])
            deduped.append(result)
        return deduped

    def _safe_mcp_url(self) -> str:
        """Hide the Tailscale secret path segment in logs and API responses."""
        if "/mcp/" in self.mcp_url:
            base, _, _secret = self.mcp_url.partition("/mcp/")
            return f"{base}/mcp/<secret>"
        return self.mcp_url

    async def _list_tools(self) -> list[dict[str, Any]]:
        payload = await self._rpc("tools/list", {})
        return payload.get("tools", [])

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        payload = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        if payload.get("isError"):
            message = self._extract_text(payload) or "Good-search tool call failed"
            raise GoodSearchError(message)
        return payload

    async def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._request_id += 1
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        body = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                if method == "tools/list" and self._session_id is None:
                    await self._initialize(client, headers)

                response = await client.post(self.mcp_url, headers=headers, json=body)
            except httpx.HTTPError as exc:
                raise GoodSearchError(f"Good-search MCP unreachable at {self._safe_mcp_url()}: {exc}") from exc

            if response.status_code >= 400:
                raise GoodSearchError(
                    f"Good-search MCP request failed ({response.status_code}): {response.text}"
                )

            session_id = response.headers.get("Mcp-Session-Id")
            if session_id:
                self._session_id = session_id

            data = self._parse_response_payload(response)
            if "error" in data:
                error = data["error"]
                message = error.get("message", str(error))
                raise GoodSearchError(f"Good-search MCP error: {message}")
            return data.get("result", {})

    async def _initialize(self, client: httpx.AsyncClient, headers: dict[str, str]) -> None:
        self._request_id += 1
        init_body = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pricewatch", "version": "0.1.0"},
            },
        }
        try:
            response = await client.post(self.mcp_url, headers=headers, json=init_body)
        except httpx.HTTPError as exc:
            raise GoodSearchError(f"Good-search MCP unreachable at {self._safe_mcp_url()}: {exc}") from exc

        if response.status_code >= 400:
            raise GoodSearchError(
                f"Good-search MCP initialize failed ({response.status_code}): {response.text}"
            )

        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            self._session_id = session_id

        self._request_id += 1
        notify_headers = dict(headers)
        if self._session_id:
            notify_headers["Mcp-Session-Id"] = self._session_id
        await client.post(
            self.mcp_url,
            headers=notify_headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )

    def _parse_response_payload(self, response: httpx.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()

        text = response.text.strip()
        if not text:
            raise GoodSearchError("Good-search MCP returned an empty response")

        if text.startswith("{"):
            return json.loads(text)

        for line in text.splitlines():
            if line.startswith("data:"):
                payload = line.removeprefix("data:").strip()
                if payload:
                    return json.loads(payload)

        raise GoodSearchError(f"Unexpected Good-search MCP response format: {text[:300]}")

    def _extract_text(self, payload: Any) -> str:
        if payload is None:
            return ""

        if isinstance(payload, str):
            return payload

        if isinstance(payload, dict):
            for key in ("text", "markdown", "content", "body"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value

            structured = payload.get("structuredContent")
            if structured is not None:
                return json.dumps(structured, indent=2)

            content = payload.get("content")
            if isinstance(content, list):
                parts: list[str] = []
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                if parts:
                    return "\n".join(parts)

            return json.dumps(payload, indent=2)

        return str(payload)
