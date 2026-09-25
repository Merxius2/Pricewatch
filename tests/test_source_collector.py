from unittest.mock import AsyncMock, MagicMock

import pytest

from pricewatch.services.source_collector import SourceCollector


def _collector_with_mock(
    *,
    fetch_contents: str = "Product page with price 899.00",
    search_results: list[dict] | None = None,
) -> SourceCollector:
    mock_client = MagicMock()
    mock_client.fetch_contents = AsyncMock(return_value=fetch_contents)
    mock_client.search = AsyncMock(return_value=search_results or [])
    collector = SourceCollector()
    collector.good_search = mock_client
    return collector


@pytest.mark.asyncio
async def test_collect_product_url_without_set_add_crash() -> None:
    """Regression: seen_urls was a list, causing 'list' object has no attribute 'add'."""
    collector = _collector_with_mock()
    url = "https://www.phonemarket.nl/iphone-17e-256gb"

    listings, reference = await collector.collect(
        name="Iphone 17e 256gb",
        search_query="Iphone 17e 256gb 2e kans",
        preferred_site="phonemarket.nl",
        product_url=url,
        also_search_other_sites=False,
        confirmed_urls=[],
    )

    assert len(listings) == 1
    assert listings[0].url == url
    assert listings[0].site == "phonemarket.nl"
    assert listings[0].source_type == "preferred"
    assert reference is not None


@pytest.mark.asyncio
async def test_collect_deduplicates_same_url() -> None:
    url = "https://www.phonemarket.nl/iphone-17e-256gb"
    collector = _collector_with_mock(
        search_results=[{"url": url, "title": "Duplicate listing", "snippet": "Same product"}],
    )

    listings, _ = await collector.collect(
        name="Iphone 17e 256gb",
        search_query="Iphone 17e 256gb",
        preferred_site="phonemarket.nl",
        product_url=url,
        also_search_other_sites=False,
        confirmed_urls=[],
    )

    assert len(listings) == 1
    collector.good_search.fetch_contents.assert_awaited_once()


@pytest.mark.asyncio
async def test_collect_skips_failed_fetches() -> None:
    from pricewatch.services.good_search import GoodSearchError

    mock_client = MagicMock()
    mock_client.fetch_contents = AsyncMock(
        side_effect=GoodSearchError("No content returned for https://example.com")
    )
    mock_client.search = AsyncMock(return_value=[])
    collector = SourceCollector()
    collector.good_search = mock_client

    listings, reference = await collector.collect(
        name="Test product",
        search_query="test",
        preferred_site=None,
        product_url="https://example.com/product",
        also_search_other_sites=False,
        confirmed_urls=[],
    )

    assert listings == []
    assert reference is None


@pytest.mark.asyncio
async def test_collect_preferred_site_search() -> None:
    search_url = "https://www.phonemarket.nl/other-listing"
    collector = _collector_with_mock(
        search_results=[{"url": search_url, "title": "Found via search", "snippet": "Match"}],
    )

    listings, reference = await collector.collect(
        name="Iphone 17e 256gb",
        search_query="Iphone 17e 256gb",
        preferred_site="phonemarket.nl",
        product_url=None,
        also_search_other_sites=False,
        confirmed_urls=[],
    )

    assert len(listings) == 1
    assert listings[0].url == search_url
    collector.good_search.search.assert_awaited_once()
    query = collector.good_search.search.await_args.args[0]
    assert "site:phonemarket.nl" in query


@pytest.mark.asyncio
async def test_collect_confirmed_urls() -> None:
    confirmed = "https://www.bol.com/confirmed-listing"
    collector = _collector_with_mock()

    listings, _ = await collector.collect(
        name="Test",
        search_query="test",
        preferred_site=None,
        product_url=None,
        also_search_other_sites=False,
        confirmed_urls=[confirmed],
    )

    assert len(listings) == 1
    assert listings[0].source_type == "confirmed"
