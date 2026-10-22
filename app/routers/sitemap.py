import time
import re
import math
from datetime import datetime
from xml.sax.saxutils import escape
from typing import Optional, Any, List, Dict
from collections import defaultdict
from fastapi import APIRouter, Depends, Response, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.db.models.listing import Listing
from app.db.models.blog import Blog
from app.core.cities import MIN_HUB_LISTINGS, slugify_city, get_city_display_name
from app.core.validation_rules import is_buyer_requirement, is_thin_business

router = APIRouter(tags=["Sitemap"])

BASE_URL = "https://tradecall.in"
CACHE_TTL_SECONDS = 3600
MAX_URLS_PER_SITEMAP = 50000

_cache: Dict[str, Any] = {
    "index": None,
    "pages": None,
    "hubs": None,
    "listings": {},
    "blog": None,
    "timestamp": 0.0
}

STATIC_PAGES = [
    "/",
    "/about",
    "/contact",
    "/cities",
    "/business-directory",
    "/blog",
]


def slugify(text: Optional[str]) -> str:
    """Matches frontend slugify() in url.ts: ASCII \\w, with typo corrections."""
    if not text:
        return ""
    text = str(text).lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.ASCII)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.replace("panchwati-raod", "panchwati-road")
    text = re.sub(r"palwal-nuh-roa(?=-|$)", "palwal-nuh-road", text)
    text = text.replace("hospitcal", "hospital")
    return text


def get_listing_path(listing_id: int, title: Optional[str], location: Optional[str], form_data: Any) -> str:
    """Matches frontend getListingUrl() in url.ts: /:city/:slug/:uniqueId."""
    loc_part = None
    if location:
        parts = location.split(",")
        if parts and parts[0]:
            loc_part = parts[0].strip()

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


def is_buyer_post_or_junk(title: Optional[str], description: Optional[str], location: Optional[str]) -> bool:
    t = (title or "").lower().strip()
    d = (description or "").lower().strip()
    loc = (location or "").lower().strip()
    if "looking to buy" in t or "looking to buy" in d or t.startswith("looking for") or t.startswith("wanted"):
        return True
    if "anywhere" in loc:
        return True
    return False


def render_urlset(urls: List[Dict[str, Optional[str]]]) -> str:
    """Renders a standard <urlset> XML document."""
    elements = []
    for u in urls:
        lastmod_tag = f"\n    <lastmod>{escape(u['lastmod'])}</lastmod>" if u.get("lastmod") else ""
        elements.append(f"""  <url>
    <loc>{escape(u['loc'])}</loc>{lastmod_tag}
  </url>""")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(elements) + "\n</urlset>\n"


def render_sitemap_index(sitemaps: List[str]) -> str:
    """Renders a <sitemapindex> pointing to child sitemaps."""
    elements = []
    for loc in sitemaps:
        elements.append(f"""  <sitemap>
    <loc>{escape(loc)}</loc>
  </sitemap>""")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(elements) + "\n</sitemapindex>\n"


def get_pages_sitemap_urls() -> List[Dict[str, Optional[str]]]:
    return [{"loc": f"{BASE_URL}{path}", "lastmod": None} for path in STATIC_PAGES]


def get_hubs_sitemap_urls(db: Session) -> List[Dict[str, Optional[str]]]:
    approved_listings = (
        db.query(Listing.location, Listing.form_data, Listing.updated_at, Listing.created_at)
        .filter(Listing.status == "approved")
        .all()
    )
    city_listings: Dict[str, List[datetime]] = defaultdict(list)
    for loc_str, f_data, upd, crt in approved_listings:
        raw_city = None
        if isinstance(f_data, dict) and f_data.get("city"):
            raw_city = f_data.get("city")
        elif loc_str:
            parts = [p.strip() for p in loc_str.split(",") if p.strip()]
            raw_city = parts[-2] if len(parts) >= 3 else (parts[0] if parts else None)
        if raw_city:
            slug = slugify_city(raw_city)
            if slug:
                dt = upd or crt
                if dt:
                    city_listings[slug].append(dt)
                else:
                    city_listings[slug].append(datetime.utcnow())

    items: List[Dict[str, Optional[str]]] = []
    for slug, dts in city_listings.items():
        if len(dts) >= MIN_HUB_LISTINGS and get_city_display_name(slug, db=db):
            latest_dt = max(dts) if dts else None
            items.append({
                "loc": f"{BASE_URL}/properties/{slug}",
                "lastmod": _format_date(latest_dt) if latest_dt else None
            })
    items.sort(key=lambda x: x["loc"])
    return items


