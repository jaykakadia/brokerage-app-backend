import pytest
import re
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
    assert 'meta property="og:title" content="3 BHK Luxury Villa in Sector 2"' in body
    assert 'meta name="twitter:title" content="3 BHK Luxury Villa in Sector 2"' in body
    assert 'meta property="og:title" content="3 BHK Luxury Villa in Sector 2 | Tradecall"' not in body
    assert 'meta name="twitter:title" content="3 BHK Luxury Villa in Sector 2 | Tradecall"' not in body
    assert 'meta property="og:image" content="https://tradecall.in/uploads/listings/test_villa.webp"' in body
    assert 'meta property="og:image:alt" content="3 BHK Luxury Villa in Sector 2"' in body
    assert 'og:image:width' not in body
    assert 'og:image:height' not in body
    assert 'meta name="twitter:image:alt" content="3 BHK Luxury Villa in Sector 2"' in body
    assert "RealEstateListing" in body
    assert '"price": 7500000.0' in body

    # Verify real HTML content inside <div id="root">
    assert "<h1>3 BHK Luxury Villa in Sector 2</h1>" in body
    assert '<p class="listing-price">₹ 75 Lac</p>' in body
    assert '<p class="listing-location">Sector 2, Palwal, Haryana</p>' in body
    assert '<img src="https://tradecall.in/uploads/listings/test_villa.webp" alt="3 BHK Luxury Villa in Sector 2" />' in body
    assert '<p class="listing-description">Spacious villa with private garden and modular kitchen.</p>' in body

    # 3. Test slug route /{city}/{slug}/TC011P-{id}
    res_slug = client.get(f"/sector-2/3-bhk-luxury-villa-in-sector-2/TC011P-{listing.id}")
    assert res_slug.status_code == 200
    assert "<title>3 BHK Luxury Villa in Sector 2 | Tradecall</title>" in res_slug.text
    assert f'link rel="canonical" href="https://tradecall.in/sector-2/3-bhk-luxury-villa-in-sector-2/TC011P-{listing.id}"' in res_slug.text
    assert "<h1>3 BHK Luxury Villa in Sector 2</h1>" in res_slug.text

    # 4. Test 404 for non-existent listing
    res_404 = client.get("/listing/9999999")
    assert res_404.status_code == 404
    assert "404 - Listing Not Found" in res_404.text

    res_slug_404 = client.get("/palwal/villa/TC011P-9999999")
    assert res_slug_404.status_code == 404


def test_api_x_robots_tag_middleware(client: TestClient):
    # API responses must include X-Robots-Tag: noindex
    api_res = client.get("/api/v1/listings")
    assert api_res.headers.get("X-Robots-Tag") == "noindex"

    auth_res = client.get("/api/v1/auth/csrf")
    assert auth_res.headers.get("X-Robots-Tag") == "noindex"

    # Non-API pages must NOT have X-Robots-Tag: noindex
    health_res = client.get("/health")
    assert "X-Robots-Tag" not in health_res.headers


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


def test_set_or_replace_canonical_replaces_duplicates():
    from app.routers.city_pages import set_or_replace_canonical

    # Test with multiple existing canonical tags with varying attribute orders and quotes
    dirty_html = (
        '<html><head>'
        '<link rel="canonical" href="https://old1.com" />'
        '<meta name="description" content="test" />'
        '<link href=\'https://old2.com\' rel=\'canonical\'>'
        '</head><body><div id="root"></div></body></html>'
    )
    clean_html = set_or_replace_canonical(dirty_html, "https://tradecall.in/clean")
    matches = re.findall(r'<link\b[^>]*\brel=["\']canonical["\']', clean_html, re.IGNORECASE)
    assert len(matches) == 1
    assert '<link rel="canonical" href="https://tradecall.in/clean" />' in clean_html
    assert "https://old1.com" not in clean_html
    assert "https://old2.com" not in clean_html


def test_single_canonical_count_on_all_pages(client: TestClient, db_session: Session):
    user = User(
        email="penthouse_test@tradecall.in",
        password_hash="fakehashedpassword",
        name="Penthouse Owner",
        phone="9999999998",
        role="owner",
        status="active"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # Setup test listing
    listing = Listing(
        user_id=user.id,
        title="4 BHK Penthouse in Central Park",
        description="Exclusive penthouse with panoramic skyline views.",
        price=35000000.0,
        location="Sector 42, Gurugram, Haryana",
        owner_name="Penthouse Owner",
        status="approved",
        is_featured=True
    )
    db_session.add(listing)
    db_session.commit()
    db_session.refresh(listing)

    # 1. Home page "/"
    res_home = client.get("/")
    assert res_home.status_code == 200
    home_canonicals = re.findall(r'<link\b[^>]*\brel=["\']canonical["\']', res_home.text, re.IGNORECASE)
    assert len(home_canonicals) == 1
    assert '<link rel="canonical" href="https://tradecall.in/" />' in res_home.text
    assert "<title>TradeCall India - Buy, Rent & Sell Property in Palwal & NCR</title>" in res_home.text
    assert "<h1>Buy, Rent & Sell Property in Palwal & NCR</h1>" in res_home.text
    assert '<a href="/properties/mumbai">Properties in Mumbai</a>' in res_home.text
    assert '<a href="/properties/palwal">Properties in Palwal</a>' in res_home.text

    # 2. Listing numeric page "/listing/<id>"
    res_listing = client.get(f"/listing/{listing.id}")
    assert res_listing.status_code == 200
    listing_canonicals = re.findall(r'<link\b[^>]*\brel=["\']canonical["\']', res_listing.text, re.IGNORECASE)
    assert len(listing_canonicals) == 1
    assert f'href="https://tradecall.in/sector-42/4-bhk-penthouse-in-central-park/TC011P-{listing.id}"' in res_listing.text

    # 3. Slug listing page "/<city>/<slug>/TC011P-<id>"
    res_slug = client.get(f"/sector-42/4-bhk-penthouse-in-central-park/TC011P-{listing.id}")
    assert res_slug.status_code == 200
    slug_canonicals = re.findall(r'<link\b[^>]*\brel=["\']canonical["\']', res_slug.text, re.IGNORECASE)
    assert len(slug_canonicals) == 1
    assert f'href="https://tradecall.in/sector-42/4-bhk-penthouse-in-central-park/TC011P-{listing.id}"' in res_slug.text

    # 4. City page "/properties/<city>"
    res_city = client.get("/properties/mumbai")
    assert res_city.status_code == 200
    city_canonicals = re.findall(r'<link\b[^>]*\brel=["\']canonical["\']', res_city.text, re.IGNORECASE)
    assert len(city_canonicals) == 1
    assert '<link rel="canonical" href="https://tradecall.in/properties/mumbai" />' in res_city.text
    assert "<h1>Properties in Mumbai</h1>" in res_city.text

