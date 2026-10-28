from app.services.mail_service import mail_service


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
    mail_service.sent_emails.clear()
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

    # Verify listing confirmation email dispatched to user
    confirmation_emails = [m for m in mail_service.sent_emails if m["to"] == test_user.email and f"#{listing_id}" in m["subject"]]
    assert len(confirmation_emails) >= 1
    confirm_mail = confirmation_emails[-1]
    assert "Listing Confirmation" in confirm_mail["subject"]
    assert "3 BHK Luxury Builder Floor in Sector 2" in confirm_mail["html"]
    assert "Palwal, Haryana" in confirm_mail["html"]
    assert "Pending Review" in confirm_mail["html"]

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


def test_search_listings_by_user_details(client, test_user, admin_user):
    """Admin and users can search listings by user name, email, phone number, and listing ID."""
    # test_user has name, email, phone
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    res = client.post("/api/v1/listings", data={
        "title": "Unique Luxury Penthouse in Cyber City",
        "location": "Gurugram, Haryana",
        "price": 12000000,
        "owner_name": test_user.name,
        "owner_role": "Owner"
    })
    assert res.status_code == 200
    listing_id = res.json()["data"]["id"]

    # Login as admin to approve
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    client.post(f"/api/v1/listings/{listing_id}/status", json={"action": "approve"})

    # Search by user name
    s_name = client.get(f"/api/v1/listings?search={test_user.name}").json()["data"]
    assert any(l["id"] == listing_id for l in s_name)

    # Search by user email
    s_email = client.get(f"/api/v1/listings?search={test_user.email}").json()["data"]
    assert any(l["id"] == listing_id for l in s_email)

    # Search by user phone
    s_phone = client.get(f"/api/v1/listings?search={test_user.phone}").json()["data"]
    assert any(l["id"] == listing_id for l in s_phone)

    # Search by numeric listing ID
    s_id = client.get(f"/api/v1/listings?search={listing_id}").json()["data"]
    assert any(l["id"] == listing_id for l in s_id)

    # Search by formatted ID (#123, TC-123)
    s_fmt = client.get(f"/api/v1/listings?search=#{listing_id}").json()["data"]
    assert any(l["id"] == listing_id for l in s_fmt)


def test_listings_pagination_caching_and_card_fields(client, admin_user, test_user):
    """Verify pagination, lightweight card fields, and in-memory cache behavior."""
    import json
    from app.routers.listings import public_listings_cache

    # 1. Clear cache upfront
    public_listings_cache.clear()

    # Create 3 approved listings
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    ids = []
    for i in range(1, 4):
        create_res = client.post("/api/v1/listings", data={
            "title": f"Apartment #{i} in Palwal City",
            "location": f"Sector {i}, Palwal, Haryana",
            "price": 1000000 * i,
            "owner_name": f"Owner {i}",
            "owner_role": "Owner",
            "form_data": json.dumps({"kind": "property", "propType": "flat", "city": "Palwal"})
        })
        assert create_res.status_code == 200
        l_id = create_res.json()["data"]["id"]
        # Approve each
        client.post(f"/api/v1/listings/{l_id}/status", json={"action": "approve"})
        ids.append(l_id)

    # Logout so we are an unauthenticated public user
    client.post("/api/v1/auth/logout")

    # 2. Test pagination: page=1, limit=2
    res_p1 = client.get("/api/v1/listings?status=approved&page=1&limit=2")
    assert res_p1.status_code == 200
    p1_data = res_p1.json()
    assert p1_data["status"] == "success"
    assert p1_data["total"] >= 3
    assert p1_data["page"] == 1
    assert p1_data["limit"] == 2
    assert p1_data["total_pages"] >= 2
    assert len(p1_data["data"]) == 2

    # 3. Test card fields (Requirement 3: no form_data, no locked contact details, only card fields)
    card_item = p1_data["data"][0]
    assert "id" in card_item
    assert "title" in card_item
    assert "price" in card_item
    assert "city" in card_item
    assert "first_image_url" in card_item
    assert "image_url" in card_item
    assert "prop_type" in card_item
    assert "verified" in card_item
    assert "is_featured" in card_item
    # Must NOT have raw form_data in list response
    assert card_item.get("form_data") is None
    # Must NOT leak assigned_email to public viewer
    assert card_item.get("assigned_email") is None

    # Detail endpoint MUST have full form_data and details (Requirement 7)
    detail_res = client.get(f"/api/v1/listings/{ids[0]}")
    assert detail_res.status_code == 200
    assert detail_res.json()["data"]["form_data"] is not None

    # 4. Test in-memory cache (Requirement 4)
    # The first call should have populated the cache
    cached_entry = public_listings_cache.get("st=approved&p=1&l=2&c=None&s=None&k=None&rc=None&rn=None&pt=None&d=None&min=None&max=None&vo=None&no=None&f=None")
    assert cached_entry is not None
    assert cached_entry["page"] == 1

    # Calling again gets the exact cached data
    res_p1_cached = client.get("/api/v1/listings?status=approved&page=1&limit=2")
    assert res_p1_cached.json() == cached_entry

    # 5. Cache invalidation on admin approval / status update
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    client.post(f"/api/v1/listings/{ids[0]}/status", json={"action": "suspended"})
    # Cache must be cleared immediately
    assert public_listings_cache.get("st=approved&p=1&l=2&c=None&s=None&k=None&rc=None&rn=None&pt=None&d=None&min=None&max=None&vo=None&no=None&f=None") is None


