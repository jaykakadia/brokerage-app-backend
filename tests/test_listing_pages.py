import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models.user import User
from app.db.models.listing import Listing, ListingImage


def test_listing_meta_injection_and_404(client: TestClient, db_session: Session):
    # 1. Create a test user and listing
    user = User(
        email="listing_seo_test@tradecall.in",
        password_hash="fakehashedpassword",
        name="Test SEO Owner",
        phone="9999999990",
        role="owner",
        status="active"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    listing = Listing(
        user_id=user.id,
        title="3 BHK Luxury Villa in Sector 2",
        location="Sector 2, Palwal, Haryana",
        price=7500000.0,
        description="Spacious villa with private garden and modular kitchen.",
        owner_name="Test SEO Owner",
        status="approved"
    )
    db_session.add(listing)
    db_session.commit()
    db_session.refresh(listing)

    image = ListingImage(
        listing_id=listing.id,
        file_path="listings/test_villa.webp",
        sort_order=0
    )
    db_session.add(image)
    db_session.commit()

    # 2. Test /listing/{id}
    res = client.get(f"/listing/{listing.id}")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    body = res.text

    assert "<title>3 BHK Luxury Villa in Sector 2 | Tradecall</title>" in body
    assert 'meta name="description"' in body
    assert "₹ 75 Lac" in body
    assert f'link rel="canonical" href="https://tradecall.in/sector-2/3-bhk-luxury-villa-in-sector-2/TC011P-{listing.id}"' in body
    assert 'meta property="og:title" content="3 BHK Luxury Villa in Sector 2 | Tradecall"' in body
    assert 'meta property="og:image" content="https://tradecall.in/uploads/listings/test_villa.webp"' in body
    assert 'meta property="og:image:alt" content="3 BHK Luxury Villa in Sector 2"' in body
    assert 'og:image:width' not in body
    assert 'og:image:height' not in body
    assert 'meta name="twitter:image:alt" content="3 BHK Luxury Villa in Sector 2"' in body
    assert "RealEstateListing" in body
    assert '"price": 7500000.0' in body

    # 3. Test slug route /{city}/{slug}/TC011P-{id}
    res_slug = client.get(f"/sector-2/3-bhk-luxury-villa-in-sector-2/TC011P-{listing.id}")
    assert res_slug.status_code == 200
    assert "<title>3 BHK Luxury Villa in Sector 2 | Tradecall</title>" in res_slug.text
    assert f'link rel="canonical" href="https://tradecall.in/sector-2/3-bhk-luxury-villa-in-sector-2/TC011P-{listing.id}"' in res_slug.text

    # 4. Test 404 for non-existent listing
    res_404 = client.get("/listing/9999999")
    assert res_404.status_code == 404
    assert "404 - Listing Not Found" in res_404.text

    res_slug_404 = client.get("/palwal/villa/TC011P-9999999")
    assert res_slug_404.status_code == 404


def test_load_base_index_html_reloads_on_mtime_change(monkeypatch, tmp_path):
    import time
    from app.routers.city_pages import load_base_index_html, _html_cache

    # Reset cache before and after test
    _html_cache["path"] = None
    _html_cache["mtime"] = 0.0
    _html_cache["content"] = None

    test_file = tmp_path / "index.html"
    test_file.write_text("<html><head><title>Default</title><script src=\"bundle-v1.js\"></script></head><body></body></html>", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_INDEX_PATH", str(test_file))

    try:
        # 1. Initial read loads bundle-v1
        v1 = load_base_index_html()
        assert "bundle-v1.js" in v1

        # 2. Simulate frontend deployment (new bundle written to disk)
        time.sleep(0.05)
        test_file.write_text("<html><head><title>Default</title><script src=\"bundle-v2.js\"></script></head><body></body></html>", encoding="utf-8")

        # 3. Next call automatically detects mtime change and serves bundle-v2
        v2 = load_base_index_html()
        assert "bundle-v2.js" in v2
        assert "bundle-v1.js" not in v2
    finally:
        _html_cache["path"] = None
        _html_cache["mtime"] = 0.0
        _html_cache["content"] = None
