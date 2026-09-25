from __future__ import annotations

import json
import re

import httpx

from pricewatch.config import Settings


class OllamaError(Exception):
    pass


PRICE_EXTRACTION_PROMPT = """You are a price extraction assistant. Given product page content,
identify the current retail price for the requested product on that specific page.

Respond with ONLY valid JSON in this exact shape:
{
  "price": 123.45,
  "currency": "EUR",
  "confidence": "high",
  "product_title": "Exact product title shown on the page",
  "summary": "One sentence explaining where you found the price"
}

Rules:
- price must be a number without currency symbols
- if no reliable price is found, set price to null and confidence to "none"
- only extract the price for the main product on the page, not accessories or bundles unless the page is clearly for a bundle
- ignore shipping, tax, or subscription fees unless they are the only price shown
"""


PRODUCT_MATCH_PROMPT = """You compare whether a product listing found on another website is the same product
as the one the user is tracking.

Respond with ONLY valid JSON in this exact shape:
{
  "same_product": true,
  "confidence": "high",
  "reason": "Short explanation comparing model, variant, color, storage, etc."
}

Confidence rules:
- "high": clearly the same product (same model/variant)
- "medium": likely the same but variant details are ambiguous (e.g. color unknown)
- "low": probably a different variant, bundle, refurbished item, or unrelated listing

Set same_product to false when confidence would be low.
"""


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model

    async def extract_price(
        self,
        *,
        product_name: str,
        search_query: str,
        context: str,
        source_url: str | None = None,
        currency_hint: str = "EUR",
    ) -> dict:
        source_line = f"Page URL: {source_url}\n" if source_url else ""
        user_message = (
            f"Product being tracked: {product_name}\n"
            f"Search query: {search_query}\n"
            f"Expected currency: {currency_hint}\n"
            f"{source_line}\n"
            f"Page content:\n{context[:16000]}"
        )
        return await self._chat_json(PRICE_EXTRACTION_PROMPT, user_message)

    async def compare_product_match(
        self,
        *,
        tracked_name: str,
        search_query: str,
        reference_context: str,
        candidate_url: str,
        candidate_site: str,
        candidate_title: str | None,
        candidate_content: str,
    ) -> dict:
        user_message = (
            f"Tracked product name: {tracked_name}\n"
            f"Search query: {search_query}\n\n"
            f"Reference listing (preferred/known product):\n{reference_context[:6000]}\n\n"
            f"Candidate listing:\n"
            f"Site: {candidate_site}\n"
            f"URL: {candidate_url}\n"
            f"Title: {candidate_title or 'Unknown'}\n"
            f"Content:\n{candidate_content[:8000]}"
        )
        return await self._chat_json(PRODUCT_MATCH_PROMPT, user_message)

    async def _chat_json(self, system_prompt: str, user_message: str) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "format": "json",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            if response.status_code >= 400:
                raise OllamaError(f"Ollama request failed ({response.status_code}): {response.text}")

            data = response.json()
            content = data.get("message", {}).get("content", "")
            return self._parse_json_response(content)

    def _parse_json_response(self, content: str) -> dict:
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if not match:
                raise OllamaError(f"Could not parse LLM response as JSON: {content[:500]}")
            return json.loads(match.group(0))
