import time
import re
from datetime import datetime
from xml.sax.saxutils import escape
from typing import Optional, Any
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.db.models.listing import Listing
from app.db.models.blog import Blog

router = APIRouter(tags=["Sitemap"])

BASE_URL = "https://tradecall.in"
CACHE_TTL_SECONDS = 3600

_cache = {
    "xml": "",
    "timestamp": 0.0
}

STATIC_PAGES = [
    "/",
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


def build_sitemap_xml(db: Session) -> str:
    urls = []

    # 1. 9 Static pages (no lastmod)
    for path in STATIC_PAGES:
        urls.append(f"""  <url>
    <loc>{escape(BASE_URL + path)}</loc>
  </url>""")

    # 2. Approved listings only (limit 48,000 for 50,000 protocol ceiling)
    listings = (
        db.query(Listing.id, Listing.title, Listing.location, Listing.form_data, Listing.updated_at, Listing.created_at)
        .filter(Listing.status == "approved")
        .order_by(Listing.id.desc())
        .limit(48000)
        .all()
    )
    for l in listings:
        path = get_listing_path(l.id, l.title, l.location, l.form_data)
        date_str = _format_date(l.updated_at or l.created_at)
        lastmod_tag = f"\n    <lastmod>{date_str}</lastmod>" if date_str else ""
        urls.append(f"""  <url>
    <loc>{escape(BASE_URL + path)}</loc>{lastmod_tag}
  </url>""")

    # 3. Published blogs with non-empty permalink only
    blogs = (
        db.query(Blog.id, Blog.permalink, Blog.updated_at, Blog.created_at)
        .filter(
            Blog.status.in_(["published", "publish"]),
            Blog.permalink.isnot(None),
            Blog.permalink != ""
        )
        .order_by(Blog.id.desc())
        .limit(1500)
        .all()
    )
    for b in blogs:
        slug = (b.permalink or "").strip()
        if not slug:
            continue
        date_str = _format_date(b.updated_at or b.created_at)
        lastmod_tag = f"\n    <lastmod>{date_str}</lastmod>" if date_str else ""
        urls.append(f"""  <url>
    <loc>{escape(f"{BASE_URL}/blog/{slug}")}</loc>{lastmod_tag}
  </url>""")

    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n"


@router.get("/sitemap.xml", include_in_schema=False)
@router.get("/api/v1/sitemap.xml", include_in_schema=False)
def get_sitemap(db: Session = Depends(get_db)):
    now = time.time()
    if _cache["xml"] and (now - _cache["timestamp"] < CACHE_TTL_SECONDS):
        xml_content = _cache["xml"]
    else:
        xml_content = build_sitemap_xml(db)
        _cache["xml"] = xml_content
        _cache["timestamp"] = now

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Cache-Control": f"public, max-age={CACHE_TTL_SECONDS}"}
    )
