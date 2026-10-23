import html as html_lib
import json
import math
import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, Request, status, HTTPException
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


def set_or_replace_hreflang(html: str, en_url: str, hi_url: Optional[str] = None) -> str:
    """Injects or replaces hreflang link tags in head (en-IN, hi-IN, and x-default)."""
    html = re.sub(r'<link\b[^>]*\bhreflang=["\'][^"\']*["\'][^>]*>', '', html, flags=re.IGNORECASE)
    tags = [
        f'  <link rel="alternate" hreflang="en-IN" href="{en_url}" />',
        f'  <link rel="alternate" hreflang="x-default" href="{en_url}" />',
    ]
    if hi_url:
        tags.insert(1, f'  <link rel="alternate" hreflang="hi-IN" href="{hi_url}" />')
    return html.replace("</head>", "\n".join(tags) + "\n</head>")


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

    # 5. Schema.org Organization + WebSite + FAQPage
    homepage_faqs = [
        {
            "question": "How does TradeCall India ensure zero brokerage on property transactions?",
            "answer": "TradeCall India directly connects verified property owners, buyers, and tenants without intermediaries. You get direct contact access to genuine owners and sellers without paying any brokerage or commission."
        },
        {
            "question": "How are property listings verified on TradeCall India?",
            "answer": "Every listing undergoes an initial verification process checking owner contact details, property specifics, and photos. Verified listings are marked with our verified badge after confirming details with the owner."
        },
        {
            "question": "Can I list my property for free on TradeCall India?",
            "answer": "Yes, genuine owners and individuals can post their property for sale or rent completely free of charge. You can list residential flats, houses, plots, agricultural land, or commercial properties."
        },
        {
            "question": "What types of properties can I find in Palwal and NCR on TradeCall India?",
            "answer": "You can find residential apartments, builder floors, independent houses, residential plots, commercial shops, office spaces, and agricultural or industrial land across Palwal, Faridabad, Gurugram, and neighboring NCR corridors."
        },
        {
            "question": "How do I contact property owners or local businesses on TradeCall India?",
            "answer": "Each property and business listing features direct call and WhatsApp buttons. Once you click to reveal contact details, you can speak or chat directly with the owner or business representative."
        },
        {
            "question": "Where is TradeCall India located and how can I get support?",
            "answer": "TradeCall India is based in Village Joharkhera, PO Mandkola, Palwal, Haryana 121102. For customer assistance, you can call or WhatsApp our support desk at +91 9992292828."
        }
    ]

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
            },
            {
                "@type": "FAQPage",
                "@id": f"{BASE_URL}/#faq",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": f["question"],
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": f["answer"]
                        }
                    }
                    for f in homepage_faqs
                ]
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

    faq_markup = "\n".join(
        f'          <dt style="font-weight: 700; margin-top: 12px;">{html_lib.escape(f["question"])}</dt>\n'
        f'          <dd style="margin-left: 0; margin-bottom: 8px; color: #4b5563;">{html_lib.escape(f["answer"])}</dd>'
        for f in homepage_faqs
    )

    verification_note = "All listings on TradeCall India undergo seller contact verification and quality review to ensure authentic, zero-brokerage deals across Palwal, Faridabad, and Delhi NCR corridor."

    root_ssr = f"""<div id="root">
    <div class="ssr-fallback" style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;">
      <header>
        <h1>{h1_text}</h1>
        <p>{description}</p>
        <section class="verification-policy" style="margin-top: 16px;">
          <h2>Verification Policy & Direct Contact Guarantee</h2>
          <p>{verification_note}</p>
          <p><strong>Customer Assistance & WhatsApp:</strong> <a href="tel:+919992292828">+91 9992292828</a></p>
          <p><strong>Registered Office:</strong> Village Joharkhera, PO Mandkola, Palwal, Haryana 121102</p>
        </section>
      </header>
      <section>
        <h2>Indexable City Real Estate Hubs</h2>
        <nav aria-label="City Hubs">
          <ul>
{hub_links}
          </ul>
        </nav>
      </section>
      <section>
        <h2>Explore Property Types in Palwal & NCR</h2>
        <ul>
          <li><a href="/properties/palwal">Residential Flats & Builder Floors</a></li>
          <li><a href="/properties/palwal">Independent Houses & Villas</a></li>
          <li><a href="/properties/palwal">Commercial Shops & Office Spaces</a></li>
          <li><a href="/properties/palwal">Industrial Plots & Land</a></li>
          <li><a href="/properties/palwal">Agricultural Land & Farmhouses</a></li>
        </ul>
      </section>
      <section>
        <h2>Frequently Asked Questions (FAQ)</h2>
        <dl>
{faq_markup}
        </dl>
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

    # Price summary formatted strings & conditional price guide
    price_count = len([l for l in matched_listings if l.price and float(l.price) > 0])
    has_enough_price_data = price_count >= 5

    min_p_str = format_price(price_stats["min"]) or "N/A"
    med_p_str = format_price(price_stats["median"]) or "N/A"
    max_p_str = format_price(price_stats["max"]) or "N/A"

    price_guide_html = f"""<div class="city-price-summary">
          <p><strong>Price Guide for {html_lib.escape(city_name)}:</strong> Starting from {min_p_str} up to {max_p_str} (Median: {med_p_str})</p>
        </div>""" if has_enough_price_data else ""

    # Real data City FAQs
    popular_loc_str = ", ".join(sorted_localities[:5]) if sorted_localities else "prime residential sectors"
    if has_enough_price_data:
        q1_ans = f"In {city_name}, verified property listings currently range from {min_p_str} up to {max_p_str}, with a median listing price of approximately {med_p_str}."
    else:
        q1_ans = f"Property prices in {city_name} vary across property types. Explore individual verified listings on TradeCall India for genuine owner pricing."

    city_faqs = [
        {
            "question": f"What are property prices like in {city_name} on TradeCall India?",
            "answer": q1_ans
        },
        {
            "question": f"Can I buy or rent property in {city_name} with zero brokerage?",
            "answer": f"Yes, all property listings in {city_name} on TradeCall India connect you directly with genuine owners and verified sellers with zero brokerage commission."
        },
        {
            "question": f"Which are the most popular localities in {city_name}?",
            "answer": f"Popular residential and commercial localities in {city_name} include {popular_loc_str}. Explore verified listings across these areas on TradeCall India."
        },
        {
            "question": f"How can I list my property in {city_name} for sale or rent?",
            "answer": f"Property owners can list free of charge in {city_name} on TradeCall India. Click 'Post Property', select {city_name}, and enter your property dimensions, photos, and contact info."
        },
        {
            "question": f"How does TradeCall India verify listings in {city_name}?",
            "answer": f"TradeCall India verifies owner contact numbers and reviews property photos and descriptions to maintain genuine listings across {city_name}."
        }
    ]

    city_faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f["answer"]
                }
            }
            for f in city_faqs
        ]
    }

    schemas_code = f"""  <!-- Breadcrumbs, ItemList & FAQPage Schemas -->
  <script type="application/ld+json">
{json.dumps(breadcrumb_ld, indent=2)}
  </script>
  <script type="application/ld+json">
{json.dumps(item_list_ld, indent=2)}
  </script>
  <script type="application/ld+json">
{json.dumps(city_faq_ld, indent=2)}
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

    # 3. Canonical & Rel prev/next & Hreflang
    html = set_or_replace_canonical(html, canonical)
    html = set_or_replace_rel_links(html, prev_url, next_url)
    hi_url = f"{BASE_URL}/hi/properties/{norm_slug}" if norm_slug in ("palwal", "faridabad") else None
    html = set_or_replace_hreflang(html, f"{BASE_URL}/properties/{norm_slug}", hi_url)

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

    city_faq_markup = "\n".join(
        f'          <dt style="font-weight: 700; margin-top: 10px;">{html_lib.escape(f["question"])}</dt>\n'
        f'          <dd style="margin-left: 0; margin-bottom: 8px; color: #4b5563;">{html_lib.escape(f["answer"])}</dd>'
        for f in city_faqs
    )

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
        {price_guide_html}
        <div class="city-intro-copy">
          <p>{html_lib.escape(intro_copy).replace(chr(10)+chr(10), '</p><p>')}</p>
        </div>
        <section class="city-localities-section">
          <h2>Popular Localities in {html_lib.escape(city_name)}</h2>
          <ul class="locality-links">
            {localities_markup}
          </ul>
        </section>
        <section class="city-types-section">
          <h2>Property Types in {html_lib.escape(city_name)}</h2>
          <ul>
            <li>Residential Apartments & Flats in {html_lib.escape(city_name)}</li>
            <li>Independent Houses & Villas in {html_lib.escape(city_name)}</li>
            <li>Plots & Residential Land in {html_lib.escape(city_name)}</li>
            <li>Commercial Shops & Offices in {html_lib.escape(city_name)}</li>
            <li>Agricultural Land & Farmland in {html_lib.escape(city_name)}</li>
          </ul>
        </section>
        <section class="city-listings-section">
          <h2>Verified Listings in {html_lib.escape(city_name)} (Showing {len(current_page_listings)} of {total_listings})</h2>
          <ul class="city-listings-links">
            {listings_markup}
          </ul>
        </section>
        {pagination_nav}
        <section class="city-faq-section" style="margin-top: 24px;">
          <h2>Frequently Asked Questions about Property in {html_lib.escape(city_name)}</h2>
          <dl>
{city_faq_markup}
          </dl>
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


