from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin, get_db
from app.db.models.enquiry import Enquiry
from app.db.models.user import User
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.enquiry import EnquiryCreate, EnquiryRead, EnquiryUpdate

router = APIRouter(prefix="/api/v1", tags=["Enquiries"])

STATUSES = ("new", "in_progress", "resolved")


@router.post("/enquiries", response_model=MessageResponse)
def submit_enquiry(req: EnquiryCreate, db: Session = Depends(get_db)):
    """Public Contact Us form."""
    if req.website:
        # Honeypot filled in: answer like a success so bots don't retry, but store nothing
        return MessageResponse(status="success", message="Thank you! Your message has been received.")

    phone = "".join(ch for ch in req.phone if ch.isdigit())
    if len(phone) == 12 and phone.startswith("91"):
        phone = phone[2:]  # drop the +91 country code
    if len(phone) < 10:
        raise HTTPException(status_code=400, detail="Enter a valid mobile number.")

    db.add(Enquiry(
        name=req.name.strip(),
        email=str(req.email).lower().strip(),
        phone=phone,
        message=req.message.strip(),
        status="new",
        source="contact"
    ))
    db.commit()
    return MessageResponse(status="success", message="Thank you! Your message has been received.")


@router.get("/admin/enquiries", response_model=APIResponse[List[EnquiryRead]])
def list_enquiries(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    query = db.query(Enquiry)
    if status and status != "all":
        query = query.filter(Enquiry.status == status)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            Enquiry.name.ilike(term) | Enquiry.email.ilike(term)
            | Enquiry.phone.ilike(term) | Enquiry.message.ilike(term)
        )
    enquiries = query.order_by(Enquiry.created_at.desc(), Enquiry.id.desc()).all()
    return APIResponse(status="success", data=[EnquiryRead.model_validate(e) for e in enquiries])


@router.get("/admin/enquiries/counts", response_model=APIResponse[Dict[str, int]])
def enquiry_counts(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = dict(db.query(Enquiry.status, func.count(Enquiry.id)).group_by(Enquiry.status).all())
    counts = {s: int(rows.get(s, 0)) for s in STATUSES}
    counts["all"] = sum(counts.values())
    return APIResponse(status="success", data=counts)


@router.patch("/admin/enquiries/{enquiry_id}", response_model=APIResponse[EnquiryRead])
def update_enquiry(
    enquiry_id: int,
    req: EnquiryUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    enquiry = db.query(Enquiry).filter(Enquiry.id == enquiry_id).first()
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found.")
    if req.status is not None:
        enquiry.status = req.status
    if "admin_note" in req.model_fields_set:
        enquiry.admin_note = (req.admin_note or "").strip() or None
    db.commit()
    db.refresh(enquiry)
    return APIResponse(status="success", data=EnquiryRead.model_validate(enquiry))


@router.delete("/admin/enquiries/{enquiry_id}", response_model=MessageResponse)
def delete_enquiry(
    enquiry_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    enquiry = db.query(Enquiry).filter(Enquiry.id == enquiry_id).first()
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found.")
    db.delete(enquiry)
    db.commit()
    return MessageResponse(status="success", message="Enquiry deleted.")
