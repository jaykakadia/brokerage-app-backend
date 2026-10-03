from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.db.models.user import User
from app.db.models.listing import Listing
from app.db.models.lead import LeadReveal
from app.schemas.lead import LeadStatusResponse, RevealContactRequest, RevealContactResponse

router = APIRouter(prefix="/api/v1/leads", tags=["Leads"])


@router.get("/status", response_model=LeadStatusResponse)
def get_lead_status(
    current_user: User = Depends(get_current_user)
):
    """Returns current user's lead balance and consumption stats."""
    return LeadStatusResponse(
        status="success",
        leads_balance=current_user.leads_balance,
        leads_used=current_user.leads_used,
        plan_id=current_user.plan_id,
        plan_expires_at=current_user.plan_expires_at
    )


@router.post("/reveal", response_model=dict)
def reveal_contact(
    req: RevealContactRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Atomically reveals listing contact information:
    - If user already revealed this listing, returns contact without deducting leads.
    - If new reveal, locks user row, verifies positive balance, decrements exactly 1 lead,
      records reveal in lead_reveals audit table, and commits atomically.
    """
    listing = db.query(Listing).filter(Listing.id == req.listing_id).first()
    if not listing or listing.status in ["deleted", "suspended"]:
        raise HTTPException(status_code=404, detail="Listing is no longer available.")

    # Fetch listing owner user record for phone/email
    owner = db.query(User).filter(User.id == listing.user_id).first()
    owner_phone = owner.phone if owner else "Not available"
    owner_email = owner.email if owner else ""

    form_data = listing.form_data if isinstance(listing.form_data, dict) else {}

    def form_value(key: str) -> str:
        value = form_data.get(key)
        return value.strip() if isinstance(value, str) else ""

    # The contact the poster entered on the listing, falling back to their account details
    mobile = form_value("mobile") or owner_phone
    contact_data = {
        "person": form_value("person") or listing.owner_name or (owner.name if owner else "Property Owner"),
        "mobile": mobile,
        "whatsapp": form_value("whatsapp") or mobile,
        "email": form_value("email") or owner_email
    }
    # Social links stay hidden on the listing until the contact is unlocked
    links = {
        name: form_data.get(key) for name, key in (
            ("website", "websiteUrl"), ("facebook", "facebookUrl"), ("x", "xUrl"), ("youtube", "youtubeUrl")
        ) if isinstance(form_data.get(key), str) and form_data.get(key).strip()
    }

    # 1. Idempotency Check: Already revealed by this user?
    existing_reveal = db.query(LeadReveal).filter(
        LeadReveal.user_id == current_user.id,
        LeadReveal.listing_id == listing.id
    ).first()

    if existing_reveal:
        return {
            "status": "success",
            "already_revealed": True,
            "contact": contact_data,
            "links": links,
            "plan": {
                "leads_remaining": current_user.leads_balance,
                "leads_used": current_user.leads_used,
                "leads_total": current_user.leads_balance + current_user.leads_used
            }
        }

    # 2. Atomic deduction with row locking
    # Lock the user record to prevent concurrent double-spending
    locked_user = (
        db.query(User)
        .filter(User.id == current_user.id)
        .with_for_update()
        .first()
    )

    if not locked_user or locked_user.leads_balance <= 0:
        return {
            "status": "error",
            "code": "no_leads",
            "message": "Your lead limit is over. Choose a plan to continue viewing contacts."
        }

    # Deduct exactly 1 lead
    locked_user.leads_balance -= 1
    locked_user.leads_used += 1

    # Record reveal audit
    new_reveal = LeadReveal(
        user_id=locked_user.id,
        listing_id=listing.id,
        owner_name_revealed=contact_data["person"],
        owner_phone_revealed=contact_data["mobile"],
        owner_email_revealed=contact_data["email"]
    )
    db.add(new_reveal)
    db.commit()
    db.refresh(locked_user)

    return {
        "status": "success",
        "already_revealed": False,
        "contact": contact_data,
        "links": links,
        "plan": {
            "leads_remaining": locked_user.leads_balance,
            "leads_used": locked_user.leads_used,
            "leads_total": locked_user.leads_balance + locked_user.leads_used
        }
    }
