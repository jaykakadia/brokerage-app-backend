import html as html_lib
import json
import math
import re
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.db.models.blog import Blog
from app.db.models.listing import Listing
from app.core.cities import MIN_HUB_LISTINGS, TOP_CITIES, get_city_display_name, slugify_city
from app.routers.city_pages import load_base_index_html, set_or_replace_canonical, set_or_replace_meta, get_active_cities_summary
from app.routers.sitemap import get_listing_path

router = APIRouter(tags=["Public Pages SSR"])
catch_all_router = APIRouter(tags=["Catch-All 404"])

BASE_URL = "https://tradecall.in"
PHONE = "+91 9992292828"
ADDRESS = "Palwal, Haryana"
GOOGLE_MAPS_URL = "https://maps.google.com/?q=Palwal,+Haryana+121102,+India"

DIRECTORY_CATEGORY_SLUGS: Dict[str, str] = {
    "property-dealers": "Property Dealers",
    "property-dealer": "Property Dealer",
    "real-estate-agents": "Real Estate Agents",
    "builders-and-developers": "Builders & Developers",
    "builders": "Builders & Developers",
    "interior-designers": "Interior Designers",
    "contractors": "Building Contractors",
    "architects": "Architects",
    "legal-advisors": "Property Legal Advisors",
    "home-loans": "Home Loan Consultants",
}