# ==============================================================================
# HINDI PILOT HUBS (I-28)
# ==============================================================================

HINDI_CITY_INFO = {
    "palwal": {
        "city_hi": "पलवल",
        "title": "पलवल में प्रॉपर्टी - मकान, प्लॉट और जमीन | TradeCall India",
        "desc": "पलवल में 130+ वेरिफाइड प्रॉपर्टी खरीदें या किराए पर लें। बिना किसी ब्रोकरेज के सीधे मालिक से संपर्क करें। प्लॉट, मकान, कृषि भूमि और कमर्शियल प्रॉपर्टी।",
        "h1": "पलवल में प्रॉपर्टी (मकान, प्लॉट और जमीन)",
        "intro": "ट्रेडकॉल इंडिया (TradeCall India) पर पलवल में शून्य ब्रोकरेज (Zero Brokerage) के साथ प्रमाणित प्रॉपर्टीज खोजें। यहां आपको ओमेक्स सिटी, हुड्डा सेक्टर 2, कैलाश नगर, पंचवटी और दिल्ली-मथुरा नेशनल हाईवे (NH-19) के पास सीधे मालिकों द्वारा लिस्टेड प्लॉट्स, स्वतंत्र मकान और कृषि भूमि मिलती है।",
        "prop_types": [
            "पलवल में आवासीय मकान और विला",
            "पलवल में कमर्शियल दुकानें और ऑफिस स्पेस",
            "पलवल में आवासीय प्लॉट और जमीन",
            "पलवल में कृषि भूमि और फार्म हाउस"
        ],
        "faqs": [
            {
                "question": "पलवल में प्रॉपर्टी की औसत कीमतें क्या हैं?",
                "answer": "पलवल में आवासीय प्लॉट्स लगभग ₹15,000 से ₹45,000 प्रति गज तक उपलब्ध हैं। स्वतंत्र मकान और विला ₹30 लाख से ₹1.5 करोड़ के बीच मिलते हैं।"
            },
            {
                "question": "क्या ट्रेडकॉल इंडिया पर बिना दलाली के सीधे मालिक से प्रॉपर्टी मिल सकती है?",
                "answer": "जी हां, ट्रेडकॉल इंडिया पर सभी लिस्टिंग्स में आपको सीधे विक्रेता या प्रॉपर्टी मालिक का मोबाइल नंबर मिलता है, जिससे आपको कोई ब्रोकरेज या कमीशन नहीं देना पड़ता।"
            },
            {
                "question": "पलवल में रहने के लिए सबसे अच्छे इलाके कौन से हैं?",
                "answer": "ओमेक्स सिटी (फेज 1 व 2), हुड्डा सेक्टर 2, कैलाश नगर, पंचवटी कॉलोनी और न्यू एक्सटेंशन कॉलोनी पलवल के सबसे पसंदीदा और सुरक्षित आवासीय क्षेत्र हैं।"
            },
            {
                "question": "हरियाणा में प्लॉट खरीदते समय कौन से दस्तावेज जांचने चाहिए?",
                "answer": "जमाबंदी (नकल), इंतकाल (दाखिल खारिज), 30 साल की सेल डीड की चेन और डीटीसीपी (DTCP) सेक्शन 7A अनापत्ति प्रमाण पत्र (NOC) की पुष्टि अवश्य करें।"
            }
        ]
    },
    "faridabad": {
        "city_hi": "फरीदाबाद",
        "title": "फरीदाबाद में प्रॉपर्टी - फ्लैट, विला और प्लॉट | TradeCall India",
        "desc": "फरीदाबाद और ग्रेटर फरीदाबाद (नहरपार) में 30+ वेरिफाइड प्रॉपर्टीज। बिना किसी ब्रोकरेज के सीधे मालिक से संपर्क करें। फ्लैट, बिल्डर फ्लोर और प्लॉट्स।",
        "h1": "फरीदाबाद में प्रॉपर्टी (फ्लैट, विला और प्लॉट)",
        "intro": "फरीदाबाद, ग्रेटर फरीदाबाद (नहरपार) और एनआईटी में शून्य ब्रोकरेज के साथ प्रमाणित प्रॉपर्टीज खोजें। यहां आपको 1 BHK, 2 BHK, 3 BHK+ फ्लैट्स, लग्जरी बिल्डर फ्लोर्स और रेसिडेंशियल प्लॉट्स सीधे मालिकों से मिलते हैं।",
        "prop_types": [
            "फरीदाबाद में बिल्डर फ्लोर और फ्लैट्स",
            "ग्रेटर फरीदाबाद (नहरपार) में आवासीय प्लॉट्स",
            "फरीदाबाद में स्वतंत्र कोठी और विला",
            "एनआईटी और सेक्टर 85 में कमर्शियल दुकानें"
        ],
        "faqs": [
            {
                "question": "फरीदाबाद में फ्लैट या बिल्डर फ्लोर की कीमतें क्या हैं?",
                "answer": "फरीदाबाद में 2 BHK व 3 BHK बिल्डर फ्लोर्स ₹40 लाख से ₹1.5 करोड़ तक और लग्जरी अपार्टमेंट्स ₹2 करोड़ से अधिक में उपलब्ध हैं।"
            },
            {
                "question": "क्या ट्रेडकॉल पर फरीदाबाद की प्रॉपर्टीज पर ब्रोकरेज लगती है?",
                "answer": "नहीं, ट्रेडकॉल इंडिया जीरो ब्रोकरेज मॉडल पर काम करता है। खरीदार सीधे मालिक या अधिकृत एसोसिएट से बात कर सकते हैं।"
            },
            {
                "question": "ग्रेटर फरीदाबाद (नहरपार) में कनेक्टिविटी कैसी है?",
                "answer": "ग्रेटर फरीदाबाद दिल्ली-मुंबई एक्सप्रेसवे, बाईपास रोड और वायलेट लाइन मेट्रो से सीधा जुड़ा हुआ है, जिससे दिल्ली और गुड़गांव आवागमन बहुत सुगम है।"
            }
        ]
    }
}


