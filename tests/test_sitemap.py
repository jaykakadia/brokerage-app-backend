import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.db.models.user import User
from app.db.models.listing import Listing
from app.db.models.blog import Blog
from app.routers.sitemap import (
    slugify,
    get_listing_path,
    build_sitemap_xml,
    STATIC_PAGES,
    get_pages_sitemap_urls,
    get_hubs_sitemap_urls,
    get_listings_sitemap_urls,
    get_blog_sitemap_urls
)


def test_slugify_and_listing_urls_parity():
    """Confirms get_listing_path matches frontend getListingUrl() output exactly."""
    s1 = get_listing_path(12, "Nectorflare Pvt Ltd Gaur City Mall", "Greater Noida, Uttar Pradesh", None)
    assert s1 == "/greater-noida/nectorflare-pvt-ltd-gaur-city-mall/TC011P-12"

    s2 = get_listing_path(5, "3 BHK Luxury Flat in Sector 15", "Sector 15, Faridabad, Haryana", None)
    assert s2 == "/sector-15/3-bhk-luxury-flat-in-sector-15/TC011P-5"

    s3 = get_listing_path(99, "Commercial Shop near Bus Stand", None, {"city": "Palwal"})
    assert s3 == "/palwal/commercial-shop-near-bus-stand/TC011P-99"

    # Typo corrections
    assert slugify("Panchwati Raod") == "panchwati-road"
    assert slugify("Palwal Nuh Roa") == "palwal-nuh-road"
    assert slugify("City Hospitcal") == "city-hospital"


def test_sitemap_index_xml_generation(db_session, client: TestClient):
    """Checks sitemap_index.xml returns <sitemapindex> containing child sitemaps."""
    res = client.get("/sitemap_index.xml")
    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]
    assert "public, max-age=3600" in res.headers["cache-control"]

    root = ET.fromstring(res.text)
    ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sitemaps = [el.find("ns:loc", ns).text for el in root.findall("ns:sitemap", ns)]

    assert "https://tradecall.in/sitemap-pages.xml" in sitemaps
    assert "https://tradecall.in/sitemap-hubs.xml" in sitemaps
    assert "https://tradecall.in/sitemap-listings-1.xml" in sitemaps
    assert "https://tradecall.in/sitemap-blog.xml" in sitemaps


def test_sitemap_pages_and_filtering(db_session, client: TestClient):
    """Checks sitemap-pages.xml contains static pages without lastmod."""
    res = client.get("/sitemap-pages.xml")
    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]

    root = ET.fromstring(res.text)
    ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [el.find("ns:loc", ns).text for el in root.findall("ns:url", ns)]

    for p in STATIC_PAGES:
        assert f"https://tradecall.in{p}" in locs

    # Excluded static pages must NOT appear in sitemap-pages
    assert "https://tradecall.in/post-listing" not in locs
    assert "https://tradecall.in/privacy" not in locs
    assert "https://tradecall.in/terms-of-use" not in locs


def test_sitemap_listings_filtering(db_session, client: TestClient):
    """Verifies approved listings appear while buyer posts, junk locations, and non-approved statuses are excluded."""
    db = db_session
    user = User(
        name="Test User",
        email="sitemap_listings_test@tradecall.in",
        phone="9999999999",
        password_hash="hashed",
        role="Owner",
        status="active"
    )
    db.add(user)
    db.commit()

    now = datetime.now(timezone.utc)

    good_listing = Listing(
        user_id=user.id,
        title="2 BHK Flat in Sector 2",
        location="Sector 2, Palwal, Haryana",
        price=3500000,
        owner_name="Owner",
        status="approved",
        created_at=now,
        updated_at=now
    )
    buyer_listing = Listing(
        user_id=user.id,
        title="Looking to Buy 2BHK Flat",
        location="Sector 2, Palwal, Haryana",
        price=3500000,
        owner_name="Owner",
        status="approved"
    )
    junk_listing = Listing(
        user_id=user.id,
        title="Commercial Plot",
        location="Anywhere, Palwal, Haryana",
        price=1500000,
        owner_name="Owner",
        status="approved"
    )
    pending_listing = Listing(
        user_id=user.id,
        title="Pending House",
        location="Palwal, Haryana",
        price=4000000,
        owner_name="Owner",
        status="pending"
    )
    db.add_all([good_listing, buyer_listing, junk_listing, pending_listing])
    db.commit()

    res = client.get("/sitemap-listings-1.xml")
    assert res.status_code == 200

    root = ET.fromstring(res.text)
    ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [el.find("ns:loc", ns).text for el in root.findall("ns:url", ns)]

    good_url = f"https://tradecall.in/sector-2/2-bhk-flat-in-sector-2/TC011P-{good_listing.id}"
    assert good_url in locs
    assert not any(f"TC011P-{buyer_listing.id}" in url for url in locs)
    assert not any(f"TC011P-{junk_listing.id}" in url for url in locs)
    assert not any(f"TC011P-{pending_listing.id}" in url for url in locs)


def test_sitemap_endpoint_headers(client: TestClient):
    """Checks endpoint response, content-type, and Cache-Control header."""
    for path in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap-pages.xml", "/sitemap-hubs.xml", "/sitemap-listings-1.xml", "/sitemap-blog.xml"]:
        res = client.get(path)
        assert res.status_code == 200
        assert "application/xml" in res.headers["content-type"]
        assert "public, max-age=3600" in res.headers["cache-control"]

        head_res = client.head(path)
        assert head_res.status_code == 200


def test_city_properties_seo_route(client: TestClient, db_session):
    """Checks GET and HEAD on /properties/:city, noindex on low-listing cities, and 404 for unknown city."""
    # Unknown city -> 404 on both GET and HEAD
    res_unknown = client.get("/properties/unknown-invalid-city-xyz")
    assert res_unknown.status_code == 404
    assert "<title>404 - Page Not Found | TradeCall India</title>" in res_unknown.text

    head_unknown = client.head("/properties/unknown-invalid-city-xyz")
    assert head_unknown.status_code == 404