def format_page_title(raw_title: str, brand: str = "TradeCall India") -> str:
    raw = (raw_title or "").strip()
    raw = re.sub(rf"\s*[\-–|:]\s*{re.escape(brand)}$", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*[\-–|:]\s*Tradecall$", "", raw, flags=re.IGNORECASE)
    raw = raw.strip()
    return f"{raw} | {brand}" if raw else brand


def _render_page_shell(
    base_html: str,
    title: str,
    description: str,
    canonical_url: Optional[str],
    robots_content: str,
    root_inner_html: str,
    json_ld: Optional[Any] = None
) -> str:
    html = base_html

    # 1. Title
    if re.search(r"<title>.*?</title>", html, flags=re.DOTALL):
        html = re.sub(r"<title>.*?</title>", f"<title>{html_lib.escape(title)}</title>", html, count=1, flags=re.DOTALL)
    else:
        html = html.replace("<head>", f"<head>\n  <title>{html_lib.escape(title)}</title>")

    # 2. Description
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

    # 3. Canonical
    if canonical_url:
        html = set_or_replace_canonical(html, canonical_url)
    else:
        html = re.sub(r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>', '', html, flags=re.IGNORECASE)

    # 4. Robots
    html = set_or_replace_meta(html, "name", "robots", robots_content)

    # 5. OpenGraph & Twitter
    html = set_or_replace_meta(html, "property", "og:title", title)
    html = set_or_replace_meta(html, "property", "og:description", description)
    if canonical_url:
        html = set_or_replace_meta(html, "property", "og:url", canonical_url)
    html = set_or_replace_meta(html, "name", "twitter:title", title)
    html = set_or_replace_meta(html, "name", "twitter:description", description)

    # 6. JSON-LD Schema
    if json_ld:
        schema_tag = f"""  <script type="application/ld+json">\n{json.dumps(json_ld, indent=2)}\n  </script>"""
        html = html.replace("</head>", f"{schema_tag}\n</head>")

    # 7. Inject SSR body content into #root (preserving script tags and head)
    rendered_root = f'''<div id="root">
    <div class="ssr-page-content" style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;">
      {root_inner_html}
    </div>
  </div>'''
    html = re.sub(r'<div\s+id=["\']root["\'][^>]*>.*?</div>', rendered_root, html, count=1, flags=re.DOTALL)

    return html


# --- PUBLIC ROUTES ---

@router.api_route("/about", methods=["GET", "HEAD"], response_class=HTMLResponse)
@router.api_route("/about-us", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_about_page():
    base_html = load_base_index_html()
    title = "About Us | TradeCall India - Zero Brokerage Real Estate"
    desc = "Learn about TradeCall India, our mission to provide direct zero-brokerage property and business listings in Palwal, Faridabad, and NCR."
    canonical = f"{BASE_URL}/about"

    org_ld = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "TradeCall India",
        "url": BASE_URL,
        "telephone": PHONE,
        "hasMap": GOOGLE_MAPS_URL,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "Palwal",
            "addressLocality": "Palwal",
            "addressRegion": "Haryana",
            "postalCode": "121102",
            "addressCountry": "IN"
        }
    }

    body = f"""<main>
      <h1>About TradeCall India</h1>
      <p>TradeCall India is a premier zero-brokerage real estate platform and local business directory founded to bring transparency, trust, and affordability to property transactions across Palwal, Faridabad, Gurugram, and the greater National Capital Region (NCR).</p>
      <section>
        <h2>Our Mission</h2>
        <p>We eliminate expensive real estate brokerage fees by directly connecting buyers, sellers, tenants, and property owners. Every listing is verified by local associates to ensure authentic prices and genuine listings.</p>
      </section>
      <section>
        <h2>Contact Information</h2>
        <p><strong>Phone &amp; WhatsApp:</strong> <a href="tel:{PHONE}">{PHONE}</a></p>
        <p><strong>Registered Address:</strong> <a href="{GOOGLE_MAPS_URL}" target="_blank" rel="noopener noreferrer">{ADDRESS}</a></p>
      </section>
      <nav>
        <a href="/">Home</a> |
        <a href="/cities">Explore Cities</a> |
        <a href="/business-directory">Business Directory</a> |
        <a href="/faq">FAQ</a> |
        <a href="/post-listing">List Your Property</a> |
        <a href="/contact">Contact Us</a>
      </nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body, org_ld)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/contact", methods=["GET", "HEAD"], response_class=HTMLResponse)
@router.api_route("/contact-us", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_contact_page():
    """
    Audit Point 6 & 8:
    - Recommended title: Contact TradeCall India – Property & Business Listing Support | TradeCall India
    - Google Maps location link
    - ContactPage and Organization schema
    - Links to About Us, FAQ, List Your Property, and List Your Business pages
    """
    base_html = load_base_index_html()
    title = "Contact TradeCall India – Property & Business Listing Support | TradeCall India"
    desc = "Get in touch with TradeCall India in Palwal, Haryana for property and business listing support. Call or WhatsApp +91 9992292828 or email support.tradecall@gmail.com."
    canonical = f"{BASE_URL}/contact"

    contact_ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "ContactPage",
                "@id": f"{BASE_URL}/contact#webpage",
                "name": "Contact TradeCall India – Property & Business Listing Support",
                "url": canonical,
                "description": desc,
                "mainEntity": {"@id": f"{BASE_URL}/#organization"}
            },
            {
                "@type": "Organization",
                "@id": f"{BASE_URL}/#organization",
                "name": "TradeCall India",
                "url": BASE_URL,
                "telephone": PHONE,
                "email": "support.tradecall@gmail.com",
                "hasMap": GOOGLE_MAPS_URL,
                "contactPoint": {
                    "@type": "ContactPoint",
                    "telephone": PHONE,
                    "contactType": "customer service",
                    "areaServed": "IN",
                    "availableLanguage": ["en", "hi"]
                },
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": "Palwal",
                    "addressLocality": "Palwal",
                    "addressRegion": "Haryana",
                    "postalCode": "121102",
                    "addressCountry": "IN"
                }
            }
        ]
    }

    body = f"""<main>
      <h1>Contact TradeCall India</h1>
      <p>Have questions about a property listing or need help posting your free property or business listing? Reach out to our Palwal customer support team directly.</p>
      <section>
        <h2>Get In Touch</h2>
        <p><strong>Phone / WhatsApp:</strong> <a href="tel:{PHONE}">{PHONE}</a></p>
        <p><strong>Email:</strong> <a href="mailto:support.tradecall@gmail.com">support.tradecall@gmail.com</a></p>
        <p><strong>Office Location:</strong> <a href="{GOOGLE_MAPS_URL}" target="_blank" rel="noopener noreferrer">Palwal, Haryana 121102 (View on Google Maps)</a></p>
      </section>
      <nav aria-label="Quick Links">
        <a href="/">Home</a> |
        <a href="/about">About Us</a> |
        <a href="/faq">FAQ</a> |
        <a href="/post-listing">List Your Property</a> |
        <a href="/post-listing">List Your Business</a> |
        <a href="/business-directory">Business Directory</a> |
        <a href="/cities">Property Hubs</a>
      </nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body, contact_ld)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/faq", methods=["GET", "HEAD"], response_class=HTMLResponse)
