from app.services.auth_service import auth_service
import io
from PIL import Image
import pytest
from app.db.models.user import User
from app.core.security import hash_password


def test_complete_phase1_flow(client, admin_user):
    """
    Complete Phase 1 Flow Verification:
    1. Register user A
    2. Authenticated cookie issued
    3. Login user A
    4. Create listing with image upload
    5. Listing saved in 'pending' state
    6. Verify not visible in public feed
    7. Admin login
    8. Admin sees listing
    9. Admin approves listing
    10. Public listing becomes visible
    11. Listing detail loads with images
    12. User A edits own listing
    13. Unauthorized user B tries to modify user A's listing (403 forbidden)
    14. Unauthorized user B tries to delete user A's listing (403 forbidden)
    15. User logs out and cookie is cleared (401 unauthorized on protected endpoint)
    """

    # --- Step 1: Register User A ---
    reg_data = {
        "name": "Alice Wonder",
        "phone": "9811223344",
        "email": "alice@example.com",
        "password": "alicePassword123"
    }
    reg_data["otp"] = auth_service.generate_and_store_otp(reg_data["email"], "register")
    reg_resp = client.post("/api/v1/auth/register", json=reg_data)
    assert reg_resp.status_code == 200, f"Register failed: {reg_resp.text}"
    assert "access_token" in client.cookies
    user_a_id = reg_resp.json()["user"]["id"]

    # --- Step 2 & 3: Login User A ---
    # Clear cookies first to simulate fresh login
    client.cookies.clear()
    login_resp = client.post("/api/v1/auth/login", json={
        "email": "alice@example.com",
        "password": "alicePassword123"
    })
    assert login_resp.status_code == 200
    assert "access_token" in client.cookies
    auth_cookie = client.cookies.get("access_token")
    assert auth_cookie is not None

    # Check authenticated identity
    me_resp = client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["email"] == "alice@example.com"

    # --- Step 4: Create Listing with Image Upload ---
    # Uploads are decoded and re-encoded, so this must be a real image
    jpeg_buf = io.BytesIO()
    Image.new("RGB", (64, 48), (12, 98, 83)).save(jpeg_buf, "JPEG")
    valid_jpeg_bytes = jpeg_buf.getvalue()
    listing_payload = {
        "title": "Spacious 3 BHK Apartment in Sector 12",
        "location": "Faridabad, Haryana",
        "price": "6500000",
        "description": "Prime location with balcony, parking, and gym facilities.",
        "owner_name": "Alice Wonder",
        "owner_role": "Owner",
        "reference_code": "REF-ALICE-01"
    }
    files = [
        ("photos", ("living_room.jpg", io.BytesIO(valid_jpeg_bytes), "image/jpeg")),
        ("photos", ("bedroom.jpg", io.BytesIO(valid_jpeg_bytes), "image/jpeg"))
    ]

    create_resp = client.post("/api/v1/listings", data=listing_payload, files=files)
    assert create_resp.status_code == 200, f"Create listing failed: {create_resp.text}"
    listing_data = create_resp.json()["data"]
    listing_id = listing_data["id"]

    # --- Step 5: Listing Saved in 'pending' State ---
    assert listing_data["status"] == "pending"
    assert listing_data["user_id"] == user_a_id
    assert len(listing_data["images"]) == 2
    assert listing_data["images"][0]["file_path"].startswith("/uploads/listings/")

    # --- Step 6: Verify NOT Visible in Public Feed ---
    public_resp_1 = client.get("/api/v1/listings?status=approved")
    assert public_resp_1.status_code == 200
    public_ids_1 = [item["id"] for item in public_resp_1.json()["data"]]
    assert listing_id not in public_ids_1

    # --- Step 7: Admin Login ---
    client.cookies.clear()
    admin_login_resp = client.post("/api/v1/auth/login", json={
        "email": admin_user.email,
        "password": "adminpass123"
    })
    assert admin_login_resp.status_code == 200
    assert admin_login_resp.json()["user"]["role"] == "Admin"

    # --- Step 8: Admin Sees Listing in All Listings & Counts ---
    admin_listings_resp = client.get("/api/v1/listings?status=all")
    assert admin_listings_resp.status_code == 200
    admin_ids = [item["id"] for item in admin_listings_resp.json()["data"]]
    assert listing_id in admin_ids

    counts_resp = client.get("/api/v1/listings/counts")
    assert counts_resp.status_code == 200
    assert counts_resp.json()["data"]["pending"] >= 1

    # --- Step 9: Admin Approves Listing ---
    approve_resp = client.post(f"/api/v1/listings/{listing_id}/status", json={"action": "approve"})
    assert approve_resp.status_code == 200

    # --- Step 10: Public Listing Becomes Visible ---
    client.cookies.clear()  # Browse as unauthenticated guest
    public_resp_2 = client.get("/api/v1/listings?status=approved")
    assert public_resp_2.status_code == 200
    public_ids_2 = [item["id"] for item in public_resp_2.json()["data"]]
    assert listing_id in public_ids_2

    # --- Step 11: Listing Detail Loads ---
    detail_resp = client.get(f"/api/v1/listings/{listing_id}")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert detail_data["id"] == listing_id
    assert detail_data["title"] == "Spacious 3 BHK Apartment in Sector 12"
    assert detail_data["status"] == "approved"
    assert len(detail_data["images"]) == 2

    # --- Step 12: User A Can Edit Their Own Listing ---
    client.post("/api/v1/auth/login", json={
        "email": "alice@example.com",
        "password": "alicePassword123"
    })
    edit_resp = client.patch(f"/api/v1/listings/{listing_id}", data={
        "title": "Renovated 3 BHK Apartment in Sector 12",
        "price": "6700000"
    })
    assert edit_resp.status_code == 200
    assert edit_resp.json()["data"]["title"] == "Renovated 3 BHK Apartment in Sector 12"
    assert float(edit_resp.json()["data"]["price"]) == 6700000.0

    # --- Step 13: Unauthorized User B Cannot Modify User A's Listing ---
    client.cookies.clear()
    reg_b = client.post("/api/v1/auth/register", json={
        "name": "Bob Intruder",
        "phone": "9700112233",
        "email": "bob@example.com",
        "password": "bobPassword123",
        "otp": auth_service.generate_and_store_otp("bob@example.com", "register")
    })
    assert reg_b.status_code == 200

    # Bob tries to edit Alice's listing
    unauthorized_edit = client.patch(f"/api/v1/listings/{listing_id}", data={
        "title": "Hacked Title By Bob"
    })
    assert unauthorized_edit.status_code == 403
    assert "Not authorized" in unauthorized_edit.json()["detail"]

    # --- Step 14: Unauthorized User B Cannot Delete User A's Listing ---
    unauthorized_delete = client.delete(f"/api/v1/listings/{listing_id}")
    assert unauthorized_delete.status_code == 403
    assert "Not authorized" in unauthorized_delete.json()["detail"]

    # Bob tries to change listing status (Admin endpoint)
    unauthorized_status = client.post(f"/api/v1/listings/{listing_id}/status", json={"action": "suspended"})
    assert unauthorized_status.status_code == 403
    assert "Admin privileges required" in unauthorized_status.json()["detail"]

    # Verify listing is still intact and unchanged
    verify_intact = client.get(f"/api/v1/listings/{listing_id}")
    assert verify_intact.status_code == 200
    assert verify_intact.json()["data"]["title"] == "Renovated 3 BHK Apartment in Sector 12"

    # --- Step 15: Logout & Cookie Invalidation ---
    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200
    # Starlette TestClient drops deleted cookies
    assert client.cookies.get("access_token") is None or client.cookies.get("access_token") == ""

    # Check unauthenticated
    after_logout_me = client.get("/api/v1/auth/me")
    assert after_logout_me.status_code == 401
