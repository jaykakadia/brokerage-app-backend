import time
import re
import math
from datetime import datetime
from xml.sax.saxutils import escape
from typing import Optional, Any, List, Dict
from fastapi import APIRouter, Depends, Response, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.db.models.listing import Listing
from app.db.models.blog import Blog
from app.db.models.location import Location
from app.core.cities import TOP_CITIES, slugify_city

router = APIRouter(tags=["Sitemap"])

BASE_URL = "https://tradecall.in"
CACHE_TTL_SECONDS = 3600
MAX_URLS_PER_SITEMAP = 50000

_cache: Dict[str, Any] = {
    "main": "",
    "chunks": {},
    "timestamp": 0.0
}

STATIC_PAGES = [
    "/",
    "/cities",
    "/business-directory",
    "/post-listing",
    "/blog",
    "/advertise",
    "/about",
    "/contact",
    "/terms-of-use",
    "/privacy",
]


def slugify(text: Optional[str]) -> str:
    """Matches frontend slugify() in url.ts: ASCII \\w, no stripping hyphens at ends."""
    if not text:
        return ""
    text = str(text).lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.ASCII)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text


def get_listing_path(listing_id: int, title: Optional[str], location: Optional[str], form_data: Any) -> str:
    """Matches frontend getListingUrl() in url.ts: /:city/:slug/:uniqueId."""
    loc_part = None
    if location:
        parts = location.split(",")
        if parts and parts[0]:
            loc_part = parts[0]

    city_candidate = loc_part
    if not city_candidate and isinstance(form_data, dict):
        city_candidate = form_data.get("city")
    if not city_candidate:
        city_candidate = "NCR"

    city = slugify(city_candidate) or "ncr"
    title_slug = slugify(title) or "property-listing"
    unique_id = f"TC011P-{listing_id}"
    return f"/{city}/{title_slug}/{unique_id}"


def _format_date(dt: Optional[datetime]) -> str:
    if dt:
        return dt.strftime("%Y-%m-%d")
    return ""


def get_all_sitemap_urls(db: Session) -> List[Dict[str, Optional[str]]]:
    """Gathers all static, city, listing, and blog URLs for sitemap generation."""
    items: List[Dict[str, Optional[str]]] = []

    # 1. Static Pages
    for path in STATIC_PAGES:
        items.append({"loc": BASE_URL + path, "lastmod": None})

    # 2. City Pages (/properties/:slug)
    # Include ONLY top cities + cities that have at least 1 active (approved) listing
    seen_cities = set()
    for top_c in TOP_CITIES:
        slug = top_c["slug"]
        if slug not in seen_cities:
            seen_cities.add(slug)
            items.append({"loc": f"{BASE_URL}/properties/{slug}", "lastmod": None})

    approved_cities_query = (
        db.query(Listing.location, Listing.form_data)
        .filter(Listing.status == "approved")
        .all()
    )
    for loc_str, f_data in approved_cities_query:
        raw_city = None
        if loc_str:
            parts = [p.strip() for p in loc_str.split(",") if p.strip()]
            raw_city = parts[-2] if len(parts) >= 3 else (parts[0] if parts else None)
        if not raw_city and isinstance(f_data, dict):
            raw_city = f_data.get("city")
        if raw_city:
            slug = slugify_city(raw_city)
            if slug and slug not in seen_cities:
                seen_cities.add(slug)
                items.append({"loc": f"{BASE_URL}/properties/{slug}", "lastmod": None})

    # 3. Approved Listings
    listings = (
        db.query(Listing.id, Listing.title, Listing.location, Listing.form_data, Listing.updated_at, Listing.created_at)
        .filter(Listing.status == "approved")
        .order_by(Listing.id.desc())
        .all()
    )
    for l in listings:
        path = get_listing_path(l.id, l.title, l.location, l.form_data)
        date_str = _format_date(l.updated_at or l.created_at)
        items.append({"loc": BASE_URL + path, "lastmod": date_str if date_str else None})

    # 4. Published Blogs
    blogs = (
        db.query(Blog.id, Blog.permalink, Blog.updated_at, Blog.created_at)
        .filter(
            Blog.status.in_(["published", "publish"]),
            Blog.permalink.isnot(None),
            Blog.permalink != ""
        )
        .order_by(Blog.id.desc())
        .all()
    )
    for b in blogs:
        slug = (b.permalink or "").strip()
        if not slug:
            continue
        date_str = _format_date(b.updated_at or b.created_at)
        items.append({"loc": f"{BASE_URL}/blog/{slug}", "lastmod": date_str if date_str else None})

    return items


