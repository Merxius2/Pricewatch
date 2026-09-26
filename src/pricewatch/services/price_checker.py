from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from pricewatch.config import Settings, get_settings
from pricewatch.db.models import (
    AlertType,
    CheckStatus,
    ConfirmedAlternateSite,
    MatchReviewStatus,
    PriceHistory,
    ProductMatchReview,
    TrackedItem,
)
from pricewatch.services.good_search import GoodSearchError
from pricewatch.services.ollama import OllamaClient, OllamaError
from pricewatch.services.source_collector import SourceCollector, SourceListing
from pricewatch.utils.urls import site_from_url


class PriceCheckResult:
    def __init__(
        self,
        *,
        success: bool,
        price: float | None = None,
        currency: str | None = None,
        source_url: str | None = None,
        source_site: str | None = None,
        summary: str | None = None,
        alert_triggered: bool = False,
        pending_reviews: int = 0,
        error: str | None = None,
    ) -> None:
        self.success = success
        self.price = price
        self.currency = currency
        self.source_url = source_url
        self.source_site = source_site
        self.summary = summary
        self.alert_triggered = alert_triggered
        self.pending_reviews = pending_reviews
        self.error = error


class VerifiedPrice:
    def __init__(
        self,
        *,
        price: float,
        currency: str,
        source_url: str,
        source_site: str,
        summary: str,
        listing: SourceListing,
    ) -> None:
        self.price = price
        self.currency = currency
        self.source_url = source_url
        self.source_site = source_site
        self.summary = summary
        self.listing = listing


class PriceChecker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.collector = SourceCollector(self.settings)
        self.ollama = OllamaClient(self.settings)

    async def check_item(self, db: Session, item: TrackedItem) -> PriceCheckResult:
        try:
            confirmed_urls = [alt.url for alt in item.confirmed_alternates]
            listings, reference_context = await self.collector.collect(
                name=item.name,
                search_query=item.search_query,
                preferred_site=item.preferred_site,
                product_url=item.product_url,
                also_search_other_sites=item.also_search_other_sites,
                confirmed_urls=confirmed_urls,
            )
            if not listings:
                return self._record_failure(db, item, "No pages could be loaded for this product.")

            verified_prices: list[VerifiedPrice] = []
            pending_reviews = 0

            for listing in listings:
                try:
                    verified = await self._evaluate_listing(
                        item, listing, reference_context, db
                    )
                except (GoodSearchError, OllamaError) as exc:
                    logger.warning(
                        "Skipping listing %s after service error: %s",
                        listing.url,
                        exc,
                    )
                    continue
                except Exception:
                    logger.exception("Skipping listing %s after unexpected error", listing.url)
                    continue

                if verified:
                    verified_prices.append(verified)
                elif listing.source_type == "other":
                    pending_reviews += 1

            if not verified_prices:
                pending_count = self._count_pending_reviews(db, item.id)
                message = (
                    "No verified prices found."
                    if pending_count == 0
                    else f"No verified prices yet — {pending_count} listing(s) waiting for your confirmation."
                )
                return self._record_needs_review(db, item, message, pending_count)

            best = min(verified_prices, key=lambda entry: entry.price)
            alert_triggered = self._evaluate_alert(item, best.price)
            summary = (
                f"Best price {best.price} {best.currency} on {best.source_site}. "
                f"{best.summary}"
            )
            self._record_success(
                db,
                item,
                best.price,
                best.currency,
                best.source_url,
                best.source_site,
                summary,
                alert_triggered,
            )

            pending_count = self._count_pending_reviews(db, item.id)
            return PriceCheckResult(
                success=True,
                price=best.price,
                currency=best.currency,
                source_url=best.source_url,
                source_site=best.source_site,
                summary=summary,
                alert_triggered=alert_triggered,
                pending_reviews=pending_count,
            )
        except (GoodSearchError, OllamaError) as exc:
            return self._record_failure(db, item, str(exc))
        except Exception as exc:  # noqa: BLE001
            detail = str(exc).strip() or type(exc).__name__
            return self._record_failure(db, item, f"Unexpected error: {detail}")

    async def _evaluate_listing(
        self,
        item: TrackedItem,
        listing: SourceListing,
        reference_context: str | None,
        db: Session,
    ) -> VerifiedPrice | None:
        extraction = await self.ollama.extract_price(
            product_name=item.name,
            search_query=item.search_query,
            context=listing.content,
            source_url=listing.url,
            currency_hint=item.currency,
        )
        price = extraction.get("price")
        currency = extraction.get("currency") or item.currency
        confidence = extraction.get("confidence", "none")
        summary = extraction.get("summary") or f"Price found on {listing.site}"
        title = extraction.get("product_title") or listing.title

        if price is None or confidence == "none":
            return None

        if listing.source_type in {"preferred", "confirmed"}:
            return VerifiedPrice(
                price=float(price),
                currency=currency,
                source_url=listing.url,
                source_site=listing.site,
                summary=summary,
                listing=listing,
            )

        match = await self.ollama.compare_product_match(
            tracked_name=item.name,
            search_query=item.search_query,
            reference_context=reference_context or listing.content,
            candidate_url=listing.url,
            candidate_site=listing.site,
            candidate_title=title,
            candidate_content=listing.content,
        )
        same_product = bool(match.get("same_product"))
        match_confidence = match.get("confidence", "low")
        reason = match.get("reason") or "The model could not confirm this is the same product."

        if same_product and match_confidence == "high":
            return VerifiedPrice(
                price=float(price),
                currency=currency,
                source_url=listing.url,
                source_site=listing.site,
                summary=f"{summary} (matched on {listing.site})",
                listing=listing,
            )

        self._upsert_match_review(
            db,
            item_id=item.id,
            listing=listing,
            title=title,
            price=float(price),
            currency=currency,
            confidence=match_confidence if same_product else "low",
            reason=reason,
        )
        return None

    def _upsert_match_review(
        self,
        db: Session,
        *,
        item_id: int,
        listing: SourceListing,
        title: str | None,
        price: float,
        currency: str,
        confidence: str,
        reason: str,
    ) -> None:
        existing = (
            db.query(ProductMatchReview)
            .filter(
                ProductMatchReview.item_id == item_id,
                ProductMatchReview.found_url == listing.url,
                ProductMatchReview.status == MatchReviewStatus.PENDING.value,
            )
            .first()
        )
        excerpt = listing.content[:1200]
        if existing:
            existing.found_title = title
            existing.found_price = price
            existing.found_currency = currency
            existing.match_confidence = confidence
            existing.match_reason = reason
            existing.page_excerpt = excerpt
        else:
            db.add(
                ProductMatchReview(
                    item_id=item_id,
                    found_url=listing.url,
                    found_site=listing.site,
                    found_title=title,
                    found_price=price,
                    found_currency=currency,
                    match_confidence=confidence,
                    match_reason=reason,
                    page_excerpt=excerpt,
                    status=MatchReviewStatus.PENDING.value,
                )
            )
        db.commit()

    def _count_pending_reviews(self, db: Session, item_id: int) -> int:
        return (
            db.query(ProductMatchReview)
            .filter(
                ProductMatchReview.item_id == item_id,
                ProductMatchReview.status == MatchReviewStatus.PENDING.value,
            )
            .count()
        )

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
        source_url: str,
        source_site: str,
        summary: str,
        alert_triggered: bool,
    ) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        item.previous_price = item.current_price
        item.current_price = price
        item.current_source_url = source_url
        item.current_source_site = source_site
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
                source_site=source_site,
                raw_summary=summary,
                status=CheckStatus.SUCCESS.value,
            )
        )
        db.commit()
        db.refresh(item)

    def _record_needs_review(
        self,
        db: Session,
        item: TrackedItem,
        message: str,
        pending_reviews: int,
    ) -> PriceCheckResult:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        item.last_checked_at = now
        item.last_check_status = CheckStatus.NEEDS_REVIEW.value
        item.last_check_error = message
        db.commit()
        db.refresh(item)
        return PriceCheckResult(success=False, pending_reviews=pending_reviews, error=message)

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


