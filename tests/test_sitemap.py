import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.db.models.user import User
from app.db.models.listing import Listing
from app.db.models.blog import Blog
from app.routers.sitemap import slugify, get_listing_path, build_sitemap_xml, STATIC_PAGES


def test_slugify_and_listing_urls_parity():
    """Confirms get_listing_path matches frontend getListingUrl() output exactly."""
    s1 = get_listing_path(12, "Nectorflare Pvt Ltd Gaur City Mall", "Greater Noida, Uttar Pradesh", None)
    assert s1 == "/greater-noida/nectorflare-pvt-ltd-gaur-city-mall/TC011P-12"

    s2 = get_listing_path(5, "3 BHK Luxury Flat in Sector 15", "Sector 15, Faridabad, Haryana", None)
    assert s2 == "/sector-15/3-bhk-luxury-flat-in-sector-15/TC011P-5"

    s3 = get_listing_path(99, "Commercial Shop near Bus Stand", None, {"city": "Palwal"})
    assert s3 == "/palwal/commercial-shop-near-bus-stand/TC011P-99"


def test_sitemap_xml_generation_and_filtering(db_session):
    """Checks XML validity, static pages lack lastmod, and only approved listings/blogs with permalinks appear."""
    db = db_session
    user = User(
        name="Test User",
        email="sitemap_test@tradecall.in",
        phone="9999999999",
        password_hash="hashed",
        role="Owner",
        status="active"
    )
    db.add(user)
    db.commit()

    now = datetime.now(timezone.utc)

    # 1. Listings with various statuses
    approved_listing = Listing(
        user_id=user.id,
        title="Approved Villa",
        location="Palwal, Haryana",
        price=5000000,
        owner_name="Owner",
        status="approved",
        created_at=now,
        updated_at=now
    )
    pending_listing = Listing(
        user_id=user.id,
        title="Pending Plot",
        location="Palwal, Haryana",
        price=1000000,
        owner_name="Owner",
        status="pending"
    )
    sold_listing = Listing(
        user_id=user.id,
        title="Sold Apartment",
        location="Faridabad, Haryana",
        price=3500000,
        owner_name="Owner",
        status="sold"
    )
    deleted_listing = Listing(
        user_id=user.id,
        title="Deleted House",
        location="Faridabad, Haryana",
        price=4000000,
        owner_name="Owner",
        status="deleted"
    )
    db.add_all([approved_listing, pending_listing, sold_listing, deleted_listing])

    # 2. Blogs with permalinks, empty permalink, draft
    blog_with_slug = Blog(
        title="Real Estate Market 2026",
        content="Guide content",
        permalink="real-estate-market-2026",
        status="published",
        created_at=now,
        updated_at=now
    )
    blog_no_slug = Blog(
        title="Untitled Post",
        content="Guide content",
        permalink="",
        status="published"
    )
    blog_draft = Blog(
        title="Draft Post",
        content="Draft content",
        permalink="draft-post",
        status="draft"
    )
    db.add_all([blog_with_slug, blog_no_slug, blog_draft])
    db.commit()

    # Build XML
    xml_content = build_sitemap_xml(db)

    # Parse XML
    root = ET.fromstring(xml_content)
    ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    url_elements = root.findall("ns:url", ns)

    loc_to_lastmod = {}
    for el in url_elements:
        loc = el.find("ns:loc", ns).text
        lastmod_el = el.find("ns:lastmod", ns)
        loc_to_lastmod[loc] = lastmod_el.text if lastmod_el is not None else None

    # Check static pages (all 9 must exist, and have NO lastmod)
    for p in STATIC_PAGES:
        full_url = f"https://tradecall.in{p}"
        assert full_url in loc_to_lastmod
        assert loc_to_lastmod[full_url] is None, f"Static page {full_url} should not have lastmod"

    # Check approved listing is present and has lastmod
    expected_listing_url = f"https://tradecall.in/palwal/approved-villa/TC011P-{approved_listing.id}"
    assert expected_listing_url in loc_to_lastmod
    assert loc_to_lastmod[expected_listing_url] == now.strftime("%Y-%m-%d")

    # Non-approved listings must NOT be present
    for loc in loc_to_lastmod:
        assert f"TC011P-{pending_listing.id}" not in loc
        assert f"TC011P-{sold_listing.id}" not in loc
        assert f"TC011P-{deleted_listing.id}" not in loc

    # Blog with slug must be present
    expected_blog_url = "https://tradecall.in/blog/real-estate-market-2026"
    assert expected_blog_url in loc_to_lastmod
    assert loc_to_lastmod[expected_blog_url] == now.strftime("%Y-%m-%d")

    # Draft blog or blog without permalink must NOT be present
    assert "https://tradecall.in/blog/draft-post" not in loc_to_lastmod
    for loc in loc_to_lastmod:
        assert not loc.endswith("/blog/")


def test_sitemap_endpoint_headers(client: TestClient):
    """Checks the endpoint response, content-type, and Cache-Control header."""
    res = client.get("/sitemap.xml")
    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]
    assert "public, max-age=3600" in res.headers["cache-control"]

    res_api = client.get("/api/v1/sitemap.xml")
    assert res_api.status_code == 200
    assert "application/xml" in res_api.headers["content-type"]