@router.api_route("/hi/properties/{city_slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_hindi_city_properties_page(
    city_slug: str,
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db)
):
    """
    Renders Hindi Pilot City Hub (Palwal & Faridabad) with natural Hindi translation,
    reciprocal hreflang tags (en-IN, hi-IN, x-default), Hindi Breadcrumbs, ItemList and FAQPage schemas.
    """
    norm_slug = slugify_city(city_slug)
    city_name = get_city_display_name(norm_slug, db=db)
    base_html = load_base_index_html()

    if not city_name or norm_slug not in HINDI_CITY_INFO:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hindi page not found")

    info = HINDI_CITY_INFO[norm_slug]
    matched_listings = get_city_approved_listings(norm_slug, city_name, db)
    total_listings = len(matched_listings)

    en_canonical = f"{BASE_URL}/properties/{norm_slug}"
    hi_canonical = f"{BASE_URL}/hi/properties/{norm_slug}"

    title = info["title"]
    description = info["desc"]

    # Schemas in Hindi
    breadcrumb_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "होम",
                "item": f"{BASE_URL}/"
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": f"{info['city_hi']} में प्रॉपर्टी",
                "item": hi_canonical
            }
        ]
    }

    item_list_elements = []
    for idx, l in enumerate(matched_listings[:15], start=1):
        l_path = get_listing_path(l.id, l.title, l.location, l.form_data)
        item_list_elements.append({
            "@type": "ListItem",
            "position": idx,
            "name": l.title or f"{info['city_hi']} में प्रॉपर्टी",
            "url": f"{BASE_URL}{l_path}"
        })

    item_list_ld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"{info['city_hi']} में प्रॉपर्टीज",
        "numberOfItems": len(item_list_elements),
        "itemListElement": item_list_elements
    }

    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f["answer"]
                }
            }
            for f in info["faqs"]
        ]
    }

    schemas_code = f"""  <!-- Hindi Schemas: Breadcrumbs, ItemList & FAQPage -->
  <script type="application/ld+json">
{json.dumps(breadcrumb_ld, indent=2, ensure_ascii=False)}
  </script>
  <script type="application/ld+json">
{json.dumps(item_list_ld, indent=2, ensure_ascii=False)}
  </script>
  <script type="application/ld+json">
{json.dumps(faq_ld, indent=2, ensure_ascii=False)}
  </script>"""

    html = base_html
    html = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1, flags=re.DOTALL)
    html = set_or_replace_meta(html, "name", "description", description)
    html = set_or_replace_canonical(html, hi_canonical)
    html = set_or_replace_hreflang(html, en_canonical, hi_canonical)
    html = set_or_replace_meta(html, "name", "robots", "index, follow")

    # OG / Twitter
    html = set_or_replace_meta(html, "property", "og:title", title)
    html = set_or_replace_meta(html, "property", "og:description", description)
    html = set_or_replace_meta(html, "property", "og:url", hi_canonical)

    html = html.replace("</head>", f"{schemas_code}\n</head>")

    items = []
    for l in matched_listings[:15]:
        l_path = get_listing_path(l.id, l.title, l.location, l.form_data)
        p_str = format_price(float(l.price)) if l.price else ""
        price_tag = f" - <strong>{html_lib.escape(p_str)}</strong>" if p_str else ""
        items.append(f'<li><a href="{l_path}">{html_lib.escape(l.title or "प्रॉपर्टी")}</a>{price_tag}</li>')
    listings_markup = "\n          ".join(items)

    faq_markup = "\n".join(
        f'          <dt style="font-weight: 700; margin-top: 10px;">{html_lib.escape(f["question"])}</dt>\n'
        f'          <dd style="margin-left: 0; margin-bottom: 8px; color: #4b5563;">{html_lib.escape(f["answer"])}</dd>'
        for f in info["faqs"]
    )

    types_markup = "\n".join(f'            <li>{html_lib.escape(t)}</li>' for t in info["prop_types"])

    root_ssr = f"""<div id="root">
    <div class="ssr-fallback" style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;">
      <main class="city-ssr-wrap" lang="hi">
        <h1>{html_lib.escape(info["h1"])}</h1>
        <p class="city-lead">{html_lib.escape(info["intro"])}</p>
        <section class="city-types-section">
          <h2>प्रॉपर्टी के प्रकार ({html_lib.escape(info["city_hi"])})</h2>
          <ul>
{types_markup}
          </ul>
        </section>
        <section class="city-listings-section">
          <h2>सत्यापित लिस्टिंग्स ({html_lib.escape(info["city_hi"])}) - कुल {total_listings} प्रॉपर्टीज</h2>
          <ul class="city-listings-links">
            {listings_markup}
          </ul>
        </section>
        <section class="city-faq-section" style="margin-top: 24px;">
          <h2>अक्सर पूछे जाने वाले सवाल (FAQ) - {html_lib.escape(info["city_hi"])}</h2>
          <dl>
{faq_markup}
          </dl>
        </section>
        <nav style="margin-top: 20px;">
          <a href="/properties/{norm_slug}">View this page in English</a> | <a href="/">TradeCall होम</a>
        </nav>
      </main>
    </div>
  </div>"""

    html = re.sub(r'<div\s+id=["\']root["\'][^>]*>.*?</div>', root_ssr, html, count=1, flags=re.DOTALL)
    return HTMLResponse(content=html, status_code=status.HTTP_200_OK, media_type="text/html")


