from __future__ import annotations

import json
import re
from typing import Any

import httpx

from pricewatch.config import Settings


class GoodSearchError(Exception):
    pass


SEARCH_TOOL_HINTS = ("search", "google_search", "web_search", "query")
FETCH_TOOL_HINTS = ("fetch", "read", "contents", "get_page", "webfetch", "web_fetch", "parse")


class GoodSearchClient:
    """Client for the local Good-search MCP service (stealth browser search + parsing)."""

    def __init__(self, settings: Settings) -> None:
        self.mcp_url = settings.good_search_mcp_url.rstrip("/")
        self.search_tool = settings.good_search_search_tool
        self.fetch_tool = settings.good_search_fetch_tool
        self.timeout = settings.good_search_timeout_seconds
        self._session_id: str | None = None
        self._request_id = 0
        self._discovered_tools: dict[str, str] | None = None

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        tool_name = await self._resolve_tool("search", self.search_tool, SEARCH_TOOL_HINTS)
        result = await self._call_tool(
            tool_name,
            {
                "query": query,
                "limit": limit,
                "count": limit,
            },
        )
        return self._parse_search_results(result)

    async def fetch_contents(self, url: str) -> str:
        tool_name = await self._resolve_tool("fetch", self.fetch_tool, FETCH_TOOL_HINTS)
        result = await self._call_tool(tool_name, {"url": url})
        return self._extract_text(result)

    async def health_check(self) -> dict[str, Any]:
        tools = await self._list_tools()
        search_tool = await self._resolve_tool("search", self.search_tool, SEARCH_TOOL_HINTS)
        fetch_tool = await self._resolve_tool("fetch", self.fetch_tool, FETCH_TOOL_HINTS)
        return {
            "reachable": True,
            "mcp_url": self.mcp_url,
            "tools": [tool.get("name") for tool in tools],
            "search_tool": search_tool,
            "fetch_tool": fetch_tool,
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

    async def _resolve_tool(
        self,
        kind: str,
        configured: str,
        hints: tuple[str, ...],
    ) -> str:
        if configured:
            return configured

        discovered = await self._discover_tools()
        if kind in discovered:
            return discovered[kind]

        available = [tool.get("name", "") for tool in await self._list_tools()]
        raise GoodSearchError(
            f"Could not find a Good-search {kind} tool. "
            f"Available tools: {', '.join(available) or 'none'}. "
            f"Set PRICEWATCH_GOOD_SEARCH_{kind.upper()}_TOOL if needed."
        )

    async def _discover_tools(self) -> dict[str, str]:
        if self._discovered_tools is not None:
            return self._discovered_tools

        tools = await self._list_tools()
        discovered: dict[str, str] = {}

        for tool in tools:
            name = (tool.get("name") or "").lower()
            if "search" in name and "search" not in discovered:
                discovered["search"] = tool["name"]
            if any(hint in name for hint in FETCH_TOOL_HINTS) and "fetch" not in discovered:
                discovered["fetch"] = tool["name"]

        for tool in tools:
            name = (tool.get("name") or "").lower()
            if name in SEARCH_TOOL_HINTS and "search" not in discovered:
                discovered["search"] = tool["name"]
            if name in FETCH_TOOL_HINTS and "fetch" not in discovered:
                discovered["fetch"] = tool["name"]

        self._discovered_tools = discovered
        return discovered

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
            if method == "tools/list" and self._session_id is None:
                await self._initialize(client, headers)

            response = await client.post(self.mcp_url, headers=headers, json=body)
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
        response = await client.post(self.mcp_url, headers=headers, json=init_body)
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

    def _parse_search_results(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        text = self._extract_text(payload)
        if not text:
            return []

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return self._parse_search_results_from_text(text)

        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]

        if isinstance(parsed, dict):
            for key in ("results", "items", "organic", "hits"):
                value = parsed.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

        return []

    def _parse_search_results_from_text(self, text: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        url_pattern = re.compile(r"https?://[^\s)>\"]+")
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        for line in lines:
            urls = url_pattern.findall(line)
            if not urls:
                continue
            results.append(
                {
                    "title": line.split(urls[0])[0].strip(" -:\t") or "Result",
                    "url": urls[0],
                    "snippet": line,
                }
            )

        return results
