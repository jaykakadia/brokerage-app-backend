import html as html_lib
import json
import math
import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.db.models.listing import Listing
from app.db.models.page_metadata import PageMetadata
from app.core.cities import get_city_display_name, slugify_city, MIN_HUB_LISTINGS
from app.routers.sitemap import get_listing_path

router = APIRouter(tags=["City Pages"])

BASE_URL = "https://tradecall.in"
PAGE_SIZE = 15


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


def set_or_replace_rel_links(html: str, prev_url: Optional[str], next_url: Optional[str]) -> str:
    """Injects or replaces rel=prev and rel=next link tags in head."""
    html = re.sub(r'<link\b[^>]*\brel=["\'](prev|next)["\'][^>]*>', '', html, flags=re.IGNORECASE)
    rel_tags = []
    if prev_url:
        rel_tags.append(f'  <link rel="prev" href="{prev_url}" />')
    if next_url:
        rel_tags.append(f'  <link rel="next" href="{next_url}" />')
    if rel_tags:
        return html.replace("</head>", "\n".join(rel_tags) + "\n</head>")
    return html


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
  <title>Property in Palwal, Faridabad & NCR | TradeCall India</title>
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


def compute_price_stats(listings: List[Listing]) -> Dict[str, Optional[float]]:
    """Calculates min, median, and max prices from a list of listings."""
    prices = [float(l.price) for l in listings if l.price and float(l.price) > 0]
    if not prices:
        return {"min": None, "median": None, "max": None}
    prices.sort()
    n = len(prices)
    min_p = prices[0]
    max_p = prices[-1]
    median_p = prices[n // 2] if n % 2 == 1 else (prices[n // 2 - 1] + prices[n // 2]) / 2.0
    return {"min": min_p, "median": median_p, "max": max_p}


def generate_city_intro(city_name: str, total_count: int, stats: Dict[str, Optional[float]]) -> str:
    """Generates 150-300 words of intro copy tailored to the city real estate hub."""
    min_str = format_price(stats["min"]) if stats["min"] else "budget-friendly rates"
    med_str = format_price(stats["median"]) if stats["median"] else "competitive market rates"
    max_str = format_price(stats["max"]) if stats["max"] else "premium valuations"

    return (
        f"Welcome to TradeCall India's dedicated real estate marketplace for {city_name}. "
        f"Whether you are planning to buy your dream residential home, lease commercial office space, "
        f"or invest in high-growth industrial and agricultural plots, {city_name} presents exceptional opportunities "
        f"across prime residential sectors, bustling commercial markets, and upcoming development corridors. "
        f"TradeCall India connects property seekers directly with verified owners, builders, and trusted local associates, "
        f"providing a 100% transparent experience with zero brokerage commissions.\n\n"
        f"At present, our platform showcases {total_count} active, verified property listings in {city_name}. "
        f"Property prices in {city_name} range from {min_str} for entry-level apartments and compact plots up to {max_str} "
        f"for expansive luxury houses, commercial buildings, and prime acreage, with a median listing price of approximately {med_str}. "
        f"Every property profile on TradeCall India includes authentic dimensions, locality highlights, owner contact channels, "
        f"and clear pricing to help you make informed decisions. Explore our curated listings below or list your property for free to "
        f"reach thousands of genuine buyers and tenants across Haryana and Delhi NCR."
    )


# --- ROUTE HANDLERS ---

@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_home_page(db: Session = Depends(get_db)):
    """
    Renders base index.html with homepage title, meta tags, canonical,
    Organization + WebSite Schema, and crawlable SSR markup inside #root.
    """
    base_html = load_base_index_html()
    title = "Property in Palwal, Faridabad & NCR | TradeCall India"
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

    # 2. Canonical
    html = set_or_replace_canonical(html, canonical)

    # 3. Meta description
    escaped_desc = html_lib.escape(description, quote=True)
    if re.search(r'<meta\s+name=["\']description["\']', html):
        html = re.sub(
            r'<meta\s+name=["\']description["\']\s+content=["\'][^"\']*["\']\s*/?>',
            f'<meta name="description" content="{escaped_desc}" />',
            html,
            count=1
        )
    else:
        html = html.replace("</head>", f'  <meta name="description" content="{escaped_desc}" />\n</head>')

    # 4. Robots & OpenGraph
    html = set_or_replace_meta(html, "name", "robots", "index, follow")
    html = set_or_replace_meta(html, "property", "og:title", title)
    html = set_or_replace_meta(html, "property", "og:description", description)
    html = set_or_replace_meta(html, "property", "og:url", canonical)
    html = set_or_replace_meta(html, "name", "twitter:title", title)
    html = set_or_replace_meta(html, "name", "twitter:description", description)

    # 5. Schema.org Organization + WebSite
    org_schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": f"{BASE_URL}/#organization",
                "name": "TradeCall India",
                "url": BASE_URL,
                "telephone": "+91 9992292828",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "Village Joharkhera, PO Mandkola",
                    "addressLocality": "Palwal",
                    "addressRegion": "Haryana",
                    "postalCode": "121102",
                    "addressCountry": "IN"
                }
            },
            {
                "@type": "WebSite",
                "@id": f"{BASE_URL}/#website",
                "url": BASE_URL,
                "name": "TradeCall India",
                "publisher": {"@id": f"{BASE_URL}/#organization"}
            }
        ]
    }
    schema_tag = f"""  <script type="application/ld+json">\n{json.dumps(org_schema, indent=2)}\n  </script>"""
    html = html.replace("</head>", f"{schema_tag}\n</head>")

    # 6. Gather active indexable city hubs (>= MIN_HUB_LISTINGS)
    active_summary = get_active_cities_summary(db)
    indexable_hubs = [c for c in active_summary if c["count"] >= MIN_HUB_LISTINGS]
    hub_links = "\n".join(
        f'          <li><a href="/properties/{c["slug"]}">Properties in {c["name"]} ({c["count"]} listings)</a></li>'
        for c in indexable_hubs
    )

    # 7. Gather latest approved listings
    latest_listings = (
        db.query(Listing)
        .filter(Listing.status == "approved")
        .order_by(Listing.id.desc())
        .limit(10)
        .all()
    )
    latest_items = []
    for l in latest_listings:
        l_path = get_listing_path(l.id, l.title, l.location, l.form_data)
        p_str = format_price(float(l.price)) if l.price else ""
        price_tag = f" - <strong>{html_lib.escape(p_str)}</strong>" if p_str else ""
        latest_items.append(f'<li><a href="{l_path}">{html_lib.escape(l.title or "Property")}</a>{price_tag} in {html_lib.escape(l.location or "NCR")}</li>')
    latest_markup = "\n            ".join(latest_items)

    verification_note = "All listings on TradeCall India are verified directly with property owners and local associates to ensure genuine, zero-brokerage deals across Palwal, Faridabad, and Delhi NCR."

    root_ssr = f"""<div id="root">
    <div class="ssr-fallback" style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;">
      <header>
        <h1>{h1_text}</h1>
        <p>{description}</p>
        <p class="verification-note"><strong>Verification Guarantee:</strong> {verification_note}</p>
      </header>
      <section>
        <h2>Indexable City Hubs</h2>
        <nav aria-label="City Hubs">
          <ul>
{hub_links}
          </ul>
        </nav>
      </section>
      <section>
        <h2>Explore Property Types</h2>
        <ul>
          <li>Residential Apartments & Builder Floors</li>
          <li>Independent Houses & Villas</li>
          <li>Commercial Shops & Office Spaces</li>
          <li>Industrial Plots & Sheds</li>
          <li>Agricultural Land & Farmhouses</li>
        </ul>
      </section>
      <section>
        <h2>Latest Verified Property Listings</h2>
        <ul>
            {latest_markup}
        </ul>
      </section>
    </div>
  </div>"""

    html = re.sub(r'<div\s+id=["\']root["\'][^>]*>.*?</div>', root_ssr, html, count=1, flags=re.DOTALL)
    return HTMLResponse(content=html, status_code=status.HTTP_200_OK, media_type="text/html")


