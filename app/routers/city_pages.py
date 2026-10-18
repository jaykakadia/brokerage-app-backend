import html as html_lib
import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, status
from fastapi.responses import HTMLResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.db.models.listing import Listing
from app.core.cities import get_city_display_name, slugify_city, TOP_CITY_SLUGS
from app.routers.sitemap import get_listing_path

router = APIRouter(tags=["City Pages"])

BASE_URL = "https://tradecall.in"


def format_price(val: Optional[float]) -> str:
    """Formats numeric price into Indian currency shorthand (Lakhs/Crores)."""
    if not val or val <= 0:
        return ""
    val = float(val)
    if val >= 10_000_000:
        cr = val / 10_000_000
        return f"₹ {cr:.2f}".rstrip("0").rstrip(".") + " Cr"
    if val >= 100_000:
        lac = val / 100_000
        return f"₹ {lac:.2f}".rstrip("0").rstrip(".") + " Lac"
    return f"₹ {int(val):,}"


def set_or_replace_canonical(html: str, canonical_url: str) -> str:
    """Replaces any and all existing canonical link tags with a single canonical tag."""
    pattern = r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>'
    html = re.sub(pattern, '', html, flags=re.IGNORECASE)
    return html.replace("</head>", f'  <link rel="canonical" href="{canonical_url}" />\n</head>')


def set_or_replace_meta(html: str, attr: str, key: str, content: str) -> str:
    """Replaces existing <meta> tag or injects before </head> if missing."""
    escaped_content = html_lib.escape(content, quote=True)
    pattern = rf'<meta\s+{attr}=["\']{re.escape(key)}["\'][^>]*>'
    if re.search(pattern, html, flags=re.IGNORECASE):
        return re.sub(pattern, f'<meta {attr}="{key}" content="{escaped_content}" />', html, count=1, flags=re.IGNORECASE)
    return html.replace("</head>", f'  <meta {attr}="{key}" content="{escaped_content}" />\n</head>')


HOME_POPULAR_CITIES = [
    {"name": "Mumbai", "slug": "mumbai"},
    {"name": "Bangalore", "slug": "bangalore"},
    {"name": "Pune", "slug": "pune"},
    {"name": "Delhi NCR", "slug": "delhi-ncr"},
    {"name": "Hyderabad", "slug": "hyderabad"},
    {"name": "Chennai", "slug": "chennai"},
    {"name": "Ahmedabad", "slug": "ahmedabad"},
    {"name": "Kolkata", "slug": "kolkata"},
    {"name": "Palwal", "slug": "palwal"},
    {"name": "Faridabad", "slug": "faridabad"},
    {"name": "Gurugram", "slug": "gurugram"},
    {"name": "Noida", "slug": "noida"},
]


_html_cache = {
    "path": None,
    "mtime": 0.0,
    "content": None
}


