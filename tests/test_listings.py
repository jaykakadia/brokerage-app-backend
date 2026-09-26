def test_listings_flow(client, test_user, admin_user):
    # 1. Log in as user and create listing
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    
    # Validation test: title > 50 words
    long_title = "word " * 55
    invalid_res = client.post("/api/v1/listings", data={
        "title": long_title,
        "location": "Palwal",
        "price": 5000000,
        "owner_name": "John Doe",
        "owner_role": "Owner"
    })
    assert invalid_res.status_code == 400
    assert "cannot exceed 50 words" in invalid_res.json()["detail"]

    # Valid listing creation
    create_res = client.post("/api/v1/listings", data={
        "title": "3 BHK Luxury Builder Floor in Sector 2",
        "location": "Palwal, Haryana",
        "price": 4500000,
        "description": "Spacious flat with modular kitchen and lift.",
        "owner_name": "John Doe",
        "owner_role": "Owner",
        "reference_code": "PAL001"
    })
    assert create_res.status_code == 200
    listing = create_res.json()["data"]
    listing_id = listing["id"]
    assert listing["status"] == "pending"  # User listings start in pending

    # 2. Public listings only show approved
    public_res = client.get("/api/v1/listings?status=approved")
    assert public_res.status_code == 200
    assert not any(l["id"] == listing_id for l in public_res.json()["data"])

    # 3. Listing detail is accessible
    detail_res = client.get(f"/api/v1/listings/{listing_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["data"]["title"] == "3 BHK Luxury Builder Floor in Sector 2"

    # 4. Admin updates status to approved and verified stamp
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    approve_res = client.post(f"/api/v1/listings/{listing_id}/status", json={"action": "approve"})
    assert approve_res.status_code == 200

    stamp_res = client.post(f"/api/v1/listings/{listing_id}/status", json={"action": "stamp"})
    assert stamp_res.status_code == 200

    # Verify listing is now in public approved feed
    public_res2 = client.get("/api/v1/listings?status=approved")
    assert any(l["id"] == listing_id for l in public_res2.json()["data"])

    # Admin counts check
    counts_res = client.get("/api/v1/listings/counts")
    assert counts_res.status_code == 200
    assert counts_res.json()["data"]["approved"] >= 1

    # 5. Delete listing
    del_res = client.delete(f"/api/v1/listings/{listing_id}")
    assert del_res.status_code == 200
