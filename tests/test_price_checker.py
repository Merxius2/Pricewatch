from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pricewatch.db.models import AlertType, CheckStatus, PriceHistory, TrackedItem
from pricewatch.services.price_checker import PriceChecker


def _make_item(**overrides) -> TrackedItem:
    defaults = {
        "name": "Test product",
        "search_query": "test product",
        "currency": "EUR",
        "alert_type": AlertType.THRESHOLD.value,
    }
    defaults.update(overrides)
    return TrackedItem(**defaults)


class TestEvaluateAlert:
    def test_threshold_alert_triggers_at_or_below_target(self) -> None:
        checker = PriceChecker()
        item = _make_item(target_price=100.0)

        assert checker._evaluate_alert(item, 99.0) is True
        assert checker._evaluate_alert(item, 100.0) is True
        assert checker._evaluate_alert(item, 101.0) is False

    def test_threshold_alert_without_target(self) -> None:
        checker = PriceChecker()
        item = _make_item(target_price=None)

        assert checker._evaluate_alert(item, 50.0) is False

    def test_any_drop_alert(self) -> None:
        checker = PriceChecker()
        item = _make_item(alert_type=AlertType.ANY_DROP.value, current_price=200.0)

        assert checker._evaluate_alert(item, 199.0) is True
        assert checker._evaluate_alert(item, 200.0) is False
        assert checker._evaluate_alert(item, 201.0) is False

    def test_any_drop_without_previous_price(self) -> None:
        checker = PriceChecker()
        item = _make_item(alert_type=AlertType.ANY_DROP.value, current_price=None)

        assert checker._evaluate_alert(item, 100.0) is False

    def test_percent_drop_alert(self) -> None:
        checker = PriceChecker()
        item = _make_item(
            alert_type=AlertType.PERCENT_DROP.value,
            current_price=100.0,
            percent_drop=10.0,
        )

        assert checker._evaluate_alert(item, 89.0) is True
        assert checker._evaluate_alert(item, 91.0) is False

    def test_percent_drop_without_current_price(self) -> None:
        checker = PriceChecker()
        item = _make_item(
            alert_type=AlertType.PERCENT_DROP.value,
            current_price=None,
            percent_drop=10.0,
        )

        assert checker._evaluate_alert(item, 50.0) is False


class TestRecordFailure:
    def test_records_failure_status_and_history(self, db_session) -> None:
        checker = PriceChecker()
        item = _make_item()
        db_session.add(item)
        db_session.commit()

        result = checker._record_failure(db_session, item, "Something went wrong")

        assert result.success is False
        assert result.error == "Something went wrong"
        assert item.last_check_status == CheckStatus.FAILED.value
        assert item.last_check_error == "Something went wrong"
        history = db_session.query(PriceHistory).filter(PriceHistory.item_id == item.id).all()
        assert len(history) == 1
        assert history[0].status == CheckStatus.FAILED.value
        assert history[0].currency == "EUR"


@pytest.mark.asyncio
async def test_check_item_continues_when_secondary_listing_fails(db_session) -> None:
    from pricewatch.services.ollama import OllamaError
    from pricewatch.services.price_checker import VerifiedPrice
    from pricewatch.services.source_collector import SourceListing

    checker = PriceChecker()
    item = _make_item()
    db_session.add(item)
    db_session.commit()

    preferred = SourceListing(
        url="https://www.phonemarket.nl/iphone",
        site="phonemarket.nl",
        title="iPhone",
        content="price page",
        source_type="preferred",
    )
    other = SourceListing(
        url="https://www.example.com/iphone",
        site="example.com",
        title="iPhone",
        content="other page",
        source_type="other",
    )

    async def fake_collect(**kwargs):
        return [preferred, other], "reference"

    async def fake_evaluate(item, listing, reference_context, db):
        if listing.source_type == "preferred":
            return VerifiedPrice(
                price=899.0,
                currency="EUR",
                source_url=listing.url,
                source_site=listing.site,
                summary="ok",
                listing=listing,
            )
        raise OllamaError("Ollama request timed out (120s)")

    with patch.object(checker.collector, "collect", side_effect=fake_collect):
        with patch.object(checker, "_evaluate_listing", side_effect=fake_evaluate):
            result = await checker.check_item(db_session, item)

    assert result.success is True
    assert result.price == 899.0
    assert item.last_check_status == "success"


@pytest.mark.asyncio
async def test_check_item_handles_collector_errors_gracefully(db_session) -> None:
    checker = PriceChecker()
    item = _make_item()
    db_session.add(item)
    db_session.commit()

    with patch.object(
        checker.collector,
        "collect",
        AsyncMock(side_effect=RuntimeError("network down")),
    ):
        result = await checker.check_item(db_session, item)

    assert result.success is False
    assert "Unexpected error: network down" in (result.error or "")
    assert item.last_check_status == CheckStatus.FAILED.value