def load_base_index_html() -> str:
    """
    Finds and reads built frontend index.html from server root or local repo.
    Re-reads the file whenever its modification time changes, ensuring newly
    deployed frontend bundles/asset hashes are picked up immediately without server restarts.
    """
    cached_path = _html_cache.get("path")
    if cached_path and os.path.isfile(cached_path):
        try:
            mtime = os.path.getmtime(cached_path)
            if mtime == _html_cache.get("mtime") and _html_cache.get("content") is not None:
                return _html_cache["content"]
            with open(cached_path, "r", encoding="utf-8") as f:
                content = f.read()
                _html_cache["mtime"] = mtime
                _html_cache["content"] = content
                return content
        except Exception:
            pass

    candidates = [
        os.getenv("FRONTEND_INDEX_PATH"),
        "/var/www/tradecall/index.html",
        str(Path(__file__).resolve().parents[3] / "brokerage-app-frontend" / "dist" / "index.html"),
        str(Path(__file__).resolve().parents[3] / "brokerage-app-frontend" / "index.html"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                mtime = os.path.getmtime(path)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    _html_cache["path"] = path
                    _html_cache["mtime"] = mtime
                    _html_cache["content"] = content
                    return content
            except Exception:
                pass

    return """<!DOCTYPE html>
<html lang="en-IN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>TradeCall India - Free Property N Related Business Listing</title>
  <meta name="description" content="Buy, sell or rent flats, plots, houses and commercial property with zero brokerage on TradeCall India." />
</head>
<body>
  <div id="root"></div>
</body>
</html>"""


def get_city_approved_listings(city_slug: str, city_name: str, db: Session) -> List[Listing]:
    """Finds all approved listings belonging to a city, matching location text or form_data city."""
    norm_slug = slugify_city(city_slug)
    norm_city = city_name.lower()

    all_approved = (
        db.query(Listing)
        .filter(Listing.status == "approved")
        .order_by(Listing.is_featured.desc(), Listing.id.desc())
        .all()
    )

    matched = []
    for l in all_approved:
        is_match = False
        if l.location:
            low = l.location.lower()
            if norm_city in low or norm_slug in low:
                is_match = True
            else:
                parts = [p.strip() for p in l.location.split(",") if p.strip()]
                raw = parts[-2] if len(parts) >= 3 else (parts[0] if parts else None)
                if raw and slugify_city(raw) == norm_slug:
                    is_match = True
        if not is_match and isinstance(l.form_data, dict):
            raw = l.form_data.get("city")
            if raw and (slugify_city(raw) == norm_slug or norm_city in str(raw).lower()):
                is_match = True
        if is_match:
            matched.append(l)

    return matched


def get_active_cities_summary(db: Session) -> List[Dict[str, Any]]:
    """Returns cities that have >= 1 approved listing, sorted by listing count descending."""
    all_approved = (
        db.query(Listing.location, Listing.form_data)
        .filter(Listing.status == "approved")
        .all()
    )
    city_counts: Dict[str, Dict[str, Any]] = {}
    for loc_str, f_data in all_approved:
        raw = None
        if isinstance(f_data, dict) and f_data.get("city"):
            raw = f_data.get("city")
        elif loc_str:
            parts = [p.strip() for p in loc_str.split(",") if p.strip()]
            raw = parts[-2] if len(parts) >= 3 else (parts[0] if parts else None)
        if raw:
            slug = slugify_city(raw)
            if slug:
                if slug not in city_counts:
                    display = get_city_display_name(slug, db) or raw.strip().title()
                    city_counts[slug] = {"name": display, "slug": slug, "count": 0}
                city_counts[slug]["count"] += 1
    return sorted(city_counts.values(), key=lambda x: (-x["count"], x["name"]))


@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_home_page(db: Session = Depends(get_db)):
    """
    Renders base index.html with server-injected canonical, homepage title,
    meta tags, and crawlable SSR fallback for popular cities with active listings inside #root.
    """
    base_html = load_base_index_html()
    title = "TradeCall India - Buy, Rent & Sell Property in Palwal & NCR"
    description = (
        "Buy, sell or rent flats, plots, houses and commercial property in Palwal, "
        "Faridabad and the NCR with zero brokerage. Contact verified owners directly "
        "and find local businesses on TradeCall India."
    )
    canonical = f"{BASE_URL}/"
    h1_text = "Buy, Rent & Sell Property in Palwal & NCR"

    html = base_html

    # 1. Replace or inject <title>
    if re.search(r"<title>.*?</title>", html, flags=re.DOTALL):
        html = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1, flags=re.DOTALL)
    else:
        html = html.replace("<head>", f"<head>\n  <title>{title}</title>")

    # 2. Canonical (guaranteed exactly one, replaces any existing)
    html = set_or_replace_canonical(html, canonical)

    # 3. Meta description
    if re.search(r'<meta\s+name=["\']description["\']', html):
        html = re.sub(
            r'<meta\s+name=["\']description["\']\s+content=["\'][^"\']*["\']\s*/?>',
            f'<meta name="description" content="{description}" />',
            html,
            count=1
        )
    else:
        html = html.replace("</head>", f'  <meta name="description" content="{description}" />\n</head>')

    # 4. OpenGraph and Twitter tags
    html = set_or_replace_meta(html, "property", "og:title", title)
    html = set_or_replace_meta(html, "property", "og:description", description)
    html = set_or_replace_meta(html, "property", "og:url", canonical)
    html = set_or_replace_meta(html, "name", "twitter:title", title)
    html = set_or_replace_meta(html, "name", "twitter:description", description)

    # 5. Inject SSR fallback with single <h1> and Popular cities links inside <div id="root">
    # Only list cities with at least 1 listing, sorted by listing count
    active_popular = get_active_cities_summary(db)
    city_links = "\n".join(
        f'          <li><a href="/properties/{c["slug"]}">Properties in {c["name"]}</a></li>'
        for c in active_popular[:12]
    )
    root_ssr = f"""<div id="root">
    <div class="ssr-fallback" style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;">
      <header>
        <h1>{h1_text}</h1>
        <p>{description}</p>
      </header>
      <section>
        <h2>Properties in Popular Cities</h2>
        <nav aria-label="Popular Cities">
          <ul>
{city_links}
          </ul>
        </nav>
      </section>
    </div>
  </div>"""

    html = re.sub(r'<div\s+id=["\']root["\'][^>]*>.*?</div>', root_ssr, html, count=1, flags=re.DOTALL)
    return HTMLResponse(content=html, status_code=status.HTTP_200_OK, media_type="text/html")


@router.api_route("/properties/{city_slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_city_properties_page(city_slug: str, db: Session = Depends(get_db)):
    """
    Renders index.html with server-injected meta tags, title, canonical,
    and BreadcrumbList JSON-LD for the requested city.
    Unknown city returns 404 status code for both GET and HEAD.
    Cities with zero listings receive <meta name="robots" content="noindex, follow">.
    Cities with at least 1 listing are indexable and display the exact listing count and crawlable links.
    """
    city_name = get_city_display_name(city_slug, db=db)
    base_html = load_base_index_html()

    if not city_name:
        # Unknown city -> 404 status
        not_found_html = re.sub(
            r"<title>.*?</title>",
            "<title>404 - Page Not Found | Tradecall</title>",
            base_html,
            count=1,
            flags=re.DOTALL
        )
        return HTMLResponse(
            content=not_found_html,
            status_code=status.HTTP_404_NOT_FOUND,
            media_type="text/html"
        )

    norm_slug = slugify_city(city_slug)
    matched_listings = get_city_approved_listings(norm_slug, city_name, db)
    listing_count = len(matched_listings)
    has_listings = listing_count > 0

    title = f"Properties in {city_name} | Buy, Rent & Commercial | Tradecall"
    if has_listings:
        description = f"{listing_count} properties for sale and rent in {city_name}. Explore verified residential and commercial properties with zero brokerage on TradeCall India."
    else:
        description = f"Looking for properties in {city_name}? Explore verified properties in nearby cities with zero brokerage on TradeCall India or post a free listing."
    canonical = f"{BASE_URL}/properties/{norm_slug}"

    breadcrumb_ld = f"""  <!-- City Breadcrumb Schema -->
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      {{
        "@type": "ListItem",
        "position": 1,
        "name": "Home",
        "item": "{BASE_URL}/"
      }},
      {{
        "@type": "ListItem",
        "position": 2,
        "name": "Properties in {city_name}",
        "item": "{canonical}"
      }}
    ]
  }}
  </script>"""

    html = base_html

    # 1. Replace or inject <title>
    if re.search(r"<title>.*?</title>", html, flags=re.DOTALL):
        html = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1, flags=re.DOTALL)
    else:
        html = html.replace("<head>", f"<head>\n  <title>{title}</title>")

    # 2. Replace or inject meta description
    if re.search(r'<meta\s+name=["\']description["\']', html):
        html = re.sub(
            r'<meta\s+name=["\']description["\']\s+content=["\'][^"\']*["\']\s*/?>',
            f'<meta name="description" content="{description}" />',
            html,
            count=1
        )
    else:
        html = html.replace("</head>", f'  <meta name="description" content="{description}" />\n</head>')

    # 3. Canonical (guaranteed exactly one, replaces any existing)
    html = set_or_replace_canonical(html, canonical)

    # 4. Robots meta tag: index, follow if >= 1 listing, else noindex, follow
    robots_content = "index, follow" if has_listings else "noindex, follow"
    html = set_or_replace_meta(html, "name", "robots", robots_content)

    # 5. OpenGraph and Twitter tags
    html = set_or_replace_meta(html, "property", "og:title", title)
    html = set_or_replace_meta(html, "property", "og:description", description)
    html = set_or_replace_meta(html, "property", "og:url", canonical)
    html = set_or_replace_meta(html, "name", "twitter:title", title)
    html = set_or_replace_meta(html, "name", "twitter:description", description)

    # 6. Inject BreadcrumbList JSON-LD before </head>
    html = html.replace("</head>", f"{breadcrumb_ld}\n</head>")

    # 7. Inject single <h1> and crawlable content inside <div id="root">
    if has_listings:
        items = []
        for l in matched_listings[:15]:
            l_path = get_listing_path(l.id, l.title, l.location, l.form_data)
            p_str = format_price(float(l.price)) if l.price else ""
            title_text = html_lib.escape(l.title or "Property")
            loc_text = html_lib.escape(l.location or city_name)
            price_tag = f" - <strong>{html_lib.escape(p_str)}</strong>" if p_str else ""
            items.append(f'<li><a href="{l_path}">{title_text}</a>{price_tag} in {loc_text}</li>')
        listings_markup = "\n          ".join(items)

        intro_line = f"{listing_count} properties for sale and rent in {html_lib.escape(city_name)}"
        root_ssr = f"""<div id="root">
    <div class="ssr-fallback" style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;">
      <main class="city-ssr-wrap">
        <h1>Properties in {html_lib.escape(city_name)}</h1>
        <p class="city-lead">{intro_line}. Explore verified residential and commercial properties with zero brokerage on TradeCall India.</p>
        <section class="city-listings-section">
          <h2>Verified Listings in {html_lib.escape(city_name)}</h2>
          <ul class="city-listings-links">
            {listings_markup}
          </ul>
        </section>
      </main>
    </div>
  </div>"""
    else:
        active_cities = get_active_cities_summary(db)
        nearby_markup = "\n          ".join(
            f'<li><a href="/properties/{c["slug"]}">Properties in {html_lib.escape(c["name"])}</a> ({c["count"]} listings)</li>'
            for c in active_cities[:8]
        )
        root_ssr = f"""<div id="root">
    <div class="ssr-fallback" style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;">
      <main class="city-ssr-wrap">
        <h1>Properties in {html_lib.escape(city_name)}</h1>
        <p class="city-lead">Currently there are 0 active property listings in {html_lib.escape(city_name)}. Explore verified listings in nearby active cities or be the first to post a listing in {html_lib.escape(city_name)}.</p>
        <section class="city-empty-section">
          <h2>Cities with Verified Listings</h2>
          <ul class="city-listings-links">
            {nearby_markup}
          </ul>
          <div class="city-post-cta" style="margin-top: 20px;">
            <a href="/post-listing" class="btn-post-free">Post Free Listing in {html_lib.escape(city_name)}</a>
          </div>
        </section>
      </main>
    </div>
  </div>"""

    html = re.sub(r'<div\s+id=["\']root["\'][^>]*>.*?</div>', root_ssr, html, count=1, flags=re.DOTALL)

    return HTMLResponse(content=html, status_code=status.HTTP_200_OK, media_type="text/html")
