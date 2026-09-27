"""
Legacy API Compatibility Layer (Phase 1).
Provides thin shims mapping legacy PHP endpoints directly to Phase 1 business logic.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Request, Response, Form, UploadFile, File
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.dependencies import get_current_user, get_current_admin, get_optional_user
from app.db.models.user import User
from app.routers.auth import login as auth_login, register as auth_register, send_otp as auth_send_otp, verify_otp as auth_verify_otp, reset_password as auth_reset_pwd
from app.routers.listings import get_listings as listings_get, get_listing as listing_detail, get_listing_counts as listing_counts, create_listing as listing_create, update_listing_status as listing_update_status, delete_listing as listing_delete
from app.routers.locations import get_cities as loc_cities, get_locations as loc_all, create_location as loc_create, delete_location as loc_delete
from app.routers.categories import get_categories as cat_all, get_category as cat_single, create_or_save_category as cat_save, delete_category as cat_delete
from app.routers.users import list_admin_users as users_all, get_admin_user as user_single, create_or_update_admin_user as user_save, update_user_role as user_role_update, soft_delete_user as user_delete
from app.schemas.auth import LoginRequest, RegisterRequest, SendOtpRequest, VerifyOtpRequest, ResetPasswordRequest
from app.schemas.listing import ListingStatusUpdate
from app.schemas.location import LocationCreate
from app.schemas.category import CategoryCreate
from app.schemas.user import AdminUserCreate, RoleUpdateRequest

router = APIRouter(prefix="/api", tags=["Legacy Compatibility"])


# --- AUTH SHIMS ---
@router.post("/login_user.php")
def legacy_login(
    email: str = Form(...),
    password: str = Form(...),
    response: Response = None,
    db: Session = Depends(get_db)
):
    return auth_login(LoginRequest(email=email, password=password), response, db)


@router.post("/register_user.php")
def legacy_register(
    name: str = Form("User"),
    phone: str = Form("0000000000"),
    email: str = Form(...),
    otp: Optional[str] = Form(None),
    password: Optional[str] = Form("DefaultPass123!"),
    response: Response = None,
    db: Session = Depends(get_db)
):
    req = RegisterRequest(name=name, phone=phone, email=email, password=password or "DefaultPass123!", otp=otp)
    return auth_register(req, response, db)


@router.post("/send_otp.php")
def legacy_send_otp(
    email: str = Form(...),
    action: str = Form("register"),
    name: Optional[str] = Form(None),
    phone: Optional[str] = Form(None)
):
    return auth_send_otp(SendOtpRequest(email=email, action=action, name=name, phone=phone))


@router.post("/verify_otp.php")
def legacy_verify_otp(
    email: str = Form(...),
    otp: str = Form(...)
):
    return auth_verify_otp(VerifyOtpRequest(email=email, otp=otp))


@router.post("/reset_password.php")
def legacy_reset_password(
    email: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db)
):
    return auth_reset_pwd(ResetPasswordRequest(email=email, new_password=new_password), db)


# --- LISTING SHIMS ---
@router.get("/get_listings.php")
def legacy_get_listings(
    status: Optional[str] = "approved",
    city: Optional[str] = None,
    search: Optional[str] = None,
    ref_code: Optional[str] = None,
    ref_name: Optional[str] = None,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    return listings_get(status, city, search, ref_code, ref_name, user, db)


@router.get("/get_listing.php")
def legacy_get_listing(id: int, db: Session = Depends(get_db)):
    return listing_detail(id, db)


@router.get("/get_listing_counts.php")
def legacy_listing_counts(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return listing_counts(admin, db)


@router.post("/save_listing.php")
async def legacy_save_listing(
    title: str = Form(...),
    location: str = Form(...),
    price: float = Form(0.0),
    description: Optional[str] = Form(None),
    owner_name: str = Form("Owner"),
    owner_role: str = Form("Owner"),
    reference_code: Optional[str] = Form(None),
    photos: List[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return await listing_create(
        title=title, location=location, price=price, description=description,
        owner_name=owner_name, owner_role=owner_role, reference_code=reference_code,
        form_data=None, photos=photos, current_user=current_user, db=db
    )


@router.post("/update_status.php")
def legacy_update_status(
    id: int = Form(...),
    action: str = Form(...),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    return listing_update_status(id, ListingStatusUpdate(action=action), admin, db)


@router.post("/delete_listing.php")
def legacy_delete_listing(
    id: int = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return listing_delete(id, current_user, db)


# --- LOCATION SHIMS ---
@router.get("/get_cities.php")
def legacy_get_cities(db: Session = Depends(get_db)):
    return loc_cities(db)


@router.get("/get_locations.php")
def legacy_get_locations(db: Session = Depends(get_db)):
    return loc_all(db)


@router.post("/save_location.php")
def legacy_save_location(
    city_name: str = Form(...),
    state: str = Form("Haryana"),
    category: Optional[str] = Form(None),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    return loc_create(LocationCreate(city_name=city_name, state=state, category=category), admin, db)


@router.post("/delete_location.php")
def legacy_delete_location(id: int = Form(...), admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return loc_delete(id, admin, db)


# --- CATEGORY SHIMS ---
@router.get("/get_categories.php")
def legacy_get_categories(db: Session = Depends(get_db)):
    return cat_all(db)


@router.get("/get_category.php")
def legacy_get_category(id: int, db: Session = Depends(get_db)):
    return cat_single(id, db)


@router.post("/save_category.php")
def legacy_save_category(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    return cat_save(CategoryCreate(name=name, description=description), admin, db)


@router.post("/delete_category.php")
def legacy_delete_category(id: int = Form(...), admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return cat_delete(id, admin, db)


# --- USER SHIMS ---
@router.get("/get_users.php")
def legacy_get_users(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return users_all(None, None, admin, db)


@router.get("/get_user.php")
def legacy_get_user(id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return user_single(id, admin, db)


@router.post("/save_user.php")
def legacy_save_user(
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("Owner"),
    status: str = Form("active"),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    return user_save(AdminUserCreate(name=name, phone=phone, email=email, password=password, role=role, status=status), admin, db)


@router.post("/update_user_role.php")
def legacy_update_user_role(
    id: int = Form(...),
    role: str = Form(...),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    return user_role_update(id, RoleUpdateRequest(role=role), admin, db)


@router.post("/delete_user.php")
def legacy_delete_user(id: int = Form(...), admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return user_delete(id, admin, db)


# --- WISHLIST SHIMS ---
from app.routers.wishlist import get_wishlist as wishlist_get, toggle_wishlist as wishlist_toggle
from app.schemas.wishlist import ToggleWishlistRequest

@router.get("/get_wishlist.php")
def legacy_get_wishlist(
    ids_only: Optional[int] = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return wishlist_get(ids_only=bool(ids_only), current_user=current_user, db=db)


@router.post("/toggle_wishlist.php")
def legacy_toggle_wishlist(
    listing_id: int = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return wishlist_toggle(ToggleWishlistRequest(listing_id=listing_id), current_user=current_user, db=db)


# --- PLANS SHIMS ---
from app.routers.plans import get_plans as plans_get, create_or_save_plan as plan_save, update_plan as plan_update, delete_plan as plan_delete
from app.schemas.plan import PlanCreate, PlanUpdate

@router.get("/get_plans.php")
def legacy_get_plans(
    all: Optional[int] = 0,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    return plans_get(all=bool(all), user=user, db=db)


@router.post("/save_plan.php")
def legacy_save_plan(
    id: Optional[int] = Form(0),
    name: str = Form(...),
    price: float = Form(...),
    listing_limit: int = Form(5),
    duration_days: int = Form(365),
    status: str = Form("active"),
    description: Optional[str] = Form(None),
    sort_order: Optional[int] = Form(0),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if id and id > 0:
        return plan_update(
            id,
            PlanUpdate(
                name=name, price=price, listing_limit=listing_limit,
                leads_count=listing_limit, duration_days=duration_days,
                status=status, description=description, sort_order=sort_order
            ),
            admin, db
        )
    return plan_save(
        PlanCreate(
            name=name, price=price, listing_limit=listing_limit,
            leads_count=listing_limit, duration_days=duration_days,
            status=status, description=description, sort_order=sort_order or 0
        ),
        admin, db
    )


@router.post("/delete_plan.php")
def legacy_delete_plan(
    id: int = Form(...),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    return plan_delete(id, admin, db)


# --- LEADS SHIMS ---
from app.routers.leads import get_lead_status as leads_status, reveal_contact as leads_reveal
from app.schemas.lead import RevealContactRequest

@router.get("/get_lead_status.php")
def legacy_get_lead_status(current_user: User = Depends(get_current_user)):
    return leads_status(current_user=current_user)


@router.post("/reveal_contact.php")
def legacy_reveal_contact(
    listing_id: int = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return leads_reveal(RevealContactRequest(listing_id=listing_id), current_user=current_user, db=db)


# --- RAZORPAY SHIMS ---
from app.routers.payments import create_order as razorpay_create_order, verify_payment as razorpay_verify_payment, get_razorpay_settings as razorpay_get_settings, save_razorpay_settings as razorpay_save_settings
from app.schemas.order import CreateOrderRequest, VerifyPaymentRequest, RazorpaySettingsUpdate

@router.post("/create_razorpay_order.php")
def legacy_create_razorpay_order(
    plan_id: int = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return razorpay_create_order(CreateOrderRequest(plan_id=plan_id), current_user=current_user, db=db)


@router.post("/verify_razorpay_payment.php")
def legacy_verify_razorpay_payment(
    razorpay_order_id: str = Form(...),
    razorpay_payment_id: str = Form(...),
    razorpay_signature: str = Form(...),
    plan_id: Optional[int] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return razorpay_verify_payment(
        VerifyPaymentRequest(
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
            plan_id=plan_id
        ),
        current_user=current_user,
        db=db
    )


@router.get("/save_razorpay_settings.php")
def legacy_get_razorpay_settings(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return razorpay_get_settings(admin=admin, db=db)


@router.post("/save_razorpay_settings.php")
def legacy_save_razorpay_settings(
    razorpay_key_id: str = Form(...),
    razorpay_key_secret: Optional[str] = Form(None),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    return razorpay_save_settings(
        RazorpaySettingsUpdate(razorpay_key_id=razorpay_key_id, razorpay_key_secret=razorpay_key_secret),
        admin=admin,
        db=db
    )
