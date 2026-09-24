from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


AlertTypeLiteral = Literal["threshold", "any_drop", "percent_drop"]
CheckStatusLiteral = Literal["pending", "success", "failed", "needs_review"]
MatchReviewStatusLiteral = Literal["pending", "confirmed", "rejected"]


class TrackedItemBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    search_query: str = Field(min_length=1, max_length=512)
    preferred_site: str | None = Field(
        default=None,
        max_length=255,
        description="Website to check first, e.g. bol.com or https://www.bol.com",
    )
    product_url: str | None = Field(
        default=None,
        description="Direct product page on the preferred website (optional)",
    )
    also_search_other_sites: bool = True
    target_price: float | None = Field(default=None, ge=0)
    alert_type: AlertTypeLiteral = "threshold"
    percent_drop: float | None = Field(default=None, ge=0, le=100)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    notes: str | None = None
    tags: str | None = None
    enabled: bool = True
    check_interval_minutes: int | None = Field(default=None, ge=5)


class TrackedItemCreate(TrackedItemBase):
    pass


class TrackedItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    search_query: str | None = Field(default=None, min_length=1, max_length=512)
    preferred_site: str | None = Field(default=None, max_length=255)
    product_url: str | None = None
    also_search_other_sites: bool | None = None
    target_price: float | None = Field(default=None, ge=0)
    alert_type: AlertTypeLiteral | None = None
    percent_drop: float | None = Field(default=None, ge=0, le=100)
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    notes: str | None = None
    tags: str | None = None
    enabled: bool | None = None
    check_interval_minutes: int | None = Field(default=None, ge=5)


class PriceHistoryOut(BaseModel):
    id: int
    price: float | None
    currency: str
    source_url: str | None
    source_site: str | None = None
    checked_at: datetime
    status: CheckStatusLiteral
    error: str | None

    model_config = {"from_attributes": True}


class ProductMatchReviewOut(BaseModel):
    id: int
    item_id: int
    item_name: str | None = None
    found_url: str
    found_site: str
    found_title: str | None
    found_price: float | None
    found_currency: str | None
    match_confidence: str
    match_reason: str | None
    page_excerpt: str | None
    status: MatchReviewStatusLiteral
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class TrackedItemOut(TrackedItemBase):
    id: int
    current_price: float | None
    current_source_url: str | None = None
    current_source_site: str | None = None
    previous_price: float | None
    lowest_price: float | None
    last_checked_at: datetime | None
    last_check_status: CheckStatusLiteral
    last_check_error: str | None
    alert_triggered: bool
    alert_triggered_at: datetime | None
    pending_match_reviews: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TrackedItemDetailOut(TrackedItemOut):
    price_history: list[PriceHistoryOut] = []
    pending_reviews: list[ProductMatchReviewOut] = []


class CheckResultOut(BaseModel):
    item_id: int
    success: bool
    price: float | None = None
    currency: str | None = None
    source_url: str | None = None
    source_site: str | None = None
    alert_triggered: bool = False
    pending_reviews: int = 0
    message: str | None = None


class DashboardStatsOut(BaseModel):
    total_items: int
    enabled_items: int
    alerts_active: int
    pending_match_reviews: int = 0
    last_run_at: datetime | None = None
