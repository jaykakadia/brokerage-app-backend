import json
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin, get_db
from app.db.models.category import Category
from app.db.models.listing import Listing
from app.db.models.user import User
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.category import CategoryRead, CategoryCreate, CategoryUpdate

router = APIRouter(prefix="/api/v1/categories", tags=["Categories"])


def _listing_category_name(form_data: Any) -> str:
    data = form_data
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("category") or "").strip().lower()


def _listing_counts_by_category(db: Session) -> Dict[str, int]:
    rows = db.query(Listing.form_data, Listing.status).all()
    counts: Dict[str, int] = {}
    for form_data, status_value in rows:
        if (status_value or "").lower() == "deleted":
            continue
        name = _listing_category_name(form_data)
        if not name:
            continue
        counts[name] = counts.get(name, 0) + 1
    return counts


def _to_category_read(category: Category, counts: Dict[str, int]) -> CategoryRead:
    return CategoryRead(
        id=category.id,
        name=category.name,
        description=category.description,
        total_listings=counts.get(category.name.strip().lower(), 0),
        created_at=category.created_at
    )


@router.get("", response_model=APIResponse[List[CategoryRead]])
def get_categories(db: Session = Depends(get_db)):
    cats = db.query(Category).order_by(Category.name.asc()).all()
    if not cats:
        # Default real estate and business categories
        defaults = [
            ("Residential Flat", "Apartments and builder floors"),
            ("Independent House/Villa", "Villas, kothis and independent houses"),
            ("Residential Plot", "Plots and land parcels"),
            ("Commercial Property", "Shops, showrooms and office spaces"),
            ("Agricultural Land", "Farmland and agricultural holdings")
        ]
        cats = [Category(name=n, description=d) for n, d in defaults]
        db.add_all(cats)
        db.commit()
        for c in cats:
            db.refresh(c)
    counts = _listing_counts_by_category(db)
    return APIResponse(status="success", data=[_to_category_read(c, counts) for c in cats])


@router.get("/{category_id}", response_model=APIResponse[CategoryRead])
def get_category(category_id: int, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found.")
    counts = _listing_counts_by_category(db)
    return APIResponse(status="success", data=_to_category_read(cat, counts))


@router.post("", response_model=APIResponse[CategoryRead])
def create_or_save_category(
    req: CategoryCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    existing = db.query(Category).filter(Category.name.ilike(req.name.strip())).first()
    if existing:
        existing.description = req.description
        db.commit()
        db.refresh(existing)
        counts = _listing_counts_by_category(db)
        return APIResponse(status="success", data=_to_category_read(existing, counts))

    cat = Category(name=req.name.strip(), description=req.description)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    counts = _listing_counts_by_category(db)
    return APIResponse(status="success", data=_to_category_read(cat, counts))


@router.put("/{category_id}", response_model=APIResponse[CategoryRead])
def update_category(
    category_id: int,
    req: CategoryUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found.")
    if req.name is not None:
        cat.name = req.name.strip()
    if req.description is not None:
        cat.description = req.description
    db.commit()
    db.refresh(cat)
    counts = _listing_counts_by_category(db)
    return APIResponse(status="success", data=_to_category_read(cat, counts))


@router.delete("/{category_id}", response_model=MessageResponse)
@router.post("/{category_id}/delete", response_model=MessageResponse)
def delete_category(
    category_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found.")
    db.delete(cat)
    db.commit()
    return MessageResponse(status="success", message="Category deleted successfully.")
