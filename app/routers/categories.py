from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin, get_db
from app.db.models.category import Category
from app.db.models.user import User
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.category import CategoryRead, CategoryCreate, CategoryUpdate

router = APIRouter(prefix="/api/v1/categories", tags=["Categories"])


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
    return APIResponse(status="success", data=[CategoryRead.model_validate(c) for c in cats])


@router.get("/{category_id}", response_model=APIResponse[CategoryRead])
def get_category(category_id: int, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found.")
    return APIResponse(status="success", data=CategoryRead.model_validate(cat))


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
        return APIResponse(status="success", data=CategoryRead.model_validate(existing))

    cat = Category(name=req.name.strip(), description=req.description)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return APIResponse(status="success", data=CategoryRead.model_validate(cat))


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
    return APIResponse(status="success", data=CategoryRead.model_validate(cat))


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
