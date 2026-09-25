from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pricewatch.db.database import Base


class AlertType(str, Enum):
    THRESHOLD = "threshold"
    ANY_DROP = "any_drop"
    PERCENT_DROP = "percent_drop"


class CheckStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class MatchReviewStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class TrackedItem(Base):
    __tablename__ = "tracked_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    search_query: Mapped[str] = mapped_column(String(512), nullable=False)
    preferred_site: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    also_search_other_sites: Mapped[bool] = mapped_column(Boolean, default=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    alert_type: Mapped[str] = mapped_column(String(32), default=AlertType.THRESHOLD.value)
    percent_drop: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    check_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    current_source_site: Mapped[str | None] = mapped_column(String(255), nullable=True)
    previous_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    lowest_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_check_status: Mapped[str] = mapped_column(String(32), default=CheckStatus.PENDING.value)
    last_check_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    alert_triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    price_history: Mapped[list["PriceHistory"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="PriceHistory.checked_at.desc()"
    )
    match_reviews: Mapped[list["ProductMatchReview"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="ProductMatchReview.created_at.desc()"
    )
    confirmed_alternates: Mapped[list["ConfirmedAlternateSite"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="ConfirmedAlternateSite.confirmed_at.desc()"
    )


class ConfirmedAlternateSite(Base):
    __tablename__ = "confirmed_alternate_sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("tracked_items.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    site: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    item: Mapped[TrackedItem] = relationship(back_populates="confirmed_alternates")


class ProductMatchReview(Base):
    __tablename__ = "product_match_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("tracked_items.id", ondelete="CASCADE"))
    found_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    found_site: Mapped[str] = mapped_column(String(255), nullable=False)
    found_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    found_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    found_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    match_confidence: Mapped[str] = mapped_column(String(16), default="low")
    match_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=MatchReviewStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    item: Mapped[TrackedItem] = relationship(back_populates="match_reviews")


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("tracked_items.id", ondelete="CASCADE"))
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_site: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(String(32), default=CheckStatus.SUCCESS.value)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    item: Mapped[TrackedItem] = relationship(back_populates="price_history")
