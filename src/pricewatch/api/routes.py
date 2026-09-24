from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from pricewatch.api.schemas import (
    CheckResultOut,
    DashboardStatsOut,
    ProductMatchReviewOut,
    TrackedItemCreate,
    TrackedItemDetailOut,
    TrackedItemOut,
    TrackedItemUpdate,
)
from pricewatch.db.database import get_db
from pricewatch.db.models import MatchReviewStatus, ProductMatchReview, TrackedItem
from pricewatch.scheduler import get_last_run_at
from pricewatch.services.price_checker import PriceChecker, confirm_match_review, reject_match_review

router = APIRouter(prefix="/api")


def _serialize_item(item: TrackedItem) -> TrackedItemOut:
    pending = sum(
        1
        for review in getattr(item, "match_reviews", [])
        if review.status == MatchReviewStatus.PENDING.value
    )
    data = TrackedItemOut.model_validate(item)
    data.pending_match_reviews = pending
    return data


def _serialize_review(review: ProductMatchReview) -> ProductMatchReviewOut:
    data = ProductMatchReviewOut.model_validate(review)
    data.item_name = review.item.name if review.item else None
    return data


@router.get("/stats", response_model=DashboardStatsOut)
def get_stats(db: Session = Depends(get_db)) -> DashboardStatsOut:
    items = db.query(TrackedItem).options(joinedload(TrackedItem.match_reviews)).all()
    pending = (
        db.query(ProductMatchReview)
        .filter(ProductMatchReview.status == MatchReviewStatus.PENDING.value)
        .count()
    )
    return DashboardStatsOut(
        total_items=len(items),
        enabled_items=sum(1 for item in items if item.enabled),
        alerts_active=sum(1 for item in items if item.alert_triggered),
        pending_match_reviews=pending,
        last_run_at=get_last_run_at(),
    )


@router.get("/items", response_model=list[TrackedItemOut])
def list_items(db: Session = Depends(get_db)) -> list[TrackedItemOut]:
    items = (
        db.query(TrackedItem)
        .options(joinedload(TrackedItem.match_reviews))
        .order_by(TrackedItem.created_at.desc())
        .all()
    )
    return [_serialize_item(item) for item in items]


@router.get("/items/{item_id}", response_model=TrackedItemDetailOut)
def get_item(item_id: int, db: Session = Depends(get_db)) -> TrackedItemDetailOut:
    item = (
        db.query(TrackedItem)
        .options(
            joinedload(TrackedItem.price_history),
            joinedload(TrackedItem.match_reviews),
        )
        .filter(TrackedItem.id == item_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    data = TrackedItemDetailOut.model_validate(item)
    data.pending_match_reviews = sum(
        1 for review in item.match_reviews if review.status == MatchReviewStatus.PENDING.value
    )
    data.pending_reviews = [
        _serialize_review(review)
        for review in item.match_reviews
        if review.status == MatchReviewStatus.PENDING.value
    ]
    return data


@router.post("/items", response_model=TrackedItemOut, status_code=status.HTTP_201_CREATED)
def create_item(payload: TrackedItemCreate, db: Session = Depends(get_db)) -> TrackedItemOut:
    item = TrackedItem(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_item(item)


@router.patch("/items/{item_id}", response_model=TrackedItemOut)
def update_item(
    item_id: int,
    payload: TrackedItemUpdate,
    db: Session = Depends(get_db),
) -> TrackedItemOut:
    item = db.get(TrackedItem, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    if payload.model_dump(exclude_unset=True):
        item.alert_triggered = False
        item.alert_triggered_at = None

    db.commit()
    db.refresh(item)
    return _serialize_item(item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, db: Session = Depends(get_db)) -> None:
    item = db.get(TrackedItem, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    db.delete(item)
    db.commit()


@router.post("/items/{item_id}/check", response_model=CheckResultOut)
async def check_item_now(item_id: int, db: Session = Depends(get_db)) -> CheckResultOut:
    item = db.get(TrackedItem, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    result = await PriceChecker().check_item(db, item)
    return CheckResultOut(
        item_id=item.id,
        success=result.success,
        price=result.price,
        currency=result.currency,
        source_url=result.source_url,
        source_site=result.source_site,
        alert_triggered=result.alert_triggered,
        pending_reviews=result.pending_reviews,
        message=result.summary if result.success else result.error,
    )


@router.post("/check-all")
async def check_all_enabled(db: Session = Depends(get_db)) -> dict:
    checker = PriceChecker()
    items = db.query(TrackedItem).filter(TrackedItem.enabled.is_(True)).all()
    results = []
    for item in items:
        result = await checker.check_item(db, item)
        results.append(
            {
                "item_id": item.id,
                "name": item.name,
                "success": result.success,
                "price": result.price,
                "source_site": result.source_site,
                "alert_triggered": result.alert_triggered,
                "pending_reviews": result.pending_reviews,
                "message": result.summary if result.success else result.error,
            }
        )
    return {"checked": len(results), "results": results}


@router.get("/match-reviews", response_model=list[ProductMatchReviewOut])
def list_match_reviews(
    status_filter: str = MatchReviewStatus.PENDING.value,
    db: Session = Depends(get_db),
) -> list[ProductMatchReviewOut]:
    reviews = (
        db.query(ProductMatchReview)
        .options(joinedload(ProductMatchReview.item))
        .filter(ProductMatchReview.status == status_filter)
        .order_by(ProductMatchReview.created_at.desc())
        .all()
    )
    return [_serialize_review(review) for review in reviews]


@router.post("/match-reviews/{review_id}/confirm", response_model=ProductMatchReviewOut)
def confirm_review(review_id: int, db: Session = Depends(get_db)) -> ProductMatchReviewOut:
    review = (
        db.query(ProductMatchReview)
        .options(joinedload(ProductMatchReview.item))
        .filter(ProductMatchReview.id == review_id)
        .first()
    )
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    if review.status != MatchReviewStatus.PENDING.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Review already resolved")

    confirm_match_review(db, review)
    db.refresh(review)
    return _serialize_review(review)


@router.post("/match-reviews/{review_id}/reject", response_model=ProductMatchReviewOut)
def reject_review(review_id: int, db: Session = Depends(get_db)) -> ProductMatchReviewOut:
    review = (
        db.query(ProductMatchReview)
        .options(joinedload(ProductMatchReview.item))
        .filter(ProductMatchReview.id == review_id)
        .first()
    )
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    if review.status != MatchReviewStatus.PENDING.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Review already resolved")

    reject_match_review(db, review)
    db.refresh(review)
    return _serialize_review(review)
