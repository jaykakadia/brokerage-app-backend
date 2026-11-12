"""Locality pages (/palwal/omaxe-city) are indexable only for real place names with enough listings."""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.cities import is_indexable_locality_slug
from app.db.models.listing import Listing
from app.db.models.user import User


def test_address_style_slugs_are_not_indexable():
    assert is_indexable_locality_slug("omaxe-city-phase-ii")
    assert is_indexable_locality_slug("nit-5")
    assert not is_indexable_locality_slug("anywhere-in-palwal")
    assert not is_indexable_locality_slug("near-mvn-girls-school")
    assert not is_indexable_locality_slug("radhey-shyam-colony-behind-vardan-nursing-home")
    assert not is_indexable_locality_slug("")


def _seed(db: Session) -> None:
    user = User(email="locality_test@tradecall.in", password_hash="x", name="Owner", phone="9999999982", role="owner", status="active")
    db.add(user)
    db.commit()
    db.refresh(user)
    for locality, count in (("Omaxe City", 3), ("Hari Nagar", 2), ("Near MVN School", 3)):
        for _ in range(count):
            db.add(Listing(
                user_id=user.id, title=f"Plot for Sale in {locality}, Palwal", location=f"{locality}, Palwal, Haryana",
                price=1500000, owner_name="Owner", status="approved",
                form_data={"kind": "owner", "city": "Palwal", "locality": locality, "propType": "plot", "plotArea": "100", "plotUnit": "Sq.Yd"},
            ))
    db.commit()


def test_locality_page_robots_and_sitemap(client: TestClient, db_session: Session):
    _seed(db_session)

    assert 'content="index, follow"' in client.get("/palwal/omaxe-city").text
    # Two listings: thin
    assert 'content="noindex, follow"' in client.get("/palwal/hari-nagar").text
    # Enough listings but it is an address, not a place name
    assert 'content="noindex, follow"' in client.get("/palwal/near-mvn-school").text

    sitemap = client.get("/sitemap-hubs.xml").text
    assert "/palwal/omaxe-city<" in sitemap
    assert "/palwal/hari-nagar<" not in sitemap
    assert "/palwal/near-mvn-school<" not in sitemap
