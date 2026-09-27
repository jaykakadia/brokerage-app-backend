import pytest
from app.db.models.listing import Listing
from app.db.models.user import User


@pytest.fixture
def owner_and_listing(db_session):
    owner = User(
        name="Property Owner Bob",
        phone="9876500000",
        email="bob_owner@example.com",
        password_hash="fakehash",
        role="Owner",
        status="active"
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    listing = Listing(
        user_id=owner.id,
        title="Commercial Showroom on Ring Road",
        location="Indore",
        price=12000000,
        owner_name=owner.name,
        owner_role="Owner",
        status="approved",
        verified=1
    )
    db_session.add(listing)
    db_session.commit()
    db_session.refresh(listing)
    return owner, listing


def test_lead_reveal_and_balance_deduction(client, test_user, owner_and_listing, db_session):
    owner, listing = owner_and_listing

    # Log in as test user
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})

    # 1. Lead status check (initially 0 balance)
    st_res = client.get("/api/v1/leads/status")
    assert st_res.status_code == 200
    assert st_res.json()["leads_balance"] == 0

    # 2. Attempt reveal with 0 balance -> returns no_leads
    rev_fail = client.post("/api/v1/leads/reveal", json={"listing_id": listing.id})
    assert rev_fail.status_code == 200
    assert rev_fail.json()["status"] == "error"
    assert rev_fail.json()["code"] == "no_leads"

    # 3. Credit user with 1 lead for testing atomic deduction
    test_user.leads_balance = 1
    db_session.commit()

    # 4. Successful reveal
    rev_ok = client.post("/api/v1/leads/reveal", json={"listing_id": listing.id})
    assert rev_ok.status_code == 200
    res_data = rev_ok.json()
    assert res_data["status"] == "success"
    assert res_data["already_revealed"] is False
    assert res_data["contact"]["mobile"] == "9876500000"
    assert res_data["plan"]["leads_remaining"] == 0
    assert res_data["plan"]["leads_used"] == 1

    # 5. Duplicate reveal idempotency: same user viewing same listing again
    # Balance is now 0, but user ALREADY revealed this listing, so it MUST succeed without deducting or blocking!
    dup_res = client.post("/api/v1/leads/reveal", json={"listing_id": listing.id})
    assert dup_res.status_code == 200
    assert dup_res.json()["status"] == "success"
    assert dup_res.json()["already_revealed"] is True
    assert dup_res.json()["contact"]["mobile"] == "9876500000"
    assert dup_res.json()["plan"]["leads_remaining"] == 0

    # 6. Negative balance prevention: viewing a DIFFERENT listing with 0 balance fails
    listing2 = Listing(
        user_id=owner.id,
        title="Another Plot in Silicon City",
        location="Indore",
        price=4000000,
        owner_name=owner.name,
        owner_role="Owner",
        status="approved",
        verified=1
    )
    db_session.add(listing2)
    db_session.commit()

    rev_fail2 = client.post("/api/v1/leads/reveal", json={"listing_id": listing2.id})
    assert rev_fail2.status_code == 200
    assert rev_fail2.json()["code"] == "no_leads"
