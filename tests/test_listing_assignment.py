from app.services.auth_service import auth_service


def _listing_data(**extra):
    return {"title": "2 BHK Flat", "location": "Palwal", "price": 100, "owner_name": "Seller", **extra}


def test_admin_assigns_listing_to_existing_user(client, admin_user, test_user):
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    res = client.post("/api/v1/listings", data=_listing_data(assign_to_email=" JOHN@example.com "))
    assert res.status_code == 200
    listing = res.json()["data"]
    assert listing["user_id"] == test_user.id
    assert listing["assigned_email"] is None

    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    mine = client.get(f"/api/v1/listings?user_id={test_user.id}").json()["data"]
    assert [l["id"] for l in mine] == [listing["id"]]


def test_listing_held_until_user_signs_up(client, admin_user):
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    res = client.post("/api/v1/listings", data=_listing_data(assign_to_email="new@example.com"))
    listing = res.json()["data"]
    assert listing["user_id"] == admin_user.id
    assert listing["assigned_email"] == "new@example.com"

    # Hidden from public viewers
    client.post("/api/v1/auth/logout")
    public = client.get(f"/api/v1/listings/{listing['id']}").json()["data"]
    assert public["assigned_email"] is None

    payload = {"name": "New User", "phone": "9000000001", "email": "new@example.com", "password": "securepassword123"}
    payload["otp"] = auth_service.generate_and_store_otp(payload["email"], "register")
    assert client.post("/api/v1/auth/register", json=payload).status_code == 200
    user_id = client.get("/api/v1/auth/me").json()["data"]["id"]

    detail = client.get(f"/api/v1/listings/{listing['id']}").json()["data"]
    assert detail["user_id"] == user_id
    assert detail["assigned_email"] is None


def test_listing_claimed_when_admin_creates_user(client, admin_user):
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    listing = client.post("/api/v1/listings", data=_listing_data(assign_to_email="later@example.com")).json()["data"]
    res = client.post("/api/v1/admin/users", json={
        "name": "Later User", "phone": "9000000002", "email": "later@example.com",
        "password": "securepassword123", "role": "Owner", "status": "active"
    })
    assert res.status_code == 200, res.text
    detail = client.get(f"/api/v1/listings/{listing['id']}").json()["data"]
    assert detail["user_id"] == res.json()["data"]["id"]


def test_admin_reassigns_existing_listing(client, admin_user, test_user):
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    listing = client.post("/api/v1/listings", data=_listing_data()).json()["data"]
    assert listing["user_id"] == admin_user.id
    res = client.patch(f"/api/v1/listings/{listing['id']}", data={"assign_to_email": test_user.email})
    assert res.status_code == 200
    assert res.json()["data"]["user_id"] == test_user.id


def test_non_admin_cannot_assign(client, test_user):
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    res = client.post("/api/v1/listings", data=_listing_data(assign_to_email="other@example.com"))
    assert res.status_code == 403


def test_reassign_to_new_email_removes_old_owner_access(client, admin_user, test_user):
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    listing = client.post("/api/v1/listings", data=_listing_data()).json()["data"]

    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    res = client.patch(f"/api/v1/listings/{listing['id']}", data={"assign_to_email": "someone@example.com"})
    assert res.json()["data"]["user_id"] == admin_user.id

    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    assert client.patch(f"/api/v1/listings/{listing['id']}", data={"title": "Hijacked"}).status_code == 403
    assert client.delete(f"/api/v1/listings/{listing['id']}").status_code == 403


def test_assign_rejects_incomplete_email(client, admin_user):
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    res = client.post("/api/v1/listings", data=_listing_data(assign_to_email="john@"))
    assert res.status_code == 400


def test_wishlist_hides_assigned_email(client, admin_user, test_user):
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    listing = client.post("/api/v1/listings", data=_listing_data(assign_to_email="held@example.com")).json()["data"]

    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    client.post("/api/v1/wishlist/toggle", json={"listing_id": listing["id"]})
    items = client.get("/api/v1/wishlist").json()["data"]
    assert [l["id"] for l in items] == [listing["id"]]
    assert items[0]["assigned_email"] is None