def test_business_directory_public_mobile_and_no_email_leak(client, test_user, admin_user):
    """
    Test business listings disclose mobile publicly without lead deduction,
    never leak email to public viewers (in card, detail or description),
    property listings keep contacts locked for anonymous users,
    and owner/admin continue to receive full email.
    """
    import json

    # 1. Admin creates an approved business listing with contact details
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    biz_email = "business_owner_secret@example.com"
    biz_mobile = "9876543210"
    biz_desc = f"Business listing\r\nCategories: Real Estate Consultant\r\nAddress: Sector 14, Gurgaon\r\nContact: Test Business Owner / {biz_mobile} / {biz_email}\r\nWhatsApp: {biz_mobile}"
    
    biz_form_data = {
        "kind": "business",
        "name": "Super Realty Business",
        "person": "Test Business Owner",
        "mobile": biz_mobile,
        "email": biz_email,
        "whatsapp": biz_mobile,
        "categoryName": "Real Estate Consultant, Property Dealer",
        "city": "Gurgaon"
    }

    res_create_biz = client.post("/api/v1/listings", data={
        "title": "Super Realty Business",
        "location": "Sector 14, Gurgaon",
        "price": 0,
        "description": biz_desc,
        "owner_name": "Test Business Owner",
        "owner_role": "Owner",
        "form_data": json.dumps(biz_form_data)
    })
    assert res_create_biz.status_code == 200
    biz_id = res_create_biz.json()["data"]["id"]

    # Approve business listing
    client.post(f"/api/v1/listings/{biz_id}/status", json={"action": "approved"})

    # Admin creates an approved property listing with contact details
    prop_mobile = "9123456780"
    prop_email = "property_owner_secret@example.com"
    prop_form_data = {
        "kind": "owner",
        "propType": "flat",
        "bhk": "2 BHK",
        "mobile": prop_mobile,
        "email": prop_email,
        "whatsapp": prop_mobile,
        "city": "Gurgaon"
    }
    res_create_prop = client.post("/api/v1/listings", data={
        "title": "2 BHK Apartment for Sale in Sector 14",
        "location": "Sector 14, Gurgaon",
        "price": 6000000,
        "description": "Lovely apartment with park view.",
        "owner_name": "Property Seller",
        "owner_role": "Owner",
        "form_data": json.dumps(prop_form_data)
    })
    assert res_create_prop.status_code == 200
    prop_id = res_create_prop.json()["data"]["id"]
    client.post(f"/api/v1/listings/{prop_id}/status", json={"action": "approved"})

    # 2. Log out -> Anonymous client
    client.post("/api/v1/auth/logout")

    # A. Anonymous GET business card (/api/v1/listings?kind=business)
    card_res = client.get("/api/v1/listings?kind=business&status=approved")
    assert card_res.status_code == 200
    card_json_text = card_res.text
    biz_cards = [c for c in card_res.json()["data"] if c["id"] == biz_id]
    assert len(biz_cards) == 1
    assert biz_cards[0]["mobile"] == biz_mobile
    # Must NOT contain business email anywhere in the card JSON response
    assert biz_email not in card_json_text
    assert "@" not in biz_cards[0].get("assigned_email", "") if biz_cards[0].get("assigned_email") else True

    # B. Anonymous GET business detail (/api/v1/listings/{biz_id})
    detail_res = client.get(f"/api/v1/listings/{biz_id}")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()["data"]
    # Mobile must be present
    assert detail_data["mobile"] == biz_mobile
    assert detail_data["form_data"]["mobile"] == biz_mobile
    # Email must NOT be in form_data
    assert "email" not in detail_data["form_data"]
    # Email must NOT leak in description
    assert biz_email not in detail_data["description"]
    assert detail_data.get("assigned_email") is None
    # Whole JSON response body text must not contain the email
    assert biz_email not in detail_res.text

    # C. Anonymous GET property card and detail -> Mobile and email MUST be hidden/locked
    prop_card_res = client.get("/api/v1/listings?kind=property&status=approved")
    assert prop_card_res.status_code == 200
    prop_cards = [c for c in prop_card_res.json()["data"] if c["id"] == prop_id]
    assert len(prop_cards) == 1
    assert prop_cards[0].get("mobile") is None
    assert prop_email not in prop_card_res.text

    prop_detail_res = client.get(f"/api/v1/listings/{prop_id}")
    assert prop_detail_res.status_code == 200
    prop_detail_data = prop_detail_res.json()["data"]
    assert prop_detail_data.get("mobile") is None
    assert "mobile" not in prop_detail_data["form_data"]
    assert "email" not in prop_detail_data["form_data"]
    assert prop_email not in prop_detail_res.text

    # D. Admin login -> Admin gets full email
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    admin_biz_res = client.get(f"/api/v1/listings/{biz_id}")
    assert admin_biz_res.status_code == 200
    assert admin_biz_res.json()["data"]["form_data"]["email"] == biz_email



