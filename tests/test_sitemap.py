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

    head_res = client.head("/sitemap.xml")
    assert head_res.status_code == 200

    res_api = client.get("/api/v1/sitemap.xml")
    assert res_api.status_code == 200
    assert "application/xml" in res_api.headers["content-type"]

    head_res_api = client.head("/api/v1/sitemap.xml")
    assert head_res_api.status_code == 200


def test_sitemap_city_urls_and_index_splitting(db_session, client: TestClient):
    """Verifies only top cities + active listing cities appear, duplicates merge, and sitemapindex splits."""
    db = db_session
    user = User(
        name="Test User 2",
        email="sitemap_city_test@tradecall.in",
        phone="8888888888",
        password_hash="hashed",
        role="Owner",
        status="active"
    )
    db.add(user)
    db.commit()

    # Add 2 listings with Bengaluru aliases to verify merging into a single slug
    l1 = Listing(
        user_id=user.id,
        title="Flat in Bengaluru Central",
        location="Bengaluru (Bangalore), Karnataka",
        price=6000000,
        owner_name="Owner",
        status="approved"
    )
    l2 = Listing(
        user_id=user.id,
        title="Flat in Bengaluru Tech Park",
        location="Bengaluru Urban, Karnataka",
        price=7000000,
        owner_name="Owner",
        status="approved"
    )
    # Add 1 listing in non-top city (Palwal)
    l3 = Listing(
        user_id=user.id,
        title="Commercial Shop Palwal",
        location="Palwal, Haryana",
        price=1500000,
        owner_name="Owner",
        status="approved"
    )
    db.add_all([l1, l2, l3])
    db.commit()

    # 1. Check city URLs exist in normal sitemap
    xml_content = build_sitemap_xml(db)
    root = ET.fromstring(xml_content)
    ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [el.find("ns:loc", ns).text for el in root.findall("ns:url", ns)]

    assert "https://tradecall.in/cities" in locs
    # Active listing cities appear
    assert "https://tradecall.in/properties/bangalore" in locs
    assert "https://tradecall.in/properties/palwal" in locs

    # Cities with 0 listings must NOT appear in sitemap
    assert "https://tradecall.in/properties/mumbai" not in locs
    assert "https://tradecall.in/properties/pune" not in locs
    assert "https://tradecall.in/properties/delhi-ncr" not in locs
    assert "https://tradecall.in/properties/rohtak" not in locs

    # Bangalore must appear only once despite multiple alias listings
    bangalore_matches = [url for url in locs if url == "https://tradecall.in/properties/bangalore"]
    assert len(bangalore_matches) == 1

    # 2. Test sitemap splitting with a low threshold
    split_xml = build_sitemap_xml(db, max_per_sitemap=5)
    split_root = ET.fromstring(split_xml)
    sitemaps = split_root.findall("ns:sitemap", ns)
    assert len(sitemaps) >= 2
    first_loc = sitemaps[0].find("ns:loc", ns).text
    assert first_loc == "https://tradecall.in/sitemap-1.xml"

    # 3. Test sub-sitemap chunk endpoint
    res_chunk = client.get("/sitemap-1.xml")
    assert res_chunk.status_code == 200
    assert "application/xml" in res_chunk.headers["content-type"]
    chunk_root = ET.fromstring(res_chunk.text)
    chunk_urls = chunk_root.findall("ns:url", ns)
    assert len(chunk_urls) > 0


def test_city_properties_seo_route(client: TestClient, db_session):
    """Checks GET and HEAD on /properties/:city, noindex on zero-listing cities, and 404 for unknown city."""
    user = User(
        name="Pune Owner",
        email="pune_owner@tradecall.in",
        phone="7777777777",
        password_hash="hashed",
        role="Owner",
        status="active"
    )
    db_session.add(user)
    db_session.commit()

    listing_pune = Listing(
        user_id=user.id,
        title="2 BHK in Pune",
        location="Koregaon Park, Pune, Maharashtra",
        owner_name="Pune Owner",
        status="approved"
    )
    db_session.add(listing_pune)
    db_session.commit()

    # 1. City with active listing (e.g. Pune) - GET & HEAD both 200, index follow
    res_pune = client.get("/properties/pune")
    assert res_pune.status_code == 200
    assert "text/html" in res_pune.headers["content-type"]
    html_pune = res_pune.text
    assert "<title>Properties in Pune | Buy, Rent & Commercial | Tradecall</title>" in html_pune
    assert "1 properties for sale and rent in Pune" in html_pune
    assert '<h1>Properties in Pune</h1>' in html_pune
    assert 'href="https://tradecall.in/properties/pune"' in html_pune
    assert "BreadcrumbList" in html_pune
    assert '"name": "Properties in Pune"' in html_pune
    assert '<meta name="robots" content="index, follow" />' in html_pune

    head_pune = client.head("/properties/pune")
    assert head_pune.status_code == 200

    # 2. Valid city alias (e.g. bengaluru) - redirects or maps to bangalore
    res_blr = client.get("/properties/bengaluru")
    assert res_blr.status_code == 200
    assert "<title>Properties in Bangalore | Buy, Rent & Commercial | Tradecall</title>" in res_blr.text
    assert 'href="https://tradecall.in/properties/bangalore"' in res_blr.text

    # 3. Cities with zero active listings -> has noindex, follow
    res_zero = client.get("/properties/rohtak")
    assert res_zero.status_code == 200
    assert '<meta name="robots" content="noindex, follow" />' in res_zero.text

    res_mumbai = client.get("/properties/mumbai")
    assert res_mumbai.status_code == 200
    assert '<meta name="robots" content="noindex, follow" />' in res_mumbai.text

    # 4. Unknown city -> 404 on both GET and HEAD
    res_unknown = client.get("/properties/unknown-invalid-city-xyz")
    assert res_unknown.status_code == 404
    assert "<title>404 - Page Not Found | Tradecall</title>" in res_unknown.text

    head_unknown = client.head("/properties/unknown-invalid-city-xyz")
    assert head_unknown.status_code == 404