def get_listings_sitemap_urls(db: Session) -> List[Dict[str, Optional[str]]]:
    listings = (
        db.query(Listing)
        .filter(Listing.status == "approved")
        .order_by(Listing.id.desc())
        .all()
    )
    items: List[Dict[str, Optional[str]]] = []
    for l in listings:
        # Rule: Exclude buyer requirement posts and junk localities
        if is_buyer_post_or_junk(l.title, l.description, l.location):
            continue
        if is_buyer_requirement(l.title, l.form_data):
            continue
        # Rule: Exclude thin business pages (no description and no useful details)
        if is_thin_business(l):
            continue
        path = get_listing_path(l.id, l.title, l.location, l.form_data)
        date_str = _format_date(l.updated_at or l.created_at)
        items.append({
            "loc": f"{BASE_URL}{path}",
            "lastmod": date_str if date_str else None
        })
    return items


def get_blog_sitemap_urls(db: Session) -> List[Dict[str, Optional[str]]]:
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
    items: List[Dict[str, Optional[str]]] = []
    for b in blogs:
        slug = (b.permalink or "").strip()
        if not slug:
            continue
        date_str = _format_date(b.updated_at or b.created_at)
        items.append({
            "loc": f"{BASE_URL}/blog/{slug}",
            "lastmod": date_str if date_str else None
        })
    return items


def count_listing_chunks(db: Session) -> int:
    urls = get_listings_sitemap_urls(db)
    return max(1, math.ceil(len(urls) / MAX_URLS_PER_SITEMAP))


def build_sitemap_xml(db: Session) -> str:
    num_chunks = count_listing_chunks(db)
    sitemaps = [
        f"{BASE_URL}/sitemap-pages.xml",
        f"{BASE_URL}/sitemap-hubs.xml",
    ]
    for c in range(1, num_chunks + 1):
        sitemaps.append(f"{BASE_URL}/sitemap-listings-{c}.xml")
    sitemaps.append(f"{BASE_URL}/sitemap-blog.xml")
    return render_sitemap_index(sitemaps)


def clear_cache_if_expired():
    now = time.time()
    if now - _cache["timestamp"] >= CACHE_TTL_SECONDS:
        _cache["index"] = None
        _cache["pages"] = None
        _cache["hubs"] = None
        _cache["listings"] = {}
        _cache["blog"] = None
        _cache["timestamp"] = now


# --- ENDPOINTS ---

@router.api_route("/sitemap.xml", methods=["GET", "HEAD"], include_in_schema=False)
@router.api_route("/sitemap_index.xml", methods=["GET", "HEAD"], include_in_schema=False)
@router.api_route("/api/v1/sitemap.xml", methods=["GET", "HEAD"], include_in_schema=False)
@router.api_route("/api/v1/sitemap_index.xml", methods=["GET", "HEAD"], include_in_schema=False)
def get_sitemap_index_endpoint(db: Session = Depends(get_db)):
    clear_cache_if_expired()
    if not _cache["index"]:
        num_chunks = count_listing_chunks(db)
        sitemaps = [
            f"{BASE_URL}/sitemap-pages.xml",
            f"{BASE_URL}/sitemap-hubs.xml",
        ]
        for c in range(1, num_chunks + 1):
            sitemaps.append(f"{BASE_URL}/sitemap-listings-{c}.xml")
        sitemaps.append(f"{BASE_URL}/sitemap-blog.xml")

        _cache["index"] = render_sitemap_index(sitemaps)

    return Response(
        content=_cache["index"],
        media_type="application/xml",
        headers={"Cache-Control": f"public, max-age={CACHE_TTL_SECONDS}"}
    )