def confirm_match_review(db: Session, review: ProductMatchReview) -> TrackedItem:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    review.status = MatchReviewStatus.CONFIRMED.value
    review.resolved_at = now

    existing = (
        db.query(ConfirmedAlternateSite)
        .filter(
            ConfirmedAlternateSite.item_id == review.item_id,
            ConfirmedAlternateSite.url == review.found_url,
        )
        .first()
    )
    if not existing:
        db.add(
            ConfirmedAlternateSite(
                item_id=review.item_id,
                url=review.found_url,
                site=review.found_site,
                label=review.found_title,
            )
        )

    item = review.item
    if review.found_price is not None:
        if item.current_price is None or review.found_price < item.current_price:
            item.previous_price = item.current_price
            item.current_price = review.found_price
            item.current_source_url = review.found_url
            item.current_source_site = review.found_site
            item.lowest_price = (
                review.found_price
                if item.lowest_price is None
                else min(item.lowest_price, review.found_price)
            )
            item.last_check_status = CheckStatus.SUCCESS.value
            item.last_check_error = None
            db.add(
                PriceHistory(
                    item_id=item.id,
                    price=review.found_price,
                    currency=review.found_currency or item.currency,
                    source_url=review.found_url,
                    source_site=review.found_site,
                    raw_summary=f"Confirmed by user as the same product on {review.found_site}.",
                    status=CheckStatus.SUCCESS.value,
                )
            )

    db.commit()
    db.refresh(item)
    return item


def reject_match_review(db: Session, review: ProductMatchReview) -> None:
    review.status = MatchReviewStatus.REJECTED.value
    review.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