@router.api_route("/faqs", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_faq_page():
    base_html = load_base_index_html()
    title = "Frequently Asked Questions (FAQ) | TradeCall India"
    desc = "Find answers to frequently asked questions about buying, selling, renting properties, and registering real estate businesses on TradeCall India."
    canonical = f"{BASE_URL}/faq"

    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "How do I post a free property or business listing on TradeCall India?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Visit the Post Property / Business page, sign in or register your free account, choose Property or Business, fill in your location and details, and submit for approval."
                }
            },
            {
                "@type": "Question",
                "name": "Does TradeCall India charge any brokerage fee?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "No, TradeCall India is a zero-brokerage platform that connects buyers, tenants, property owners, and local businesses directly."
                }
            }
        ]
    }

    body = """<main>
      <h1>Frequently Asked Questions (FAQ) – TradeCall India</h1>
      <p>Find answers to common questions about buying, selling, renting properties, and listing your business on TradeCall India.</p>
      <nav>
        <a href="/">Home</a> |
        <a href="/about">About Us</a> |
        <a href="/contact">Contact Us</a> |
        <a href="/post-listing">List Your Property</a> |
        <a href="/business-directory">Business Directory</a>
      </nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body, faq_ld)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/cities", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_cities_page(db: Session = Depends(get_db)):
    base_html = load_base_index_html()
    title = "Property by City & Hubs | TradeCall India"
    desc = "Explore verified real estate listings by city in Palwal, Faridabad, Hodal, Ballabgarh, Greater Noida, and across Delhi NCR with zero brokerage."
    canonical = f"{BASE_URL}/cities"

    active_cities = get_active_cities_summary(db)
    city_items = []
    for c in active_cities:
        city_items.append(f'<li><a href="/properties/{c["slug"]}">Properties in {c["name"]} ({c["count"]} listings)</a></li>')
    city_list_html = "\n        ".join(city_items)

    body = f"""<main>
      <h1>Property in Top Cities &amp; Hubs</h1>
      <p>Browse zero-brokerage real estate listings across top cities and towns in Haryana, Uttar Pradesh, and the NCR.</p>
      <section>
        <h2>Active City Hubs</h2>
        <ul>
        {city_list_html}
        </ul>
      </section>
      <nav><a href="/">Home</a> | <a href="/business-directory">Business Directory</a> | <a href="/contact">Contact Us</a></nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


def _extract_biz_categories(listing: Listing) -> List[str]:
    fd = listing.form_data if isinstance(listing.form_data, dict) else {}
    cats: List[str] = []
    selected = fd.get("selectedCategories")
    if isinstance(selected, list):
        for item in selected:
            if isinstance(item, dict) and item.get("name"):
                cats.append(str(item["name"]).strip())
            elif isinstance(item, str) and item.strip():
                cats.append(item.strip())
    if not cats:
        for k in ("categoryName", "category"):
            val = fd.get(k)
            if isinstance(val, str) and val.strip():
                cats.extend([c.strip() for c in val.split(",") if c.strip()])
    return cats or ["Property Dealer"]


def _extract_biz_city(listing: Listing) -> str:
    fd = listing.form_data if isinstance(listing.form_data, dict) else {}
    if fd.get("city"):
        return str(fd["city"]).strip()
    if listing.location:
        parts = [p.strip() for p in listing.location.split(",") if p.strip()]
        if len(parts) >= 3:
            return parts[-2]
        elif len(parts) == 2:
            return parts[1]
        elif len(parts) == 1:
            return parts[0]
    return "Palwal"