# ==============================================================================
# SUB-LOCALITY LANDING PAGES (I-27)
# ==============================================================================

RESERVED_CITY_PATHS = {
    "api", "assets", "uploads", "static", "properties", "listing", "blog",
    "about", "contact", "cities", "business-directory", "privacy", "privacy-policy",
    "terms", "terms-of-use", "advertise", "post-listing", "login", "register",
    "admin", "hi", "health", "sitemap", "favicon.ico", "robots.txt"
}


def slugify_locality(text: Optional[str]) -> str:
    """Normalizes locality name into a clean hyphenated URL slug."""
    if not text:
        return ""
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    s = re.sub(r"panchwati-raod", "panchwati-road", s)
    s = re.sub(r"palwal-nuh-roa(?=-|$)", "palwal-nuh-road", s)
    s = re.sub(r"hospitcal", "hospital", s)
    return s.strip("-")


def get_locality_approved_listings(city_slug: str, city_name: str, locality_slug: str, db: Session):
    """
    Finds approved listings matching both city and locality slug.
    Returns (matched_listings, best_display_locality_name).
    """
    city_listings = get_city_approved_listings(city_slug, city_name, db)
    matched = []
    locality_display = locality_slug.replace("-", " ").title()

    for l in city_listings:
        loc_str = ""
        if isinstance(l.form_data, dict) and l.form_data.get("locality"):
            loc_str = str(l.form_data.get("locality")).strip()
        elif l.location:
            parts = [p.strip() for p in l.location.split(",") if p.strip()]
            if parts and parts[0].lower() != city_name.lower():
                loc_str = parts[0]

        if loc_str:
            clean_s = slugify_locality(loc_str)
            if clean_s == locality_slug or locality_slug == clean_s or (len(locality_slug) >= 5 and locality_slug in clean_s):
                matched.append(l)
                if len(loc_str) > len(locality_display) or locality_display == locality_slug.replace("-", " ").title():
                    locality_display = loc_str

    return matched, locality_display


