from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from pricewatch.config import Settings, get_settings
from pricewatch.db.models import AlertType, CheckStatus, PriceHistory, TrackedItem
from pricewatch.services.good_search import GoodSearchClient, GoodSearchError
from pricewatch.services.ollama import OllamaClient, OllamaError


class PriceCheckResult:
    def __init__(
        self,
        *,
        success: bool,
        price: float | None = None,
        currency: str | None = None,
        source_url: str | None = None,
        summary: str | None = None,
        alert_triggered: bool = False,
        error: str | None = None,
    ) -> None:
        self.success = success
        self.price = price
        self.currency = currency
        self.source_url = source_url
        self.summary = summary
        self.alert_triggered = alert_triggered
        self.error = error


class PriceChecker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.good_search = GoodSearchClient(self.settings)
        self.ollama = OllamaClient(self.settings)

    async def check_item(self, db: Session, item: TrackedItem) -> PriceCheckResult:
        try:
            context, source_url = await self.good_search.gather_product_context(
                search_query=item.search_query,
                product_url=item.product_url,
            )
            extraction = await self.ollama.extract_price(
                product_name=item.name,
                search_query=item.search_query,
                context=context,
                currency_hint=item.currency,
            )

            price = extraction.get("price")
            currency = extraction.get("currency") or item.currency
            summary = extraction.get("summary")
            confidence = extraction.get("confidence", "none")

            if price is None or confidence == "none":
                return self._record_failure(
                    db,
                    item,
                    "LLM could not find a reliable price in search results.",
                )

            price = float(price)
            alert_triggered = self._evaluate_alert(item, price)
            self._record_success(db, item, price, currency, source_url, summary, alert_triggered)

            return PriceCheckResult(
                success=True,
                price=price,
                currency=currency,
                source_url=source_url,
                summary=summary,
                alert_triggered=alert_triggered,
            )
        except (GoodSearchError, OllamaError) as exc:
            return self._record_failure(db, item, str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._record_failure(db, item, f"Unexpected error: {exc}")

    def _evaluate_alert(self, item: TrackedItem, new_price: float) -> bool:
        if item.alert_type == AlertType.THRESHOLD.value:
            return item.target_price is not None and new_price <= item.target_price

        if item.alert_type == AlertType.ANY_DROP.value:
            return item.current_price is not None and new_price < item.current_price

        if item.alert_type == AlertType.PERCENT_DROP.value:
            if item.current_price is None or not item.percent_drop:
                return False
            drop_pct = ((item.current_price - new_price) / item.current_price) * 100
            return drop_pct >= item.percent_drop

        return False

    def _record_success(
        self,
        db: Session,
        item: TrackedItem,
        price: float,
        currency: str,
        source_url: str | None,
        summary: str | None,
        alert_triggered: bool,
    ) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        item.previous_price = item.current_price
        item.current_price = price
        item.lowest_price = price if item.lowest_price is None else min(item.lowest_price, price)
        item.last_checked_at = now
        item.last_check_status = CheckStatus.SUCCESS.value
        item.last_check_error = None

        if alert_triggered:
            item.alert_triggered = True
            item.alert_triggered_at = now
        elif item.alert_type == AlertType.THRESHOLD.value and item.target_price is not None:
            item.alert_triggered = price <= item.target_price

        db.add(
            PriceHistory(
                item_id=item.id,
                price=price,
                currency=currency,
                source_url=source_url,
                raw_summary=summary,
                status=CheckStatus.SUCCESS.value,
            )
        )
        db.commit()
        db.refresh(item)

    def _record_failure(self, db: Session, item: TrackedItem, error: str) -> PriceCheckResult:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        item.last_checked_at = now
        item.last_check_status = CheckStatus.FAILED.value
        item.last_check_error = error
        db.add(
            PriceHistory(
                item_id=item.id,
                price=None,
                currency=item.currency,
                status=CheckStatus.FAILED.value,
                error=error,
            )
        )
        db.commit()
        db.refresh(item)
        return PriceCheckResult(success=False, error=error)
