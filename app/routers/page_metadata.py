from typing import List, Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin, get_db
from app.db.models.page_metadata import PageMetadata
from app.db.models.user import User
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.page_metadata import PageMetadataRead, PageMetadataCreate, PageMetadataUpdate

router = APIRouter(tags=["Page Metadata"])


def normalize_path(raw: str) -> str:
    """
    Cleans up any user-provided URL or path into a canonical route path:
    e.g. 'https://tradecall.in/properties/palwal/' -> '/properties/palwal'
    'about' -> '/about'
    '/' -> '/'
    """
    cleaned = raw.strip()
    if not cleaned:
        return "/"
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        parsed = urlparse(cleaned)
        cleaned = parsed.path or "/"
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    # remove trailing slash unless it's root
    if len(cleaned) > 1 and cleaned.endswith("/"):
        cleaned = cleaned.rstrip("/")
    return cleaned.lower()


# --- PUBLIC ENDPOINTS ---

@router.get("/api/v1/metadata", response_model=APIResponse[List[PageMetadataRead]])
def get_all_metadata(db: Session = Depends(get_db)):
    """Public endpoint to fetch all configured page metadata mappings."""
    items = db.query(PageMetadata).order_by(PageMetadata.path.asc()).all()
    return APIResponse(status="success", data=[PageMetadataRead.model_validate(item) for item in items])


@router.get("/api/v1/metadata/resolve", response_model=APIResponse[Optional[PageMetadataRead]])
def resolve_page_metadata(path: str = Query(..., description="URL path to check, e.g. /properties/palwal"), db: Session = Depends(get_db)):
    """Public endpoint to fetch metadata for a single specific page URL path."""
    normalized = normalize_path(path)
    item = db.query(PageMetadata).filter(PageMetadata.path == normalized).first()
    if not item:
        return APIResponse(status="success", data=None)
    return APIResponse(status="success", data=PageMetadataRead.model_validate(item))


# --- ADMIN ENDPOINTS ---

@router.get("/api/v1/admin/metadata", response_model=APIResponse[List[PageMetadataRead]])
def admin_get_metadata(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    items = db.query(PageMetadata).order_by(PageMetadata.path.asc()).all()
    return APIResponse(status="success", data=[PageMetadataRead.model_validate(item) for item in items])


@router.post("/api/v1/admin/metadata", response_model=APIResponse[PageMetadataRead], status_code=status.HTTP_201_CREATED)
def admin_create_metadata(
    req: PageMetadataCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    clean_path = normalize_path(req.path)
    clean_title = req.meta_title.strip()
    clean_desc = req.meta_description.strip()

    if not clean_title:
        raise HTTPException(status_code=400, detail="Meta Name/Title cannot be empty.")
    if not clean_desc:
        raise HTTPException(status_code=400, detail="Meta Description cannot be empty.")

    existing = db.query(PageMetadata).filter(PageMetadata.path == clean_path).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Metadata for path '{clean_path}' already exists (ID #{existing.id}). Please edit it instead."
        )

    entry = PageMetadata(
        path=clean_path,
        meta_title=clean_title,
        meta_description=clean_desc,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return APIResponse(status="success", data=PageMetadataRead.model_validate(entry))


@router.put("/api/v1/admin/metadata/{item_id}", response_model=APIResponse[PageMetadataRead])
def admin_update_metadata(
    item_id: int,
    req: PageMetadataUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    entry = db.query(PageMetadata).filter(PageMetadata.id == item_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Page metadata not found.")

    if req.path is not None:
        clean_path = normalize_path(req.path)
        existing = db.query(PageMetadata).filter(PageMetadata.path == clean_path, PageMetadata.id != item_id).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Path '{clean_path}' is already used by entry #{existing.id}.")
        entry.path = clean_path

    if req.meta_title is not None:
        clean_title = req.meta_title.strip()
        if not clean_title:
            raise HTTPException(status_code=400, detail="Meta Name/Title cannot be empty.")
        entry.meta_title = clean_title

    if req.meta_description is not None:
        clean_desc = req.meta_description.strip()
        if not clean_desc:
            raise HTTPException(status_code=400, detail="Meta Description cannot be empty.")
        entry.meta_description = clean_desc

    db.commit()
    db.refresh(entry)
    return APIResponse(status="success", data=PageMetadataRead.model_validate(entry))


@router.delete("/api/v1/admin/metadata/{item_id}", response_model=MessageResponse)
def admin_delete_metadata(
    item_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    entry = db.query(PageMetadata).filter(PageMetadata.id == item_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Page metadata not found.")

    db.delete(entry)
    db.commit()
    return MessageResponse(status="success", message="Page metadata deleted successfully.")
