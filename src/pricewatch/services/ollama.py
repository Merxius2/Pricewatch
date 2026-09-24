from __future__ import annotations

import json
import re

import httpx

from pricewatch.config import Settings


class OllamaError(Exception):
    pass


PRICE_EXTRACTION_PROMPT = """You are a price extraction assistant. Given product search results and page content,
identify the current retail price for the requested product.

Respond with ONLY valid JSON in this exact shape:
{
  "price": 123.45,
  "currency": "USD",
  "confidence": "high",
  "summary": "One sentence explaining where you found the price"
}

Rules:
- price must be a number without currency symbols
- if no reliable price is found, set price to null and confidence to "none"
- prefer the official retailer or manufacturer price over marketplace listings
- ignore shipping, tax, or subscription fees unless they are the only price shown
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
        currency_hint: str = "USD",
    ) -> dict:
        user_message = (
            f"Product: {product_name}\n"
            f"Search query: {search_query}\n"
            f"Expected currency: {currency_hint}\n\n"
            f"Source material:\n{context[:16000]}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": PRICE_EXTRACTION_PROMPT},
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