def render_urlset(urls: List[Dict[str, Optional[str]]]) -> str:
    """Renders a standard <urlset> XML document."""
    elements = []
    for u in urls:
        lastmod_tag = f"\n    <lastmod>{u['lastmod']}</lastmod>" if u.get("lastmod") else ""
        elements.append(f"""  <url>
    <loc>{escape(u['loc'])}</loc>{lastmod_tag}
  </url>""")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(elements) + "\n</urlset>\n"


def render_sitemap_index(total_chunks: int) -> str:
    """Renders a <sitemapindex> pointing to sub-sitemaps."""
    elements = []
    for i in range(1, total_chunks + 1):
        elements.append(f"""  <sitemap>
    <loc>{BASE_URL}/sitemap-{i}.xml</loc>
  </sitemap>""")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(elements) + "\n</sitemapindex>\n"


def build_sitemap_xml(db: Session, max_per_sitemap: int = MAX_URLS_PER_SITEMAP) -> str:
    """
    Builds the main sitemap XML. If total URLs <= max_per_sitemap, returns <urlset>.
    If total URLs > max_per_sitemap, returns <sitemapindex>.
    """
    urls = get_all_sitemap_urls(db)
    if len(urls) <= max_per_sitemap:
        return render_urlset(urls)

    total_chunks = math.ceil(len(urls) / max_per_sitemap)
    return render_sitemap_index(total_chunks)


def build_sitemap_chunk_xml(db: Session, page: int, max_per_sitemap: int = MAX_URLS_PER_SITEMAP) -> Optional[str]:
    """Builds a specific sub-sitemap chunk <urlset>."""
    urls = get_all_sitemap_urls(db)
    total_chunks = math.ceil(len(urls) / max_per_sitemap)
    if page < 1 or page > total_chunks:
        return None

    start = (page - 1) * max_per_sitemap
    end = start + max_per_sitemap
    chunk_urls = urls[start:end]
    return render_urlset(chunk_urls)


@router.get("/sitemap.xml", include_in_schema=False)
@router.get("/api/v1/sitemap.xml", include_in_schema=False)
def get_sitemap(db: Session = Depends(get_db)):
    now = time.time()
    if _cache["main"] and (now - _cache["timestamp"] < CACHE_TTL_SECONDS):
        xml_content = _cache["main"]
    else:
        xml_content = build_sitemap_xml(db)
        _cache["main"] = xml_content
        _cache["chunks"] = {}
        _cache["timestamp"] = now

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Cache-Control": f"public, max-age={CACHE_TTL_SECONDS}"}
    )


@router.get("/sitemap-{page}.xml", include_in_schema=False)
@router.get("/api/v1/sitemap-{page}.xml", include_in_schema=False)
def get_sitemap_chunk(page: int, db: Session = Depends(get_db)):
    now = time.time()
    cached = _cache["chunks"].get(page)
    if cached and (now - _cache["timestamp"] < CACHE_TTL_SECONDS):
        xml_content = cached
    else:
        xml_content = build_sitemap_chunk_xml(db, page)
        if not xml_content:
            raise HTTPException(status_code=404, detail="Sitemap page not found")
        _cache["chunks"][page] = xml_content

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Cache-Control": f"public, max-age={CACHE_TTL_SECONDS}"}
    )
