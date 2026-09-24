from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pricewatch.api.schemas import (
    CheckResultOut,
    DashboardStatsOut,
    TrackedItemCreate,
    TrackedItemDetailOut,
    TrackedItemOut,
    TrackedItemUpdate,
)
from pricewatch.db.database import get_db
from pricewatch.db.models import TrackedItem
from pricewatch.scheduler import get_last_run_at
from pricewatch.services.price_checker import PriceChecker

router = APIRouter(prefix="/api")


@router.get("/stats", response_model=DashboardStatsOut)
def get_stats(db: Session = Depends(get_db)) -> DashboardStatsOut:
    items = db.query(TrackedItem).all()
    return DashboardStatsOut(
        total_items=len(items),
        enabled_items=sum(1 for item in items if item.enabled),
        alerts_active=sum(1 for item in items if item.alert_triggered),
        last_run_at=get_last_run_at(),
    )


@router.get("/items", response_model=list[TrackedItemOut])
def list_items(db: Session = Depends(get_db)) -> list[TrackedItem]:
    return db.query(TrackedItem).order_by(TrackedItem.created_at.desc()).all()


@router.get("/items/{item_id}", response_model=TrackedItemDetailOut)
def get_item(item_id: int, db: Session = Depends(get_db)) -> TrackedItem:
    item = db.get(TrackedItem, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


@router.post("/items", response_model=TrackedItemOut, status_code=status.HTTP_201_CREATED)
def create_item(payload: TrackedItemCreate, db: Session = Depends(get_db)) -> TrackedItem:
    item = TrackedItem(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/items/{item_id}", response_model=TrackedItemOut)
def update_item(
    item_id: int,
    payload: TrackedItemUpdate,
    db: Session = Depends(get_db),
) -> TrackedItem:
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
    return item


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
        alert_triggered=result.alert_triggered,
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
                "alert_triggered": result.alert_triggered,
                "message": result.summary if result.success else result.error,
            }
        )
    return {"checked": len(results), "results": results}
