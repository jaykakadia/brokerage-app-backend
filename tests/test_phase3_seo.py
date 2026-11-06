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


def test_property_costs_guide_content(client: TestClient, db_session: Session):
    """Property costs guide must reflect official Haryana Revenue rates and Income-tax Act 2025 Section 393(1)."""
    cost_guide = next(g for g in GUIDES if g["permalink"] == "property-registration-and-purchase-costs-in-haryana")
    b = Blog(
        title=cost_guide["title"],
        permalink=cost_guide["permalink"],
        category=cost_guide["category"],
        content=cost_guide["content"],
        author=cost_guide["author"],
        tags=cost_guide["tags"],
        status="published"
    )
    db_session.add(b)
    db_session.commit()

    res = client.get(f"/blog/{cost_guide['permalink']}")
    assert res.status_code == 200
    html = res.text

    assert "Section 393(1)" in html
    assert "Form 141 (Schedule B)" in html
    assert "7.0%" in html
    assert "5.0% Stamp Duty + 2.0% Municipal Duty" in html
    assert "egrashry.nic.in" in html
    assert "jamabandi.nic.in" in html
    assert "Last Reviewed: October 2026" in html


def test_audit_improvements_directory_contact_faq_and_business_seo(client: TestClient, db_session: Session):
    """Verifies Audit Points 2a, 3, 4, 5, 6, 7, and 8 across Business Directory, Contact, FAQ, and Business Detail SSR."""
    user = User(
        email="ashoka_prop@tradecall.in",
        password_hash="fakehash",
        name="Ashoka Owner",
        phone="9999999911",
        role="owner",
        status="active"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    biz = Listing(
        user_id=user.id,
        title="Ashoka Property",
        description="Leading real estate consultant for plots and flats.",
        price=0.0,
        location="Greater Faridabad, Faridabad, Haryana",
        owner_name="Ashoka Owner",
        status="approved",
        form_data={
            "kind": "business",
            "businessName": "Ashoka Property",
            "category": "Property Dealer",
            "locality": "Greater Faridabad",
            "city": "Faridabad"
        }
    )
    db_session.add(biz)
    db_session.commit()
    db_session.refresh(biz)

    # 1. Business Detail SSR (Points 3, 4, 2a)
    biz_res = client.get(f"/greater-faridabad/ashoka-property/TC011P-{biz.id}")
    assert biz_res.status_code == 200
    biz_html = biz_res.text
    assert "<title>Ashoka Property Faridabad – Property Dealer | TradeCall India</title>" in biz_html
    assert "<h1>Ashoka Property – Property Dealer in Greater Faridabad</h1>" in biz_html
    assert "Contact Ashoka Property in Greater Faridabad, Faridabad" in biz_html
    assert 'href="/faridabad/greater-faridabad"' in biz_html

    # 2. Business Directory & Category/City Landing Page SSR (Points 7 & 8)
    dir_res = client.get("/business-directory")
    assert dir_res.status_code == 200
    assert "<title>Business Directory in Palwal, Faridabad &amp; Delhi NCR | TradeCall India</title>" in dir_res.text
    assert '"@type": "CollectionPage"' in dir_res.text
    assert '"@type": "ItemList"' in dir_res.text
    assert "Ashoka Property" in dir_res.text

    landing_res = client.get("/business-directory/faridabad/property-dealers")
    assert landing_res.status_code == 200
    assert "<title>Property Dealers in Faridabad | Business Directory – TradeCall India</title>" in landing_res.text
    assert "<h1>Property Dealers in Faridabad</h1>" in landing_res.text
    assert "Ashoka Property" in landing_res.text

    # 3. Contact Page SSR (Points 6 & 8)
    contact_res = client.get("/contact")
    assert contact_res.status_code == 200
    assert "<title>Contact TradeCall India – Property &amp; Business Listing Support | TradeCall India</title>" in contact_res.text
    assert '"@type": "ContactPage"' in contact_res.text
    assert '"@type": "Organization"' in contact_res.text
    assert "maps.google.com" in contact_res.text
    assert 'href="/faq"' in contact_res.text
    assert 'href="/post-listing"' in contact_res.text

    # 4. FAQ Page SSR
    faq_res = client.get("/faq")
    assert faq_res.status_code == 200
    assert '"@type": "FAQPage"' in faq_res.text