@router.api_route("/properties/{city_slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_city_properties_page(
    city_slug: str,
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db)
):
    """
    Renders index.html with server-injected meta tags, title, pagination canonical/prev/next,
    150-300 words intro copy, price stats, ItemList + BreadcrumbList JSON-LD, and crawlable pagination nav.
    """
    city_name = get_city_display_name(city_slug, db=db)
    base_html = load_base_index_html()

    if not city_name:
        # Unknown city -> 404 status
        not_found_html = re.sub(
            r"<title>.*?</title>",
            "<title>404 - Page Not Found | TradeCall India</title>",
            base_html,
            count=1,
            flags=re.DOTALL
        )
        not_found_html = set_or_replace_meta(not_found_html, "name", "robots", "noindex, follow")
        not_found_html = re.sub(r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>', '', not_found_html, flags=re.IGNORECASE)
        return HTMLResponse(content=not_found_html, status_code=status.HTTP_404_NOT_FOUND, media_type="text/html")

    norm_slug = slugify_city(city_slug)
    matched_listings = get_city_approved_listings(norm_slug, city_name, db)
    total_listings = len(matched_listings)
    has_listings = total_listings > 0

    total_pages = max(1, math.ceil(total_listings / PAGE_SIZE))

    # page > total_pages (and total > 0) -> 404 + noindex
    if page > total_pages and total_listings > 0:
        not_found_html = re.sub(
            r"<title>.*?</title>",
            f"<title>Page {page} Not Found - Properties in {html_lib.escape(city_name)} | TradeCall India</title>",
            base_html,
            count=1,
            flags=re.DOTALL
        )
        not_found_html = set_or_replace_meta(not_found_html, "name", "robots", "noindex, follow")
        not_found_html = re.sub(r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>', '', not_found_html, flags=re.IGNORECASE)
        return HTMLResponse(content=not_found_html, status_code=status.HTTP_404_NOT_FOUND, media_type="text/html")

    # Page slice
    start_idx = (page - 1) * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    current_page_listings = matched_listings[start_idx:end_idx]

    # Canonical & Prev/Next
    if page == 1:
        canonical = f"{BASE_URL}/properties/{norm_slug}"
    else:
        canonical = f"{BASE_URL}/properties/{norm_slug}?page={page}"

    prev_url = f"{BASE_URL}/properties/{norm_slug}" if page == 2 else (f"{BASE_URL}/properties/{norm_slug}?page={page - 1}" if page > 2 else None)
    next_url = f"{BASE_URL}/properties/{norm_slug}?page={page + 1}" if page < total_pages else None

    # Robots: if total_listings < MIN_HUB_LISTINGS or extra filter params exist -> noindex, follow; else index, follow
    extra_filters = any(k not in ("page",) for k in request.query_params.keys())
    if total_listings < MIN_HUB_LISTINGS or extra_filters:
        robots_content = "noindex, follow"
    else:
        robots_content = "index, follow"

    # Metadata customization or defaults
    page_suffix = f" - Page {page}" if page > 1 else ""
    title = f"Properties in {city_name}{page_suffix} | Buy, Rent & Commercial | TradeCall India"
    if has_listings:
        description = f"{total_listings} properties for sale and rent in {city_name}. Explore verified residential and commercial properties with zero brokerage on TradeCall India.{page_suffix}"
    else:
        description = f"Looking for properties in {city_name}? Explore verified properties in nearby cities with zero brokerage on TradeCall India or post a free listing."

    # Compute price statistics
    price_stats = compute_price_stats(matched_listings)
    intro_copy = generate_city_intro(city_name, total_listings, price_stats)

    # Extract unique localities for locality links
    localities = set()
    for l in matched_listings:
        if l.location:
            parts = [p.strip() for p in l.location.split(",") if p.strip()]
            if parts and parts[0] != city_name:
                localities.add(parts[0])
        if isinstance(l.form_data, dict) and l.form_data.get("locality"):
            loc_val = l.form_data.get("locality").strip()
            if loc_val and loc_val != city_name:
                localities.add(loc_val)
    sorted_localities = sorted(list(localities))[:12]
    locality_items = [f'<li><span class="locality-tag">{html_lib.escape(loc)}</span></li>' for loc in sorted_localities]
    localities_markup = "\n            ".join(locality_items) if locality_items else "<li><span>All Sectors</span></li>"

    # Schema JSON-LD: BreadcrumbList + ItemList
    breadcrumb_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": f"{BASE_URL}/"
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": f"Properties in {city_name}",
                "item": f"{BASE_URL}/properties/{norm_slug}"
            }
        ]
    }

    item_list_elements = []
    for idx, l in enumerate(current_page_listings, start=1):
        l_path = get_listing_path(l.id, l.title, l.location, l.form_data)
        item_list_elements.append({
            "@type": "ListItem",
            "position": (page - 1) * PAGE_SIZE + idx,
            "name": l.title or f"Property in {city_name}",
            "url": f"{BASE_URL}{l_path}"
        })

    item_list_ld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"Properties in {city_name}{page_suffix}",
        "numberOfItems": len(item_list_elements),
        "itemListElement": item_list_elements
    }

    schemas_code = f"""  <!-- Breadcrumbs & ItemList Schemas -->
  <script type="application/ld+json">
{json.dumps(breadcrumb_ld, indent=2)}
  </script>
  <script type="application/ld+json">
{json.dumps(item_list_ld, indent=2)}
  </script>"""

    html = base_html

    # 1. Title
    html = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1, flags=re.DOTALL)

    # 2. Meta description
    escaped_desc = html_lib.escape(description, quote=True)
    if re.search(r'<meta\s+name=["\']description["\']', html):
        html = re.sub(
            r'<meta\s+name=["\']description["\']\s+content=["\'][^"\']*["\']\s*/?>',
            f'<meta name="description" content="{escaped_desc}" />',
            html,
            count=1
        )
    else:
        html = html.replace("</head>", f'  <meta name="description" content="{escaped_desc}" />\n</head>')

    # 3. Canonical & Rel prev/next
    html = set_or_replace_canonical(html, canonical)
    html = set_or_replace_rel_links(html, prev_url, next_url)

    # 4. Robots meta tag
    html = set_or_replace_meta(html, "name", "robots", robots_content)

    # 5. OpenGraph & Twitter
    html = set_or_replace_meta(html, "property", "og:title", title)
    html = set_or_replace_meta(html, "property", "og:description", description)
    html = set_or_replace_meta(html, "property", "og:url", canonical)
    html = set_or_replace_meta(html, "name", "twitter:title", title)
    html = set_or_replace_meta(html, "name", "twitter:description", description)

    # 6. Inject Schemas
    html = html.replace("</head>", f"{schemas_code}\n</head>")

    # 7. Build Pagination nav
    pagination_links = []
    for p in range(1, total_pages + 1):
        p_url = f"/properties/{norm_slug}" if p == 1 else f"/properties/{norm_slug}?page={p}"
        active_cls = ' class="active"' if p == page else ''
        pagination_links.append(f'<li><a href="{p_url}"{active_cls}>{p}</a></li>')
    pagination_nav = f"""<nav aria-label="Pagination" class="pagination-nav">
          <ul class="pagination-links" style="display: flex; list-style: none; gap: 8px;">
            {chr(10).join(pagination_links)}
          </ul>
        </nav>"""

    # Price summary formatted strings
    min_p_str = format_price(price_stats["min"]) or "N/A"
    med_p_str = format_price(price_stats["median"]) or "N/A"
    max_p_str = format_price(price_stats["max"]) or "N/A"

    if has_listings:
        items = []
        for l in current_page_listings:
            l_path = get_listing_path(l.id, l.title, l.location, l.form_data)
            p_str = format_price(float(l.price)) if l.price else ""
            title_text = html_lib.escape(l.title or "Property")
            loc_text = html_lib.escape(l.location or city_name)
            price_tag = f" - <strong>{html_lib.escape(p_str)}</strong>" if p_str else ""
            items.append(f'<li><a href="{l_path}">{title_text}</a>{price_tag} in {loc_text}</li>')
        listings_markup = "\n          ".join(items)

        root_ssr = f"""<div id="root">
    <div class="ssr-fallback" style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;">
      <main class="city-ssr-wrap">
        <h1>Properties in {html_lib.escape(city_name)}{page_suffix}</h1>
        <div class="city-price-summary">
          <p><strong>Price Summary:</strong> Min: {min_p_str} | Median: {med_p_str} | Max: {max_p_str}</p>
        </div>
        <div class="city-intro-copy">
          <p>{html_lib.escape(intro_copy).replace(chr(10)+chr(10), '</p><p>')}</p>
        </div>
        <section class="city-localities-section">
          <h2>Popular Localities in {html_lib.escape(city_name)}</h2>
          <ul class="locality-links">
            {localities_markup}
          </ul>
        </section>
        <section class="city-listings-section">
          <h2>Verified Listings in {html_lib.escape(city_name)} (Showing {len(current_page_listings)} of {total_listings})</h2>
          <ul class="city-listings-links">
            {listings_markup}
          </ul>
        </section>
        {pagination_nav}
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
