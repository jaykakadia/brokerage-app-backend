from app.db.models.listing import Listing
from app.db.models.user import User


def _login(client, user, password):
    client.post("/api/v1/auth/login", json={"email": user.email, "password": password})


def test_reviews_full_lifecycle(client, admin_user, test_user, db_session):
    # 1. Create a listing owned by admin_user
    listing = Listing(
        user_id=admin_user.id,
        title="Apex Realty Solutions",
        location="Sector 12, Faridabad, Haryana",
        price=0.0,
        owner_name="Apex Group",
        owner_role="Agent",
        reference_code="APX001",
        status="approved",
        form_data={"kind": "business", "city": "Faridabad"},
    )
    db_session.add(listing)
    db_session.commit()
    db_session.refresh(listing)

    # 2. Public view of reviews - starts empty
    pub_res = client.get(f"/api/v1/listings/{listing.id}/reviews")
    assert pub_res.status_code == 200
    data = pub_res.json()["data"]
    assert data["total_reviews"] == 0
    assert data["average_rating"] == 0.0
    assert len(data["reviews"]) == 0
    assert data["user_review"] is None

    # 3. Unauthenticated review rejected
    unauth = client.post(
        f"/api/v1/listings/{listing.id}/reviews",
        json={"rating": 5, "comment": "Great experience!"},
    )
    assert unauth.status_code == 401

    # 4. Owner cannot review their own listing
    _login(client, admin_user, "adminpass123")
    owner_rev = client.post(
        f"/api/v1/listings/{listing.id}/reviews",
        json={"rating": 5, "comment": "Self review"},
    )
    assert owner_rev.status_code == 400
    assert "cannot review your own listing" in owner_rev.json()["detail"]

    # 5. Regular registered user submits review
    _login(client, test_user, "password123")
    sub_res = client.post(
        f"/api/v1/listings/{listing.id}/reviews",
        json={"rating": 5, "comment": "Excellent service and transparent deals."},
    )
    assert sub_res.status_code == 200
    review_data = sub_res.json()["data"]
    assert review_data["rating"] == 5
    assert review_data["status"] == "pending"
    assert review_data["comment"] == "Excellent service and transparent deals."

    # 6. Public approved list should still be 0, but test_user sees their pending review in user_review
    check_user_res = client.get(f"/api/v1/listings/{listing.id}/reviews")
    assert check_user_res.status_code == 200
    c_data = check_user_res.json()["data"]
    assert c_data["total_reviews"] == 0  # not approved yet
    assert c_data["user_review"] is not None
    assert c_data["user_review"]["status"] == "pending"

    # 7. Non-admin cannot access admin moderation endpoints
    non_admin_mod = client.get("/api/v1/admin/reviews")
    assert non_admin_mod.status_code == 403

    # 8. Admin reviews list shows the pending review
    _login(client, admin_user, "adminpass123")
    admin_list = client.get("/api/v1/admin/reviews?status=pending")
    assert admin_list.status_code == 200
    admin_reviews = admin_list.json()["data"]
    assert len(admin_reviews) >= 1
    target = next((r for r in admin_reviews if r["id"] == review_data["id"]), None)
    assert target is not None
    assert target["user_name"] == test_user.name
    assert target["rating"] == 5

    # 9. Admin approves the review
    approve_res = client.patch(
        f"/api/v1/admin/reviews/{review_data['id']}/status",
        json={"status": "approved"},
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["data"]["status"] == "approved"

    # 10. Public view now displays approved review with accurate rating & distribution
    pub_res2 = client.get(f"/api/v1/listings/{listing.id}/reviews")
    assert pub_res2.status_code == 200
    data2 = pub_res2.json()["data"]
    assert data2["total_reviews"] == 1
    assert data2["average_rating"] == 5.0
    assert data2["distribution"]["5"] == 1
    assert len(data2["reviews"]) == 1
    assert data2["reviews"][0]["comment"] == "Excellent service and transparent deals."

    # 11. User updates their review
    _login(client, test_user, "password123")
    upd_res = client.post(
        f"/api/v1/listings/{listing.id}/reviews",
        json={"rating": 4, "comment": "Updated review - still very good."},
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["data"]["rating"] == 4

    # 12. User deletes their review
    del_res = client.delete(f"/api/v1/listings/{listing.id}/reviews/me")
    assert del_res.status_code == 200

    pub_res3 = client.get(f"/api/v1/listings/{listing.id}/reviews")
    assert pub_res3.json()["data"]["total_reviews"] == 0
