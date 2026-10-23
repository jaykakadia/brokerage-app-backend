import re
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models.user import User
from app.db.models.listing import Listing
from app.db.models.blog import Blog
from scripts.seed_blog_guides import GUIDES


def test_privacy_and_terms_aliases_redirect(client: TestClient):
    """Alias URLs /privacy-policy and /terms must 301 redirect to canonical URLs."""
    res1 = client.get("/privacy-policy", follow_redirects=False)
    assert res1.status_code == 301
    assert res1.headers.get("location") == "https://tradecall.in/privacy"

    res2 = client.get("/terms", follow_redirects=False)
    assert res2.status_code == 301
    assert res2.headers.get("location") == "https://tradecall.in/terms-of-use"


def test_sub_locality_hub_page(client: TestClient, db_session: Session):
    """Sub-locality hub /palwal/omaxe-city-phase-ii renders SSR, breadcrumbs, price guide, and schemas."""
    user = User(
        email="omaxe_seller@tradecall.in",
        password_hash="fakehash",
        name="Omaxe Seller",
        phone="9999999998",
        role="owner",
        status="active"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # Seed 2 listings in Omaxe City Phase-II to meet indexable threshold
    l1 = Listing(
        user_id=user.id,
        title="3 BHK Luxury Villa in Omaxe City Phase-II, Palwal",
        description="Beautiful villa with wide road access and park facing.",
        price=7500000.0,
        location="Omaxe City Phase-II, Palwal, Haryana",
        owner_name="Omaxe Seller",
        status="approved",
        form_data={
            "kind": "owner",
            "propType": "house",
            "bhk": "3BHK",
            "area": "250",
            "unit": "Sq.Yd",
            "locality": "Omaxe City Phase-II",
            "city": "Palwal"
        }
    )
    l2 = Listing(
        user_id=user.id,
        title="200 Gaj Plot for Sale in Omaxe City Phase-II, Palwal",
        description="Prime residential plot near clubhouse.",
        price=4500000.0,
        location="Omaxe City Phase-II, Palwal, Haryana",
        owner_name="Omaxe Seller",
        status="approved",
        form_data={
            "kind": "owner",
            "propType": "plot",
            "plotArea": "200",
            "plotUnit": "Gaj",
            "locality": "Omaxe City Phase-II",
            "city": "Palwal"
        }
    )
    db_session.add_all([l1, l2])
    db_session.commit()

    res = client.get("/palwal/omaxe-city-phase-ii")
    assert res.status_code == 200
    html = res.text

    # Title & Metadata
    assert "<title>Properties in Omaxe City Phase-II, Palwal | Buy & Rent | TradeCall India</title>" in html
    assert '<link rel="canonical" href="https://tradecall.in/palwal/omaxe-city-phase-ii" />' in html
    assert '<meta name="robots" content="index, follow" />' in html

    # Breadcrumbs & Headings
    assert "<h1>Properties in Omaxe City Phase-II, Palwal</h1>" in html
    assert 'href="/properties/palwal"' in html

    # Schemas
    assert '"@type": "BreadcrumbList"' in html
    assert '"@type": "ItemList"' in html
    assert '"@type": "FAQPage"' in html

    # Price stats & Listings
    assert "₹ 45 Lac" in html
    assert "₹ 75 Lac" in html


def test_sub_locality_empty_returns_404(client: TestClient, db_session: Session):
    """Sub-locality with 0 listings returns 404 status."""
    res = client.get("/palwal/non-existent-colony-123")
    assert res.status_code == 404
    assert "noindex" in res.text


def test_hindi_pilot_hub_palwal(client: TestClient, db_session: Session):
    """Hindi hub /hi/properties/palwal renders natural Hindi, hreflang, and schemas."""
    user = User(
        email="hi_palwal_user@tradecall.in",
        password_hash="fakehash",
        name="Hi User",
        phone="9999999996",
        role="owner",
        status="active"
    )
    db_session.add(user)
    db_session.commit()

    l = Listing(
        user_id=user.id,
        title="मकान बिक्री के लिए पलवल",
        description="पलवल में सुंदर मकान।",
        price=3500000.0,
        location="Sector 2, Palwal, Haryana",
        owner_name="Hi User",
        status="approved",
        form_data={"city": "Palwal", "locality": "Sector 2"}
    )
    db_session.add(l)
    db_session.commit()

    res = client.get("/hi/properties/palwal")
    assert res.status_code == 200
    html = res.text

    assert "पलवल में प्रॉपर्टी" in html
    assert '<link rel="canonical" href="https://tradecall.in/hi/properties/palwal" />' in html

    # Reciprocal Hreflang
    assert '<link rel="alternate" hreflang="en-IN" href="https://tradecall.in/properties/palwal" />' in html
    assert '<link rel="alternate" hreflang="hi-IN" href="https://tradecall.in/hi/properties/palwal" />' in html
    assert '<link rel="alternate" hreflang="x-default" href="https://tradecall.in/properties/palwal" />' in html

    # Hindi schemas
    assert '"@type": "BreadcrumbList"' in html
    assert '"@type": "FAQPage"' in html


def test_english_hub_has_reciprocal_hreflang(client: TestClient, db_session: Session):
    """English hub /properties/palwal contains reciprocal hreflang pointing to /hi/properties/palwal."""
    res = client.get("/properties/palwal")
    assert res.status_code == 200
    html = res.text

    assert '<link rel="alternate" hreflang="en-IN" href="https://tradecall.in/properties/palwal" />' in html
    assert '<link rel="alternate" hreflang="hi-IN" href="https://tradecall.in/hi/properties/palwal" />' in html
    assert '<link rel="alternate" hreflang="x-default" href="https://tradecall.in/properties/palwal" />' in html


def test_blog_guides_seeding_and_ssr(client: TestClient, db_session: Session):
    """Seeded real estate guides render on /blog/{slug} with BlogPosting schema."""
    g = GUIDES[0]
    b = Blog(
        title=g["title"],
        permalink=g["permalink"],
        category=g["category"],
        content=g["content"],
        author=g["author"],
        tags=g["tags"],
        status="published"
    )
    db_session.add(b)
    db_session.commit()

    res = client.get(f"/blog/{g['permalink']}")
    assert res.status_code == 200
    html = res.text

    assert g["title"] in html
    assert '<link rel="canonical" href="https://tradecall.in/blog/' + g["permalink"] + '" />' in html
    assert '"@type": "BlogPosting"' in html
    assert "DTCP Approval" in html
