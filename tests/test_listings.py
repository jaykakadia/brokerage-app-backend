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

    # Validation test: invalid owner_role
    invalid_role_res = client.post("/api/v1/listings", data={
        "title": "3 BHK Luxury Builder Floor",
        "location": "Palwal",
        "price": 5000000,
        "owner_name": "John Doe",
        "owner_role": "Broker"
    })
    assert invalid_role_res.status_code == 400
    assert "Invalid owner_role" in invalid_role_res.json()["detail"]

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


def test_listing_form_data_round_trip(client, admin_user):
    """Everything the post-listing wizard puts in form_data must come back unchanged."""
    import json

    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})

    property_form = {
        "kind": "owner",
        "propType": "flat",
        "forWhat": "sale",
        "posterRole": "real_owner",
        "businessName": "Kakadia Builders",
        "mobile": "9876543210",
        "whatsapp": "9123456780",
        "sameAsMobile": False,
        "facebookUrl": "https://facebook.com/kakadia",
        "websiteUrl": "https://kakadia.in/",
        "xUrl": "https://x.com/kakadia",
        "bhk": "3BHK",
        "bath": "2",
        "furnish": "Semi-Furnished",
        "area": "1200",
        "unit": "Sq.Ft",
        "rate": "4,500",
        "amenities": ["Lift", "Power Backup", "Gym"],
        "frontRoad": "Yes",
        "roadWidth": "30",
        "facing": "East",
        "city": "Sonipat",
        "state": "Haryana",
        "price": 5400000
    }
    res = client.post("/api/v1/listings", data={
        "title": "3BHK Flat/Builder Floor/House/Villa for Sale in Sonipat",
        "location": "Sonipat, Haryana",
        "price": 5400000,
        "owner_name": "Jay",
        "owner_role": "Owner",
        "form_data": json.dumps(property_form)
    })
    assert res.status_code == 200, res.text
    listing_id = res.json()["data"]["id"]

    saved = client.get(f"/api/v1/listings/{listing_id}").json()["data"]
    assert saved["form_data"] == property_form
    assert saved["price"] == 5400000

    # Admin edit (PATCH) must not wipe the wizard data
    fd = {"title": "Edited title", "price": "5500000"}
    assert client.patch(f"/api/v1/listings/{listing_id}", data=fd).status_code == 200
    after_edit = client.get(f"/api/v1/listings/{listing_id}").json()["data"]
    assert after_edit["title"] == "Edited title"
    assert after_edit["form_data"] == property_form

    # The full edit form sends form_data back, which replaces the saved wizard data
    edited_form = {**property_form, "bhk": "4BHK", "amenities": ["Lift"]}
    res = client.patch(f"/api/v1/listings/{listing_id}", data={"form_data": json.dumps(edited_form)})
    assert res.status_code == 200
    assert res.json()["data"]["form_data"] == edited_form
    assert client.patch(f"/api/v1/listings/{listing_id}", data={"form_data": "{not json"}).status_code == 400

    business_form = {
        "kind": "business",
        "name": "Kakadia Builders",
        "person": "Jay",
        "mobile": "9876543210",
        "whatsapp": "9876543210",
        "sameAsMobile": True,
        "email": "jay@example.com",
        "facebookUrl": "https://facebook.com/kakadia",
        "websiteUrl": "",
        "xUrl": "",
        "pincode": "131001",
        "city": "Sonipat",
        "state": "Haryana",
        "selectedCategories": [{"id": "1", "name": "Builders"}]
    }
    res = client.post("/api/v1/listings", data={
        "title": "Kakadia Builders",
        "location": "Sonipat",
        "price": 0,
        "owner_name": "Jay",
        "owner_role": "Owner",
        "form_data": json.dumps(business_form)
    })
    assert res.status_code == 200, res.text
    saved = client.get(f"/api/v1/listings/{res.json()['data']['id']}").json()["data"]
    assert saved["form_data"] == business_form


def test_admin_feature_listing(client, test_user, admin_user):
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    listing_id = client.post("/api/v1/listings", data={
        "title": "Shop for rent", "location": "Palwal", "price": 20000, "owner_name": "John Doe"
    }).json()["data"]["id"]

    # Non-admins cannot feature
    assert client.post(f"/api/v1/listings/{listing_id}/feature", json={"days": 7}).status_code == 403

    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    # Pending listings cannot be featured
    assert client.post(f"/api/v1/listings/{listing_id}/feature", json={"days": 7}).status_code == 400

    client.post(f"/api/v1/listings/{listing_id}/status", json={"action": "approve"})
    res = client.post(f"/api/v1/listings/{listing_id}/feature", json={"days": 7})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["is_featured"] is True
    assert data["featured_until"] is not None

    # No days → featured with no expiry
    data = client.post(f"/api/v1/listings/{listing_id}/feature", json={}).json()["data"]
    assert data["is_featured"] is True and data["featured_until"] is None

    assert client.post(f"/api/v1/listings/{listing_id}/feature", json={"days": 0}).status_code == 422

    data = client.post(f"/api/v1/listings/{listing_id}/feature", json={"featured": False}).json()["data"]
    assert data["is_featured"] is False and data["featured_until"] is None
