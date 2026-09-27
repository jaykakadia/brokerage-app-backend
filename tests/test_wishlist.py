import pytest
from app.db.models.listing import Listing


@pytest.fixture
def sample_listing(db_session, test_user):
    listing = Listing(
        user_id=test_user.id,
        title="2 BHK Apartment in Green Park",
        location="Indore, MP",
        price=3500000,
        owner_name="John Doe",
        owner_role="Owner",
        status="approved",
        verified=1
    )
    db_session.add(listing)
    db_session.commit()
    db_session.refresh(listing)
    return listing


def test_wishlist_flow_and_authorization(client, test_user, sample_listing):
    # 1. Unauthenticated access blocked
    res_unauth = client.get("/api/v1/wishlist")
    assert res_unauth.status_code == 401

    res_toggle_unauth = client.post("/api/v1/wishlist/toggle", json={"listing_id": sample_listing.id})
    assert res_toggle_unauth.status_code == 401

    # 2. Log in as test user
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})

    # Check empty wishlist
    init_res = client.get("/api/v1/wishlist?ids_only=true")
    assert init_res.status_code == 200
    assert init_res.json()["ids"] == []

    # 3. Add to wishlist
    add_res = client.post("/api/v1/wishlist/toggle", json={"listing_id": sample_listing.id})
    assert add_res.status_code == 200
    assert add_res.json()["wishlisted"] is True
    assert add_res.json()["listing_id"] == sample_listing.id

    # Verify present in ids_only
    ids_res = client.get("/api/v1/wishlist?ids_only=true")
    assert ids_res.status_code == 200
    assert sample_listing.id in ids_res.json()["ids"]

    # Verify present in full details
    full_res = client.get("/api/v1/wishlist")
    assert full_res.status_code == 200
    assert len(full_res.json()["data"]) == 1
    assert full_res.json()["data"][0]["title"] == "2 BHK Apartment in Green Park"

    # 4. Remove from wishlist (toggle again)
    remove_res = client.post("/api/v1/wishlist/toggle", json={"listing_id": sample_listing.id})
    assert remove_res.status_code == 200
    assert remove_res.json()["wishlisted"] is False

    # Verify empty again
    check_empty = client.get("/api/v1/wishlist?ids_only=true")
    assert check_empty.status_code == 200
    assert sample_listing.id not in check_empty.json()["ids"]

    # 5. Invalid listing 404
    inv_res = client.post("/api/v1/wishlist/toggle", json={"listing_id": 999999})
    assert inv_res.status_code == 404