@router.api_route("/sitemap-pages.xml", methods=["GET", "HEAD"], include_in_schema=False)
@router.api_route("/api/v1/sitemap-pages.xml", methods=["GET", "HEAD"], include_in_schema=False)
def get_sitemap_pages_endpoint():
    clear_cache_if_expired()
    if not _cache["pages"]:
        urls = get_pages_sitemap_urls()
        _cache["pages"] = render_urlset(urls)

    return Response(
        content=_cache["pages"],
        media_type="application/xml",
        headers={"Cache-Control": f"public, max-age={CACHE_TTL_SECONDS}"}
    )


@router.api_route("/sitemap-hubs.xml", methods=["GET", "HEAD"], include_in_schema=False)
@router.api_route("/api/v1/sitemap-hubs.xml", methods=["GET", "HEAD"], include_in_schema=False)
def get_sitemap_hubs_endpoint(db: Session = Depends(get_db)):
    clear_cache_if_expired()
    if not _cache["hubs"]:
        urls = get_hubs_sitemap_urls(db)
        _cache["hubs"] = render_urlset(urls)

    return Response(
        content=_cache["hubs"],
        media_type="application/xml",
        headers={"Cache-Control": f"public, max-age={CACHE_TTL_SECONDS}"}
    )


@router.api_route("/sitemap-blog.xml", methods=["GET", "HEAD"], include_in_schema=False)
@router.api_route("/api/v1/sitemap-blog.xml", methods=["GET", "HEAD"], include_in_schema=False)
def get_sitemap_blog_endpoint(db: Session = Depends(get_db)):
    clear_cache_if_expired()
    if not _cache["blog"]:
        urls = get_blog_sitemap_urls(db)
        _cache["blog"] = render_urlset(urls)

    return Response(
        content=_cache["blog"],
        media_type="application/xml",
        headers={"Cache-Control": f"public, max-age={CACHE_TTL_SECONDS}"}
    )


@router.api_route("/sitemap-listings-{chunk}.xml", methods=["GET", "HEAD"], include_in_schema=False)
@router.api_route("/api/v1/sitemap-listings-{chunk}.xml", methods=["GET", "HEAD"], include_in_schema=False)
def get_sitemap_listings_chunk_endpoint(chunk: str, db: Session = Depends(get_db)):
    if not chunk or not chunk.isdigit():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing sitemap chunk not found")

    chunk_num = int(chunk)
    clear_cache_if_expired()
    cached = _cache["listings"].get(chunk_num)
    if cached:
        return Response(content=cached, media_type="application/xml", headers={"Cache-Control": f"public, max-age={CACHE_TTL_SECONDS}"})

    all_listings = get_listings_sitemap_urls(db)
    total_chunks = max(1, math.ceil(len(all_listings) / MAX_URLS_PER_SITEMAP))
    if chunk_num < 1 or chunk_num > total_chunks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing sitemap chunk not found")

    start = (chunk_num - 1) * MAX_URLS_PER_SITEMAP
    end = start + MAX_URLS_PER_SITEMAP
    chunk_xml = render_urlset(all_listings[start:end])
    _cache["listings"][chunk_num] = chunk_xml

    return Response(
        content=chunk_xml,
        media_type="application/xml",
        headers={"Cache-Control": f"public, max-age={CACHE_TTL_SECONDS}"}
    )


@router.api_route("/sitemap-{chunk}.xml", methods=["GET", "HEAD"], include_in_schema=False)
@router.api_route("/api/v1/sitemap-{chunk}.xml", methods=["GET", "HEAD"], include_in_schema=False)
def get_legacy_sitemap_chunk_endpoint(chunk: str, db: Session = Depends(get_db)):
    if not chunk or not chunk.isdigit():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sitemap chunk not found")
    return get_sitemap_listings_chunk_endpoint(chunk=chunk, db=db)