@router.api_route("/{city_slug}/{locality_slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_sub_locality_properties_page(
    city_slug: str,
    locality_slug: str,
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db)
):
    """
    Renders Sub-Locality Hub (e.g. /palwal/omaxe-city-phase-ii) with verified inventory,
    price statistics, breadcrumbs, ItemList + FAQPage schemas, and link to parent city hub.
    """
    clean_city = city_slug.lower().strip()
    clean_loc = locality_slug.lower().strip()

    if clean_city in RESERVED_CITY_PATHS or clean_loc in RESERVED_CITY_PATHS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    city_name = get_city_display_name(clean_city, db=db)
    if not city_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City Not Found")

    matched_listings, locality_name = get_locality_approved_listings(clean_city, city_name, clean_loc, db)
    total_listings = len(matched_listings)

    if total_listings == 0:
        base_html = load_base_index_html()
        body = f"""<main style="padding: 40px 20px; text-align: center;">
          <h1>No Active Listings in {html_lib.escape(locality_name)}</h1>
          <p>There are currently no active listings in {html_lib.escape(locality_name)}, {html_lib.escape(city_name)}. Explore verified properties across {html_lib.escape(city_name)}.</p>
          <p><a href="/properties/{clean_city}">Browse All Properties in {html_lib.escape(city_name)}</a></p>
        </main>"""
        rendered = re.sub(
            r"<title>.*?</title>",
            f"<title>Properties in {html_lib.escape(locality_name)}, {html_lib.escape(city_name)} | TradeCall India</title>",
            base_html,
            count=1,
            flags=re.DOTALL
        )
        rendered = set_or_replace_meta(rendered, "name", "robots", "noindex, follow")
        rendered = re.sub(r'<div\s+id=["\']root["\'][^>]*>.*?</div>', f'<div id="root">{body}</div>', rendered, count=1, flags=re.DOTALL)
        return HTMLResponse(content=rendered, status_code=status.HTTP_404_NOT_FOUND)

    # Sub-locality threshold: >= 2 listings indexable; 1 listing noindex
    robots_content = "index, follow" if total_listings >= 2 else "noindex, follow"
    canonical = f"{BASE_URL}/{clean_city}/{clean_loc}"

    title = f"Properties in {locality_name}, {city_name} | Buy & Rent | TradeCall India"
    description = f"{total_listings} verified properties for sale and rent in {locality_name}, {city_name}. Explore plots, flats, and houses directly with genuine owners and zero brokerage."

    price_stats = compute_price_stats(matched_listings)
    min_p_str = format_price(price_stats["min"]) or "N/A"
    med_p_str = format_price(price_stats["median"]) or "N/A"
    max_p_str = format_price(price_stats["max"]) or "N/A"

    # Breadcrumbs Schema
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
                "item": f"{BASE_URL}/properties/{clean_city}"
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": locality_name,
                "item": canonical
            }
        ]
    }

    item_list_elements = []
    for idx, l in enumerate(matched_listings, start=1):
        l_path = get_listing_path(l.id, l.title, l.location, l.form_data)
        item_list_elements.append({
            "@type": "ListItem",
            "position": idx,
            "name": l.title or f"Property in {locality_name}",
            "url": f"{BASE_URL}{l_path}"
        })

    item_list_ld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"Properties in {locality_name}, {city_name}",
        "numberOfItems": len(item_list_elements),
        "itemListElement": item_list_elements
    }

    locality_faqs = [
        {
            "question": f"What are property prices like in {locality_name}, {city_name}?",
            "answer": f"Verified property listings in {locality_name} currently range from {min_p_str} up to {max_p_str}, with a median listing price of approximately {med_p_str}."
        },
        {
            "question": f"Can I purchase or rent property in {locality_name} with zero brokerage?",
            "answer": f"Yes, TradeCall India connects buyers and tenants directly with property owners and verified sellers in {locality_name} with 0% brokerage commission."
        },
        {
            "question": f"What types of properties are available in {locality_name}?",
            "answer": f"Property options in {locality_name} include residential plots, independent houses, villas, builder floors, and commercial options."
        },
        {
            "question": f"How do I verify plot approvals and registry in {locality_name}?",
            "answer": f"Always inspect the Jamabandi land records on jamabandi.nic.in, confirm sanctioned mutation (Inteqal), and check DTCP Section 7A NOC compliance before paying bayana."
        }
    ]

    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f["answer"]
                }
            }
            for f in locality_faqs
        ]
    }

    schemas_code = f"""  <!-- Sub-Locality Schemas: Breadcrumbs, ItemList & FAQPage -->
  <script type="application/ld+json">
{json.dumps(breadcrumb_ld, indent=2)}
  </script>
  <script type="application/ld+json">
{json.dumps(item_list_ld, indent=2)}
  </script>
  <script type="application/ld+json">
{json.dumps(faq_ld, indent=2)}
  </script>"""

    base_html = load_base_index_html()
    html = base_html
    html = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1, flags=re.DOTALL)
    html = set_or_replace_meta(html, "name", "description", description)
    html = set_or_replace_canonical(html, canonical)
    html = set_or_replace_meta(html, "name", "robots", robots_content)

    html = set_or_replace_meta(html, "property", "og:title", title)
    html = set_or_replace_meta(html, "property", "og:description", description)
    html = set_or_replace_meta(html, "property", "og:url", canonical)

    html = html.replace("</head>", f"{schemas_code}\n</head>")

    items = []
    for l in matched_listings:
        l_path = get_listing_path(l.id, l.title, l.location, l.form_data)
        p_str = format_price(float(l.price)) if l.price else ""
        price_tag = f" - <strong>{html_lib.escape(p_str)}</strong>" if p_str else ""
        items.append(f'<li><a href="{l_path}">{html_lib.escape(l.title or "Property")}</a>{price_tag} in {html_lib.escape(l.location or locality_name)}</li>')
    listings_markup = "\n          ".join(items)

    faq_markup = "\n".join(
        f'          <dt style="font-weight: 700; margin-top: 10px;">{html_lib.escape(f["question"])}</dt>\n'
        f'          <dd style="margin-left: 0; margin-bottom: 8px; color: #4b5563;">{html_lib.escape(f["answer"])}</dd>'
        for f in locality_faqs
    )

    root_ssr = f"""<div id="root">
    <div class="ssr-fallback" style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;">
      <main class="sub-locality-ssr-wrap">
        <nav aria-label="Breadcrumb" class="breadcrumbs">
          <a href="/">Home</a> &gt; <a href="/properties/{clean_city}">Properties in {html_lib.escape(city_name)}</a> &gt; <span>{html_lib.escape(locality_name)}</span>
        </nav>
        <h1>Properties in {html_lib.escape(locality_name)}, {html_lib.escape(city_name)}</h1>
        <div class="locality-price-summary">
          <p><strong>Price Range for {html_lib.escape(locality_name)}:</strong> Starting from {min_p_str} to {max_p_str} (Median: {med_p_str})</p>
        </div>
        <p class="locality-lead">Explore {total_listings} verified properties for sale and rent in {html_lib.escape(locality_name)}, {html_lib.escape(city_name)}. Buy directly from owners and verified agents with zero brokerage commission.</p>
        <section class="locality-listings-section">
          <h2>Verified Listings in {html_lib.escape(locality_name)} ({total_listings} Properties)</h2>
          <ul class="locality-listings-links">
            {listings_markup}
          </ul>
        </section>
        <section class="locality-faq-section" style="margin-top: 24px;">
          <h2>Frequently Asked Questions about {html_lib.escape(locality_name)}</h2>
          <dl>
{faq_markup}
          </dl>
        </section>
        <section class="locality-guides-section" style="margin-top: 20px;">
          <h2>Buyer Resources & Guides</h2>
          <ul>
            <li><a href="/blog/how-to-choose-suitable-residential-locality-in-palwal">Guide to Choosing Residential Localities in Palwal</a></li>
            <li><a href="/blog/how-to-check-plot-approvals-and-registry-documents-in-haryana">How to Check Plot Approvals & Registry in Haryana</a></li>
            <li><a href="/blog/property-registration-and-purchase-costs-in-haryana">Haryana Stamp Duty and Registration Charges Explained</a></li>
          </ul>
        </section>
        <nav style="margin-top: 20px;">
          <a href="/properties/{clean_city}">Browse All Properties in {html_lib.escape(city_name)}</a> | <a href="/cities">All City Hubs</a> | <a href="/">TradeCall Home</a>
        </nav>
      </main>
    </div>
  </div>"""

    html = re.sub(r'<div\s+id=["\']root["\'][^>]*>.*?</div>', root_ssr, html, count=1, flags=re.DOTALL)
    return HTMLResponse(content=html, status_code=status.HTTP_200_OK, media_type="text/html")