def _render_business_directory_ssr(
    request: Request,
    db: Session,
    city_slug: Optional[str] = None,
    category_slug: Optional[str] = None
) -> HTMLResponse:
    """
    Audit Point 7 & 8:
    - Renders business names, categories, locations, and crawlable detail-page links in initial HTML
    - Supports category and city landing pages (e.g. 'Property Dealers in Palwal', 'Property Dealers in Faridabad')
    - Uses unique page titles and H1 headings for each category/location page
    - Adds crawlable pagination links
    - Adds CollectionPage and ItemList schema
    """
    base_html = load_base_index_html()

    q_city = (request.query_params.get("city") or "").strip()
    q_category = (request.query_params.get("category") or "").strip()
    try:
        page = max(1, int(request.query_params.get("page") or "1"))
    except ValueError:
        page = 1

    resolved_city = ""
    if city_slug:
        c_display = get_city_display_name(city_slug, db=db)
        if not c_display and city_slug.lower() in DIRECTORY_CATEGORY_SLUGS and not category_slug:
            category_slug = city_slug
            city_slug = None
        else:
            resolved_city = c_display or city_slug.replace("-", " ").title()
    elif q_city:
        resolved_city = q_city

    resolved_category = ""
    if category_slug:
        clean_cat_slug = category_slug.strip().lower()
        resolved_category = DIRECTORY_CATEGORY_SLUGS.get(
            clean_cat_slug,
            clean_cat_slug.replace("-", " ").title()
        )
    elif q_category:
        resolved_category = q_category

    # Query all approved business listings
    all_approved = (
        db.query(Listing)
        .filter(Listing.status == "approved")
        .order_by(Listing.is_featured.desc(), Listing.id.desc())
        .all()
    )
    businesses: List[Listing] = []
    for item in all_approved:
        fd = item.form_data if isinstance(item.form_data, dict) else {}
        if fd.get("kind") == "business" or (fd.get("businessName") and not fd.get("propType") and not item.price):
            businesses.append(item)

    # Filter by city and category if requested
    filtered: List[Listing] = []
    for b in businesses:
        b_city = _extract_biz_city(b)
        b_cats = _extract_biz_categories(b)
        if resolved_city:
            if resolved_city.lower() not in b_city.lower() and resolved_city.lower() not in (b.location or "").lower():
                continue
        if resolved_category:
            cat_Singular = resolved_category.lower().rstrip("s")
            if not any(cat_Singular in c.lower() or c.lower() in resolved_category.lower() for c in b_cats):
                continue
        filtered.append(b)

    per_page = 20
    total_items = len(filtered)
    total_pages = max(1, math.ceil(total_items / per_page))
    current_page = min(page, total_pages)
    start_idx = (current_page - 1) * per_page
    paged_items = filtered[start_idx : start_idx + per_page]

    # Unique H1 and Page Title (Audit Point 7 & 8)
    if resolved_category and resolved_city:
        h1_text = f"{resolved_category} in {resolved_city}"
        title = f"{resolved_category} in {resolved_city} | Business Directory – TradeCall India"
        desc = f"Find verified {resolved_category.lower()} in {resolved_city} on TradeCall India. Browse business names, categories, locations, and direct contact details."
    elif resolved_city:
        h1_text = f"Business Directory in {resolved_city}"
        title = f"Business Directory in {resolved_city} – Property Dealers & Local Businesses | TradeCall India"
        desc = f"Explore verified local businesses, property dealers, builders, and real estate services in {resolved_city} on TradeCall India."
    elif resolved_category:
        h1_text = f"{resolved_category} in Palwal, Faridabad & Delhi NCR"
        title = f"{resolved_category} in Palwal, Faridabad & Delhi NCR | Business Directory – TradeCall India"
        desc = f"Connect with verified {resolved_category.lower()} across Palwal, Faridabad, and Delhi NCR on TradeCall India."
    else:
        h1_text = "Business Directory in Palwal, Faridabad & Delhi NCR"
        title = "Business Directory in Palwal, Faridabad & Delhi NCR | TradeCall India"
        desc = "Discover verified local businesses, property dealers, builders, contractors, and professional services in Palwal, Faridabad, and Delhi NCR on TradeCall India."

    # Canonical URL
    if city_slug and category_slug:
        base_canon_path = f"/business-directory/{city_slug.lower()}/{category_slug.lower()}"
    elif city_slug:
        base_canon_path = f"/business-directory/{city_slug.lower()}"
    elif category_slug:
        base_canon_path = f"/business-directory/{category_slug.lower()}"
    else:
        base_canon_path = "/business-directory"

    canonical = f"{BASE_URL}{base_canon_path}"
    if current_page > 1:
        canonical = f"{canonical}?page={current_page}"

    # Build HTML list of businesses with name, category, location, and crawlable detail-page link
    biz_li_items: List[str] = []
    item_list_elements: List[Dict[str, Any]] = []
    for idx, b in enumerate(paged_items):
        b_path = get_listing_path(b.id, b.title, b.location, b.form_data)
        b_url = f"{BASE_URL}{b_path}"
        fd = b.form_data if isinstance(b.form_data, dict) else {}
        b_name = (fd.get("businessName") or b.title or "Business").strip()
        b_cats = ", ".join(_extract_biz_categories(b))
        b_city = _extract_biz_city(b)
        b_loc = b.location or b_city
        biz_li_items.append(
            f'<li>'
            f'<a href="{b_path}"><strong>{html_lib.escape(b_name)}</strong></a> '
            f'– <span>{html_lib.escape(b_cats)}</span> in <span>{html_lib.escape(b_loc)}</span>'
            f'</li>'
        )
        item_list_elements.append({
            "@type": "ListItem",
            "position": start_idx + idx + 1,
            "item": {
                "@type": "LocalBusiness",
                "name": b_name,
                "url": b_url,
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": b_city,
                    "addressRegion": "Haryana",
                    "addressCountry": "IN"
                }
            }
        })

    biz_list_html = "\n          ".join(biz_li_items) if biz_li_items else "<li><a href=\"/post-listing\">List your business in this category</a></li>"

    # Category & City Landing Links
    landing_links = [
        ('<a href="/business-directory/palwal/property-dealers">Property Dealers in Palwal</a>'),
        ('<a href="/business-directory/faridabad/property-dealers">Property Dealers in Faridabad</a>'),
        ('<a href="/business-directory/palwal/builders-and-developers">Builders &amp; Developers in Palwal</a>'),
        ('<a href="/business-directory/faridabad/builders-and-developers">Builders &amp; Developers in Faridabad</a>'),
        ('<a href="/business-directory/gurugram/property-dealers">Property Dealers in Gurugram</a>'),
        ('<a href="/business-directory/noida/property-dealers">Property Dealers in Noida</a>'),
        ('<a href="/business-directory/ballabgarh/property-dealers">Property Dealers in Ballabgarh</a>'),
        ('<a href="/business-directory/hodal/property-dealers">Property Dealers in Hodal</a>'),
        ('<a href="/business-directory/palwal">Businesses in Palwal</a>'),
        ('<a href="/business-directory/faridabad">Businesses in Faridabad</a>'),
    ]
    landing_links_html = " | ".join(landing_links)

    # Crawlable pagination links
    pagination_links: List[str] = []
    if total_pages > 1:
        for p_num in range(1, total_pages + 1):
            p_href = base_canon_path if p_num == 1 else f"{base_canon_path}?page={p_num}"
            pagination_links.append(f'<a href="{p_href}">Page {p_num}</a>')
    pagination_html = (
        f'<nav aria-label="Business Directory Pagination">{" | ".join(pagination_links)}</nav>'
        if pagination_links
        else ""
    )

    # CollectionPage & ItemList JSON-LD Schema
    collection_ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": h1_text,
        "description": desc,
        "url": canonical,
        "mainEntity": {
            "@type": "ItemList",
            "name": h1_text,
            "numberOfItems": total_items,
            "itemListElement": item_list_elements
        }
    }

    body = f"""<main>
      <nav aria-label="Breadcrumb">
        <a href="/">Home</a> &rarr; <a href="/business-directory">Business Directory</a>{f' &rarr; <span>{html_lib.escape(h1_text)}</span>' if (resolved_city or resolved_category) else ''}
      </nav>
      <h1>{html_lib.escape(h1_text)}</h1>
      <p>{html_lib.escape(desc)}</p>
      <section>
        <h2>Verified Businesses ({total_items})</h2>
        <ul>
          {biz_list_html}
        </ul>
        {pagination_html}
      </section>
      <section>
        <h2>Popular Category &amp; City Landing Pages</h2>
        <nav aria-label="Business Categories by City">
          {landing_links_html}
        </nav>
      </section>
      <nav>
        <a href="/">Home</a> |
        <a href="/cities">Property Hubs</a> |
        <a href="/post-listing">List Your Business</a> |
        <a href="/post-listing">List Your Property</a> |
        <a href="/about">About Us</a> |
        <a href="/faq">FAQ</a> |
        <a href="/contact">Contact Us</a>
      </nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body, collection_ld)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/business-directory", methods=["GET", "HEAD"], response_class=HTMLResponse)
@router.api_route("/businesses", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_business_directory_page(request: Request, db: Session = Depends(get_db)):
    return _render_business_directory_ssr(request=request, db=db)


@router.api_route("/business-directory/{city_slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_business_directory_city_page(city_slug: str, request: Request, db: Session = Depends(get_db)):
    return _render_business_directory_ssr(request=request, db=db, city_slug=city_slug)


@router.api_route("/business-directory/{city_slug}/{category_slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_business_directory_city_category_page(city_slug: str, category_slug: str, request: Request, db: Session = Depends(get_db)):
    return _render_business_directory_ssr(request=request, db=db, city_slug=city_slug, category_slug=category_slug)


@router.api_route("/blog", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_blog_index_page(db: Session = Depends(get_db)):
    base_html = load_base_index_html()
    title = "How to Register and Search Properties on TradeCall India | Real Estate Blog"
    desc = "Real estate market updates, how to register and search properties on TradeCall India, legal registration tips, and investment analysis for Palwal, Faridabad, and Delhi NCR."
    canonical = f"{BASE_URL}/blog"

    blogs = (
        db.query(Blog)
        .filter(Blog.status.in_(["published", "publish"]))
        .order_by(Blog.id.desc())
        .limit(20)
        .all()
    )
    blog_items = []
    for b in blogs:
        blog_items.append(f'<li><a href="/blog/{b.permalink}">{html_lib.escape(b.title)}</a></li>')
    blog_list_html = "\n        ".join(blog_items) if blog_items else "<p>Check back soon for new real estate articles and guides.</p>"

    body = f"""<main>
      <h1>Real Estate Blog &amp; Property Guides – TradeCall India</h1>
      <p>Stay informed with the latest property market trends, how to register and search properties on TradeCall India, legal guidance, and real estate investment tips.</p>
      <section>
        <h2>Recent Articles</h2>
        <ul>
        {blog_list_html}
        </ul>
      </section>
      <nav>
        <a href="/">Home</a> |
        <a href="/properties/palwal">Properties in Palwal</a> |
        <a href="/properties/faridabad">Properties in Faridabad</a> |
        <a href="/business-directory">Business Directory</a> |
        <a href="/post-listing">Post Property / Register</a> |
        <a href="/contact">Contact Us</a>
      </nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/blog/{slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_blog_detail_page(slug: str, db: Session = Depends(get_db)):
    base_html = load_base_index_html()
    clean_slug = slug.strip().lower()

    blog = db.query(Blog).filter(
        Blog.permalink == clean_slug,
        Blog.status.in_(["published", "publish"])
    ).first()

    if not blog:
        not_found_body = """<main>
          <h1>Article Not Found</h1>
          <p>The requested blog article does not exist or has been removed.</p>
          <nav><a href="/blog">Browse All Articles</a> | <a href="/">Back to Homepage</a></nav>
        </main>"""
        rendered = _render_page_shell(
            base_html,
            "404 - Article Not Found | TradeCall India",
            "This article could not be found.",
            None,
            "noindex, follow",
            not_found_body
        )
        return HTMLResponse(content=rendered, status_code=status.HTTP_404_NOT_FOUND)

    title = format_page_title(blog.title)
    clean_text = re.sub(r"<[^>]*>", " ", blog.content or "")
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    desc = clean_text[:160].rstrip() if clean_text else f"Read {blog.title} on TradeCall India Blog."
    canonical = f"{BASE_URL}/blog/{blog.permalink}"

    pub_date = blog.created_at.strftime("%Y-%m-%d") if blog.created_at else "2026-05-01"
    mod_date = blog.updated_at.strftime("%Y-%m-%d") if blog.updated_at else pub_date
    author_name = blog.author or "TradeCall Team"

    # Audit Point 5: BlogPosting schema with accurate author and publication dates
    article_ld = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": blog.title,
        "description": desc,
        "url": canonical,
        "datePublished": pub_date,
        "dateModified": mod_date,
        "author": {
            "@type": "Person",
            "name": author_name
        },
        "publisher": {
            "@type": "Organization",
            "name": "TradeCall India",
            "url": BASE_URL,
            "logo": {
                "@type": "ImageObject",
                "url": f"{BASE_URL}/favicon-192x192.png"
            }
        }
    }

    # Audit Point 5: Natural internal links to property listing page, business directory, contact page, and registration pages
    body = f"""<article>
      <h1>{html_lib.escape(blog.title)}</h1>
      <p class="post-meta">By <span class="author">{html_lib.escape(author_name)}</span> · Published on <time datetime="{pub_date}">{pub_date}</time></p>
      <div class="post-content">
        {blog.content}
      </div>
      <section class="blog-internal-links">
        <h2>Explore TradeCall India Real Estate &amp; Directory Services</h2>
        <p>
          Browse verified <a href="/properties/palwal">property listings in Palwal</a> and <a href="/properties/faridabad">Properties in Faridabad</a>,
          connect with local dealers in our <a href="/business-directory">Business Directory</a>,
          <a href="/register">register an account</a> to <a href="/post-listing">post your property or business for free</a>,
          or reach out via our <a href="/contact">Contact Us page</a>.
        </p>
      </section>
      <nav><a href="/blog">Back to Blog</a> | <a href="/">Home</a> | <a href="/business-directory">Business Directory</a> | <a href="/contact">Contact</a></nav>
    </article>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body, article_ld)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/privacy", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_privacy_page():
    base_html = load_base_index_html()
    title = "Privacy Policy | TradeCall India"
    desc = "Privacy policy and personal data protection terms for TradeCall India users and listing posters."
    canonical = f"{BASE_URL}/privacy"

    body = """<main>
      <h1>Privacy Policy</h1>
      <p>TradeCall India respects your privacy and is committed to protecting your personal data. This privacy policy explains how we handle your personal information when you browse our website or post property and business listings.</p>
      <nav><a href="/">Home</a> | <a href="/terms-of-use">Terms of Use</a></nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/privacy-policy", methods=["GET", "HEAD"], response_class=HTMLResponse)
