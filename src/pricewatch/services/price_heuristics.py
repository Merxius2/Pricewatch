from __future__ import annotations

import json
import re
from html import unescape
from typing import Any


class HeuristicPriceError(Exception):
    pass


_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_META_PRICE_RE = re.compile(
    r'(?:property|name)=["\'](?:product:price:amount|og:price:amount)["\'][^>]*content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_ITEMPROP_PRICE_RE = re.compile(
    r'itemprop=["\']price["\'][^>]*content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_EURO_RE = re.compile(
    r"(?:€|EUR)\s*(\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)"
    r"|(\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)\s*(?:€|EUR)",
    re.IGNORECASE,
)


def extract_price_heuristic(
    content: str,
    *,
    currency_hint: str = "EUR",
) -> dict[str, Any] | None:
    """Best-effort price parse from HTML/text without an LLM."""
    if not content or not content.strip():
        return None

    content = unescape(content)

    for match in _JSON_LD_RE.finditer(content):
        raw = unescape(match.group(1)).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        found = _price_from_json_ld(payload)
        if found:
            price, currency = found
            return _result(
                price,
                currency or currency_hint,
                "high",
                "Structured data (JSON-LD) on the page",
            )

    for pattern in (_META_PRICE_RE, _ITEMPROP_PRICE_RE):
        meta = pattern.search(content)
        if meta:
            price = _parse_amount(meta.group(1))
            if price is not None:
                return _result(
                    price,
                    currency_hint,
                    "medium",
                    "Product meta tag on the page",
                )

    dutch_price = _best_dutch_euro_price(content)
    if dutch_price is not None:
        return _result(
            dutch_price,
            currency_hint,
            "medium",
            "Euro price on the product page (Dutch format)",
        )

    euro_match = _EURO_RE.search(content)
    if euro_match:
        raw = euro_match.group(1) or euro_match.group(2)
        price = _parse_amount(raw)
        if price is not None:
            return _result(
                price,
                currency_hint,
                "low",
                "Euro amount pattern in page text",
            )

    return None


_DUTCH_EURO_PRICE_RE = re.compile(
    r"€\s*(\d{1,3}(?:\.\d{3})*|\d+)\s*(?:,\s*-|,\d{2})",
    re.IGNORECASE,
)


def _best_dutch_euro_price(content: str) -> float | None:
    """Pick the main product price when a page lists accessories too (e.g. PhoneMarket)."""
    best: float | None = None
    best_score = -1.0

    for match in _DUTCH_EURO_PRICE_RE.finditer(content):
        prefix = content[max(0, match.start() - 24) : match.start()].lower()
        if "adviesprijs" in prefix:
            continue

        amount = _parse_amount(match.group(1))
        if amount is None or amount < 20:
            continue

        window = content[match.start() : match.end() + 48].lower()
        score = amount
        if "op voorraad" in window:
            score += 10_000
        if "toevoegen aan winkelwagen" in window:
            score += 5_000
        if "winkelwagen" in window:
            score += 1_000

        if score > best_score:
            best_score = score
            best = amount

    return best


def _result(price: float, currency: str, confidence: str, summary: str) -> dict[str, Any]:
    return {
        "price": price,
        "currency": currency.upper() if len(currency) <= 8 else currency,
        "confidence": confidence,
        "summary": summary,
        "product_title": None,
    }


def _parse_amount(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    text = re.sub(r"[^\d,.\-]", "", text)
    if not text:
        return None

    # Dutch/EU: 1.299,00 vs US 1,299.00
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        parts = text.split(",")
        if len(parts[-1]) == 2:
            text = parts[0].replace(".", "") + "." + parts[1]
        else:
            text = text.replace(",", ".")
    else:
        text = text.replace(",", "")

    try:
        value = float(text)
    except ValueError:
        return None
    return value if value >= 0 else None


def _price_from_json_ld(node: Any) -> tuple[float, str | None] | None:
    if isinstance(node, list):
        for item in node:
            found = _price_from_json_ld(item)
            if found:
                return found
        return None

    if not isinstance(node, dict):
        return None

    if "@graph" in node:
        return _price_from_json_ld(node["@graph"])

    types = node.get("@type")
    type_names = types if isinstance(types, list) else [types]
    type_names = [str(t).lower() for t in type_names if t]

    if any("product" in t for t in type_names):
        offers = node.get("offers")
        found = _price_from_offers(offers)
        if found:
            return found

    for value in node.values():
        if isinstance(value, (dict, list)):
            found = _price_from_json_ld(value)
            if found:
                return found
    return None


def _price_from_offers(offers: Any) -> tuple[float, str | None] | None:
    if offers is None:
        return None
    if isinstance(offers, list):
        for offer in offers:
            found = _price_from_offer(offer)
            if found:
                return found
        return None
    return _price_from_offer(offers)


def _price_from_offer(offer: Any) -> tuple[float, str | None] | None:
    if not isinstance(offer, dict):
        return None
    price = offer.get("price")
    if price is None and isinstance(offer.get("priceSpecification"), dict):
        spec = offer["priceSpecification"]
        price = spec.get("price") or spec.get("minPrice")
    if price is None:
        return None
    amount = _parse_amount(str(price))
    if amount is None:
        return None
    currency = offer.get("priceCurrency")
    if isinstance(offer.get("priceSpecification"), dict):
        currency = currency or offer["priceSpecification"].get("priceCurrency")
    return amount, str(currency) if currency else None
