import re
from typing import Optional
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.db.models.blog import Blog
from app.core.cities import slugify_city, get_city_display_name, CITY_SLUG_MAP, TOP_CITIES
from app.routers.city_pages import load_base_index_html, set_or_replace_meta

router = APIRouter(tags=["Legacy SEO Redirects"])
BASE_URL = "https://tradecall.in"


def _build_410_response(base_html: str, reason: str = "This page is no longer available.") -> HTMLResponse:
    html = base_html
    # Replace title
    html = re.sub(
        r"<title>.*?</title>",
        "<title>410 - Content Removed | TradeCall India</title>",
        html,
        count=1,
        flags=re.DOTALL
    )
    # Remove canonical
    html = re.sub(r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>', '', html, flags=re.IGNORECASE)
    # Set robots to noindex, follow
    html = set_or_replace_meta(html, "name", "robots", "noindex, follow")

    rendered_root = f'''<div id="root">
    <main style="padding: 40px 20px; text-align: center; font-family: sans-serif;">
      <h1>410 - Content Permanently Removed</h1>
      <p>{reason}</p>
      <p><a href="/" style="color: #2563eb; text-decoration: underline;">Go to TradeCall Homepage</a> | <a href="/cities" style="color: #2563eb; text-decoration: underline;">Browse City Hubs</a></p>
    </main>
  </div>'''
    html = re.sub(r'<div\s+id=["\']root["\'][^>]*>.*?</div>', rendered_root, html, count=1, flags=re.DOTALL)
    return HTMLResponse(content=html, status_code=status.HTTP_410_GONE)


# 1. Legacy Blog redirects: /blog/blog-detail/...
@router.api_route("/blog/blog-detail/{blog_id}/{sub_id}/{slug:path}", methods=["GET", "HEAD"])
@router.api_route("/blog/blog-detail/{rest:path}", methods=["GET", "HEAD"])
def legacy_blog_detail(
    request: Request,
    blog_id: Optional[str] = None,
    sub_id: Optional[str] = None,
    slug: Optional[str] = None,
    rest: Optional[str] = None,
    db: Session = Depends(get_db)
):
    blog = None

    # Check numeric blog_id
    candidate_id = blog_id
    if not candidate_id and rest:
        parts = rest.strip("/").split("/")
        if parts and parts[0].isdigit():
            candidate_id = parts[0]

    if candidate_id and candidate_id.isdigit():
        blog = db.query(Blog).filter(Blog.id == int(candidate_id)).first()

    # If not found by ID, attempt permalink match from slug or rest
    if not blog:
        candidate_slug = slug or (rest.strip("/").split("/")[-1] if rest else None)
        if candidate_slug:
            clean_s = candidate_slug.strip().lower()
            blog = db.query(Blog).filter(Blog.permalink == clean_s).first()

    if blog and blog.status in ("published", "publish") and blog.permalink:
        target_url = f"{BASE_URL}/blog/{blog.permalink}"
        return RedirectResponse(url=target_url, status_code=status.HTTP_301_MOVED_PERMANENTLY)

    base_html = load_base_index_html()
    return _build_410_response(base_html, "This blog article has been removed or is no longer published.")


# 2. Legacy Page redirects: /pages/{slug:path}
@router.api_route("/pages/{slug:path}", methods=["GET", "HEAD"])
def legacy_pages_redirect(slug: str):
    clean = slug.strip("/").lower()

    if clean in ("about", "about-us", "aboutus", "about-tradecall"):
        return RedirectResponse(url=f"{BASE_URL}/about", status_code=status.HTTP_301_MOVED_PERMANENTLY)
    if clean in ("contact", "contact-us", "contactus"):
        return RedirectResponse(url=f"{BASE_URL}/contact", status_code=status.HTTP_301_MOVED_PERMANENTLY)
    if clean in ("privacy", "privacy-policy"):
        return RedirectResponse(url=f"{BASE_URL}/privacy", status_code=status.HTTP_301_MOVED_PERMANENTLY)
    if clean in ("terms", "terms-of-use", "terms-and-conditions"):
        return RedirectResponse(url=f"{BASE_URL}/terms-of-use", status_code=status.HTTP_301_MOVED_PERMANENTLY)

    base_html = load_base_index_html()
    return _build_410_response(base_html, "The legacy page you requested is no longer available.")


# 3. Legacy Search redirects: /search/get-property and /search/{rest:path}
@router.api_route("/search/get-property", methods=["GET", "HEAD"])
@router.api_route("/search/{rest:path}", methods=["GET", "HEAD"])
def legacy_search_redirect(request: Request, rest: Optional[str] = None, db: Session = Depends(get_db)):
    loc = request.query_params.get("location") or request.query_params.get("city") or request.query_params.get("search")
    if not loc and rest:
        # Check if rest path contains a city name
        clean_rest = rest.strip("/").lower()
        if clean_rest and clean_rest not in ("get-property", "property", "all"):
            loc = clean_rest

    if loc:
        # Split on comma or dash to find first city candidate
        first_token = [p.strip() for p in loc.split(",") if p.strip()][0] if "," in loc else loc.strip()
        slug = slugify_city(first_token)
        if slug:
            # Verify if this is a known city
            display = get_city_display_name(slug, db=db)
            if display:
                target_url = f"{BASE_URL}/properties/{slug}"
                return RedirectResponse(url=target_url, status_code=status.HTTP_301_MOVED_PERMANENTLY)

    base_html = load_base_index_html()
    return _build_410_response(base_html, "This search query is no longer valid or supported.")


# 4. Bare Properties redirect: /properties and /properties/ -> /
@router.api_route("/properties", methods=["GET", "HEAD"])
@router.api_route("/properties/", methods=["GET", "HEAD"])
def legacy_properties_redirect():
    return RedirectResponse(url=f"{BASE_URL}/", status_code=status.HTTP_301_MOVED_PERMANENTLY)