def redirect_privacy_policy():
    return RedirectResponse(url=f"{BASE_URL}/privacy", status_code=status.HTTP_301_MOVED_PERMANENTLY)


@router.api_route("/terms-of-use", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_terms_page():
    base_html = load_base_index_html()
    title = "Terms of Use | TradeCall India"
    desc = "Terms of use, listing guidelines, and user agreement for TradeCall India."
    canonical = f"{BASE_URL}/terms-of-use"

    body = """<main>
      <h1>Terms of Use</h1>
      <p>By accessing or using TradeCall India, you agree to comply with and be bound by these terms of use. All property listings must be genuine, legally marketable, and free from misleading descriptions.</p>
      <nav><a href="/">Home</a> | <a href="/privacy">Privacy Policy</a></nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/terms", methods=["GET", "HEAD"], response_class=HTMLResponse)
def redirect_terms():
    return RedirectResponse(url=f"{BASE_URL}/terms-of-use", status_code=status.HTTP_301_MOVED_PERMANENTLY)


@router.api_route("/advertise", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_advertise_page():
    base_html = load_base_index_html()
    title = "Advertise with Us | TradeCall India"
    desc = "Promote your real estate projects, builder developments, and local businesses to targeted buyers across Palwal, Faridabad, and NCR."
    canonical = f"{BASE_URL}/advertise"

    body = f"""<main>
      <h1>Advertise with TradeCall India</h1>
      <p>Reach thousands of active property seekers and homeowners across Palwal, Faridabad, and NCR through featured banner placements and verified business promotions.</p>
      <p>For custom advertising packages, call or WhatsApp us directly at <a href="tel:{PHONE}">{PHONE}</a>.</p>
      <nav><a href="/">Home</a> | <a href="/contact">Contact Us</a></nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/post-listing", methods=["GET", "HEAD"], response_class=HTMLResponse)
@router.api_route("/register", methods=["GET", "HEAD"], response_class=HTMLResponse)
@router.api_route("/login", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_post_listing_page(request: Request):
    base_html = load_base_index_html()
    path = request.url.path.lower()
    if path == "/register":
        title = "Register Free Account | TradeCall India"
        desc = "Create a free account on TradeCall India to post properties, list your business, and contact verified owners directly."
        canonical = f"{BASE_URL}/register"
    elif path == "/login":
        title = "Sign In | TradeCall India"
        desc = "Sign in to your TradeCall India account to manage your property and business listings."
        canonical = f"{BASE_URL}/login"
    else:
        title = "Post Free Property Listing | TradeCall India"
        desc = "Post your property for sale or rent with zero brokerage on TradeCall India and connect directly with verified buyers and tenants."
        canonical = f"{BASE_URL}/post-listing"

    body = """<main>
      <h1>Post Free Property or Business Listing</h1>
      <p>Post your residential flat, plot, house, commercial shop, or local business on TradeCall India. 100% free with zero brokerage.</p>
      <nav><a href="/">Home</a> | <a href="/cities">Explore Properties</a> | <a href="/business-directory">Business Directory</a></nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "noindex, follow", body)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


# --- CATCH-ALL ROUTE (Registered at the very end of app routing) ---

@catch_all_router.api_route("/{path:path}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def handle_catch_all_404(path: str, db: Session = Depends(get_db)):
    clean_path = path.lower().strip("/")

    if (
        clean_path.startswith("api/")
        or clean_path.startswith("assets/")
        or clean_path.startswith("uploads/")
        or clean_path.startswith("static/")
        or clean_path.startswith("sitemap")
        or clean_path in ("robots.txt", "favicon.ico", "favicon.png", "icon.jpeg", "health")
        or any(clean_path.endswith(ext) for ext in [
            ".js", ".css", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico",
            ".woff", ".woff2", ".ttf", ".eot", ".map", ".json", ".xml", ".txt"
        ])
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    base_html = load_base_index_html()
    active_cities = get_active_cities_summary(db)
    top_links = []
    for c in active_cities[:8]:
        top_links.append(f'<li><a href="/properties/{c["slug"]}">Properties in {c["name"]}</a></li>')
    links_html = "\n        ".join(top_links)

    body = f"""<main style="padding: 40px 20px; text-align: center; font-family: sans-serif;">
      <h1>Page Not Found</h1>
      <p>The page you requested could not be found. It may have been moved, renamed, or is temporarily unavailable.</p>
      <section style="margin-top: 24px;">
        <h2>Explore Verified Properties</h2>
        <ul style="list-style: none; padding: 0; display: flex; flex-wrap: wrap; justify-content: center; gap: 12px;">
          <li><a href="/">TradeCall Home</a></li>
          {links_html}
        </ul>
      </section>
    </main>"""

    rendered = _render_page_shell(
        base_html=base_html,
        title="Page Not Found | TradeCall India",
        description="The requested page could not be found on TradeCall India.",
        canonical_url=None,
        robots_content="noindex, nofollow",
        root_inner_html=body
    )
    return HTMLResponse(content=rendered, status_code=status.HTTP_404_NOT_FOUND)
