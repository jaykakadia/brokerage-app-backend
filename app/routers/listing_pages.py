import html as html_lib
import json
import re
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.db.models.listing import Listing
from app.core.cities import slugify_city
from app.core.validation_rules import is_buyer_requirement, is_thin_business
from app.routers.city_pages import load_base_index_html, set_or_replace_canonical, set_or_replace_meta
from app.routers.sitemap import get_listing_path

router = APIRouter(tags=["Listing Share Pages"])

BASE_URL = "https://tradecall.in"

KNOWN_DELETED_LISTING_IDS = {49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 93, 95, 96, 97, 172, 227}


def parse_listing_id(raw_id: str) -> Optional[int]:
    """Extracts numeric listing ID from raw path parameter (e.g. '60', 'TC011P-60', 'TC-60')."""
    if not raw_id:
        return None
    val = str(raw_id).strip()
    upper = val.upper()
    if upper.startswith("TC011P-"):
        val = val[7:]
    elif upper.startswith("TC-"):
        val = val[3:]
    return int(val) if val.isdigit() else None


def format_price(val: Optional[float]) -> str:
    """Formats numeric price into Indian currency shorthand (Lakhs/Crores)."""
    if val is None or float(val or 0) <= 0:
        return "Price on request"
    val = float(val)
    if val >= 10_000_000:
        cr = val / 10_000_000
        return f"₹ {cr:.2f}".rstrip("0").rstrip(".") + " Cr"
    if val >= 100_000:
        lac = val / 100_000
        return f"₹ {lac:.2f}".rstrip("0").rstrip(".") + " Lac"
    return f"₹ {int(val):,}"


def _listing_city(location: Optional[str], form_data: Dict[str, Any]) -> str:
    city = form_data.get("city")
    if not city and location:
        parts = [p.strip() for p in location.split(",") if p.strip()]
        if len(parts) >= 3:
            city = parts[-2]
        elif len(parts) == 2:
            city = parts[1]
        elif len(parts) == 1:
            city = parts[0]
    return city or "Palwal"


import time

_DUPLICATE_TITLES_CACHE: Dict[str, Any] = {"timestamp": 0.0, "titles": set()}


def invalidate_title_cache() -> None:
    """Invalidates the duplicate SEO title cache."""
    _DUPLICATE_TITLES_CACHE["timestamp"] = 0.0
    _DUPLICATE_TITLES_CACHE["titles"] = set()


def compute_base_seo_title(listing: Any) -> str:
    """
    Computes base SEO title directly using listing.title and price:
    {listing.title} - {price}
    """
    form_data = getattr(listing, "form_data", None) or {}
    if not isinstance(form_data, dict):
        form_data = {}

    price = getattr(listing, "price", 0.0)
    raw_title = (getattr(listing, "title", "") or "").strip()

    # Business listings
    b_name = form_data.get("businessName")
    is_business = form_data.get("kind") == "business" or bool(b_name and not form_data.get("propType") and not price)
    if is_business:
        location = getattr(listing, "location", "") or ""
        city = _listing_city(location, form_data) or "Palwal"
        cat_name = form_data.get("category") or form_data.get("categoryName") or "Business"
        return f"{b_name or raw_title or 'Business'} - {cat_name} in {city}"

    price_str = format_price(price)
    price_clause = f" - {price_str}" if price_str else ""

    if raw_title:
        clean_title = re.sub(r"\s*\|\s*TradeCall.*$", "", raw_title, flags=re.IGNORECASE).strip()
        return f"{clean_title}{price_clause}"

    location = getattr(listing, "location", "") or ""
    city = _listing_city(location, form_data) or "Palwal"
    locality = form_data.get("locality") or (location.split(",")[0].strip() if location else city)
    for_what = (form_data.get("forWhat") or "sale").title()
    loc_clause = f"in {locality}, {city}" if locality != city else f"in {city}"
    return f"Property for {for_what} {loc_clause}{price_clause}"


def get_duplicate_seo_titles(db: Session, ttl: float = 60.0) -> set:
    """Finds all base SEO titles produced by 2 or more approved listings."""
    now = time.time()
    if now - _DUPLICATE_TITLES_CACHE["timestamp"] < ttl and _DUPLICATE_TITLES_CACHE["titles"]:
        return _DUPLICATE_TITLES_CACHE["titles"]

    approved = db.query(Listing).filter(Listing.status == "approved").all()
    counts: Dict[str, int] = {}
    for l in approved:
        bt = compute_base_seo_title(l)
        counts[bt] = counts.get(bt, 0) + 1

    dups = {bt for bt, count in counts.items() if count > 1}
    _DUPLICATE_TITLES_CACHE["timestamp"] = now
    _DUPLICATE_TITLES_CACHE["titles"] = dups
    return dups


def compute_listing_seo_title(listing: Listing, db: Optional[Session] = None) -> str:
    """
    Builds final SEO title.
    Adds '(TC011P-xxx)' only when two or more approved listings produce the exact same final base title.
    """
    base_title = compute_base_seo_title(listing)
    has_collision = False
    if db is not None:
        dups = get_duplicate_seo_titles(db)
        has_collision = base_title in dups

    unique_code = f"TC011P-{listing.id}"
    if has_collision:
        return f"{base_title} ({unique_code}) | TradeCall India"
    else:
        return f"{base_title} | TradeCall India"


def clean_meta_description(text: str, max_len: int = 160) -> str:
    """Truncates description cleanly at a word boundary without trailing punctuation."""
    clean = re.sub(r"<[^>]*>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    if len(clean) <= max_len:
        return clean
    truncated = clean[: max_len - 3]
    truncated = re.sub(r"\s+\S*$", "", truncated).strip()
    truncated = re.sub(r"[,;:\.\-\s]+$", "", truncated).strip()
    return f"{truncated}..."


def pick_og_image(images: list) -> str:
    """Selects JPEG/PNG image if available; otherwise falls back to first WebP or default OG image."""
    if not images:
        return f"{BASE_URL}/og-image.png"

    chosen_fp = None
    for img in images:
        fp = (getattr(img, "file_path", None) or "").strip()
        if not fp:
            continue
        lower = fp.lower()
        if lower.endswith(".jpg") or lower.endswith(".jpeg") or lower.endswith(".png"):
            chosen_fp = fp
            break

    if not chosen_fp and images and getattr(images[0], "file_path", None):
        chosen_fp = images[0].file_path.strip()

    if not chosen_fp:
        return f"{BASE_URL}/og-image.png"

    fp_clean = chosen_fp.lstrip("/")
    if fp_clean.startswith("http://") or fp_clean.startswith("https://"):
        return fp_clean
    if fp_clean.startswith("uploads/"):
        return f"{BASE_URL}/{fp_clean}"
    return f"{BASE_URL}/uploads/{fp_clean}"


def build_410_html(base_html: str, message: str = "This listing has expired or has been permanently removed.") -> str:
    """Builds a real 410 Gone response with noindex for deleted / non-approved listings."""
    html = re.sub(
        r"<title>.*?</title>",
        "<title>Listing Removed (410) | TradeCall India</title>",
        base_html,
        count=1,
        flags=re.DOTALL
    )
    html = set_or_replace_meta(html, "name", "robots", "noindex, follow")
    html = re.sub(r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>', '', html, flags=re.IGNORECASE)

    rendered_root = f'''<div id="root">
    <main class="ssr-410" style="padding: 40px 20px; text-align: center; font-family: sans-serif;">
      <h1>Listing No Longer Available</h1>
      <p>{message}</p>
      <p><a href="/" style="color: #2563eb; text-decoration: underline;">Back to Homepage</a> | <a href="/cities" style="color: #2563eb; text-decoration: underline;">Explore Cities</a></p>
    </main>
  </div>'''
    html = re.sub(r'<div\s+id=["\']root["\'][^>]*>.*?</div>', rendered_root, html, count=1, flags=re.DOTALL)
    return html


def build_404_html(base_html: str) -> str:
    """Builds a real 404 response with noindex for missing listings."""
    html = re.sub(
        r"<title>.*?</title>",
        "<title>404 - Listing Not Found | TradeCall India</title>",
        base_html,
        count=1,
        flags=re.DOTALL
    )
    html = set_or_replace_meta(html, "name", "robots", "noindex, follow")
    html = re.sub(r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>', '', html, flags=re.IGNORECASE)

    rendered_root = '''<div id="root">
    <main class="ssr-404" style="padding: 40px 20px; text-align: center; font-family: sans-serif;">
      <h1>Listing Not Found</h1>
      <p>The property listing you are looking for does not exist or may have been deleted.</p>
      <p><a href="/" style="color: #2563eb; text-decoration: underline;">Back to Homepage</a> | <a href="/cities" style="color: #2563eb; text-decoration: underline;">Explore Cities</a></p>
    </main>
  </div>'''
    html = re.sub(r'<div\s+id=["\']root["\'][^>]*>.*?</div>', rendered_root, html, count=1, flags=re.DOTALL)
    return html


def build_listing_html(listing: Listing, base_html: str, db: Session) -> str:
    """
    Injects unique title, meta description, canonical, OG tags,
    BreadcrumbList + RealEstateListing/LocalBusiness JSON-LD, specs table, and similar listings.
    """
    form_data: Dict[str, Any] = listing.form_data if isinstance(listing.form_data, dict) else {}

    # Determine listing location & city
    city = form_data.get("city")
    locality = form_data.get("locality")
    if not city or not locality:
        if listing.location:
            parts = [p.strip() for p in listing.location.split(",") if p.strip()]
            if len(parts) >= 3:
                locality = locality or parts[0]
                city = city or parts[-2]
            elif len(parts) == 2:
                locality = locality or parts[0]
                city = city or parts[1]
            elif len(parts) == 1:
                city = city or parts[0]
    city = city or "Palwal"
    locality = locality or city
    city_slug = slugify_city(city) or "palwal"

    price_str = format_price(float(listing.price)) if listing.price else ""

    # Check if business listing or real estate
    b_name = form_data.get("businessName")
    is_business = False
    if form_data.get("kind") == "business" or (b_name and not form_data.get("propType") and not listing.price):
        is_business = True

    cat_name = "Business"
    if form_data.get("category"):
        cat_name = str(form_data.get("category"))

    unique_code = f"TC011P-{listing.id}"
    full_title = compute_listing_seo_title(listing, db)
    if is_business:
        headline = f"{b_name or 'Business'} - {cat_name} in {city}"
    else:
        headline = listing.title or "Property Listing"

    summary_parts = [p for p in [price_str, listing.location] if p]
    summary_str = " · ".join(summary_parts)

    raw_desc = (listing.description or "").strip()
    clean_desc = re.sub(r"<[^>]*>", " ", raw_desc)
    clean_desc = re.sub(r"\s+", " ", clean_desc).strip()
    if not clean_desc:
        # Generated strictly from verified fields without padding or invented details
        if is_business:
            clean_desc = f"{b_name or 'Business'} - {cat_name} in {locality}, {city}. Verified business listing on TradeCall India."
        else:
            prop_type = (form_data.get("propType") or "Property").replace("-", " ").title()
            for_what = (form_data.get("forWhat") or "sale").lower()
            parts = [f"{prop_type} for {for_what}", f"in {locality}, {city}"]
            if price_str:
                parts.append(f"priced at {price_str}")
            clean_desc = f"{' '.join(parts)}. Verified property listing on TradeCall India with zero brokerage."

    combined_desc = f"{summary_str}. {clean_desc} Contact verified owner directly on TradeCall India." if summary_str else f"{clean_desc} Contact verified owner directly on TradeCall India."
    meta_desc = clean_meta_description(combined_desc, max_len=160)

    canonical_path = get_listing_path(listing.id, listing.title, listing.location, listing.form_data)
    canonical_url = f"{BASE_URL}{canonical_path}"
    image_url = pick_og_image(listing.images or [])

    # BreadcrumbList Schema (Home > City > Locality > Property)
    breadcrumb_items = [
        {
            "@type": "ListItem",
            "position": 1,
            "name": "Home",
            "item": f"{BASE_URL}/"
        },
        {
            "@type": "ListItem",
            "position": 2,
            "name": f"Properties in {city}",
            "item": f"{BASE_URL}/properties/{city_slug}"
        }
    ]
    if locality and locality != city:
        breadcrumb_items.append({
            "@type": "ListItem",
            "position": 3,
            "name": f"Properties in {locality}",
            "item": f"{BASE_URL}/properties/{city_slug}"
        })
    breadcrumb_items.append({
        "@type": "ListItem",
        "position": len(breadcrumb_items) + 1,
        "name": headline,
        "item": canonical_url
    })

    breadcrumbs_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": breadcrumb_items
    }

    # Main Entity Schema (RealEstateListing or LocalBusiness)
    if is_business:
        entity_ld = {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": headline,
            "description": meta_desc,
            "url": canonical_url,
            "image": [image_url],
            "address": {
                "@type": "PostalAddress",
                "addressLocality": city,
                "addressRegion": "Haryana",
                "addressCountry": "IN"
            }
        }
    else:
        entity_ld = {
            "@context": "https://schema.org",
            "@type": "RealEstateListing",
            "name": headline,
            "description": meta_desc,
            "url": canonical_url,
            "image": [image_url],
        }
        if listing.price and float(listing.price) > 0:
            entity_ld["offers"] = {
                "@type": "Offer",
                "price": float(listing.price),
                "priceCurrency": "INR"
            }

    schema_ld = f"""  <!-- Schemas: BreadcrumbList & Entity -->
  <script type="application/ld+json">
{json.dumps(breadcrumbs_ld, indent=2)}
  </script>
  <script type="application/ld+json">
{json.dumps(entity_ld, indent=2)}
  </script>"""

    # Query up to 6 listings in the same locality (approved only)
    more_in_locality = []
    if locality and locality != city:
        more_in_locality = (
            db.query(Listing)
            .filter(
                Listing.status == "approved",
                Listing.id != listing.id,
                Listing.location.ilike(f"%{locality}%")
            )
            .order_by(Listing.id.desc())
            .limit(6)
            .all()
        )

    # Query up to 6 similar listings in the city (approved only, excluding locality matches)
    exclude_ids = [listing.id] + [m.id for m in more_in_locality]
    similar = (
        db.query(Listing)
        .filter(
            Listing.status == "approved",
            Listing.id.notin_(exclude_ids)
        )
        .order_by(Listing.id.desc())
        .limit(6)
        .all()
    )

    def _render_listing_li(s: Listing) -> str:
        s_path = get_listing_path(s.id, s.title, s.location, s.form_data)
        s_p = format_price(float(s.price)) if s.price else ""
        price_tag = f" ({s_p})" if s_p else ""
        return f'<li><a href="{s_path}">{html_lib.escape(s.title or "Property Listing")}</a>{price_tag}</li>'

    locality_html = "\n            ".join(_render_listing_li(s) for s in more_in_locality)
    similar_html = "\n            ".join(_render_listing_li(s) for s in similar)

    # Specification table: strictly non-empty, valid rows (no "N/A" or empty cells)
    specs = []
    def _add_spec(label: str, val: Any):
        if val is None:
            return
        s = str(val).strip()
        if not s or s.lower() in ("n/a", "na", "none", "null", "undefined"):
            return
        specs.append(f'<tr><th>{html_lib.escape(label)}</th><td>{html_lib.escape(s)}</td></tr>')

    raw_pt = str(form_data.get("propType") or "").lower().strip()
    is_residential = raw_pt in ("flat", "house") or any(
        w in (listing.title or "").lower() for w in ("flat", "house", "villa", "builder floor", "apartment", "penthouse")
    )

    if form_data.get("propType"):
        _add_spec("Property Type", str(form_data.get("propType")).replace("-", " ").title())
    if is_residential and form_data.get("bhk"):
        _add_spec("Configuration", form_data.get("bhk"))
    if form_data.get("area"):
        _add_spec("Super / Carpet Area", f"{form_data.get('area')} {form_data.get('unit', '')}".strip())
    if form_data.get("plotArea"):
        _add_spec("Plot Area", f"{form_data.get('plotArea')} {form_data.get('plotUnit', '')}".strip())
    if form_data.get("agriArea"):
        _add_spec("Land Area", f"{form_data.get('agriArea')} {form_data.get('agriUnit', '')}".strip())
    if form_data.get("builtArea"):
        _add_spec("Built-up Area", f"{form_data.get('builtArea')} {form_data.get('builtUnit', '')}".strip())
    if is_residential and form_data.get("bath"):
        _add_spec("Bathrooms", form_data.get("bath"))
    if is_residential and form_data.get("furnish"):
        _add_spec("Furnishing", form_data.get("furnish"))
    if form_data.get("facing"):
        _add_spec("Facing", form_data.get("facing"))
    if form_data.get("possession"):
        _add_spec("Possession / Age", form_data.get("possession"))
    if price_str:
        _add_spec("Price", price_str)
    if locality:
        _add_spec("Locality", locality)
    if city:
        _add_spec("City", city)
    specs_html = "\n            ".join(specs)

    html = base_html

    # 1. Title
    html = re.sub(r"<title>.*?</title>", f"<title>{html_lib.escape(full_title)}</title>", html, count=1, flags=re.DOTALL)

    # 2. Meta description
    escaped_desc = html_lib.escape(meta_desc, quote=True)
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
    html = set_or_replace_canonical(html, canonical_url)

    # 4. Robots:
    # Rule B4: Thin business pages (no description and no useful contact details) must be noindex, follow.
    # Rule B5: "Looking to buy..." / requirement posts must be noindex, follow.
    if is_thin_business(listing) or is_buyer_requirement(listing.title, form_data):
        robots_content = "noindex, follow"
    else:
        robots_content = "index, follow" if listing.status == "approved" else "noindex, follow"
    html = set_or_replace_meta(html, "name", "robots", robots_content)

    # 5. OG and Twitter tags
    html = re.sub(r'\s*<meta\s+property=["\']og:image:(?:width|height)["\'][^>]*>', '', html)
    html = set_or_replace_meta(html, "property", "og:type", "website")
    html = set_or_replace_meta(html, "property", "og:title", headline)
    html = set_or_replace_meta(html, "property", "og:description", meta_desc)
    html = set_or_replace_meta(html, "property", "og:url", canonical_url)
    html = set_or_replace_meta(html, "property", "og:image", image_url)
    html = set_or_replace_meta(html, "property", "og:image:alt", headline)
    html = set_or_replace_meta(html, "name", "twitter:card", "summary_large_image")
    html = set_or_replace_meta(html, "name", "twitter:title", headline)
    html = set_or_replace_meta(html, "name", "twitter:description", meta_desc)
    html = set_or_replace_meta(html, "name", "twitter:image", image_url)
    html = set_or_replace_meta(html, "name", "twitter:image:alt", headline)

    # 6. JSON-LD Schemas
    html = html.replace("</head>", f"{schema_ld}\n</head>")

    # 7. Real HTML body inside <div id="root">
    escaped_headline = html_lib.escape(headline)
    escaped_price = html_lib.escape(price_str)
    escaped_loc = html_lib.escape(listing.location or f"{locality}, {city}")
    escaped_desc_body = html_lib.escape(clean_desc)
    escaped_img_src = html_lib.escape(image_url, quote=True)

    more_locality_section = f"""<section class="locality-listings-section" style="margin-top: 16px;">
        <h2>More Properties in {html_lib.escape(locality)}</h2>
        <ul>
          {locality_html}
        </ul>
      </section>""" if locality_html else ""

    rendered_root = f'''<div id="root">
    <article class="listing-ssr-preview" style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;">
      <nav aria-label="Breadcrumb" class="breadcrumbs">
        <a href="/">Home</a> &gt; <a href="/properties/{city_slug}">Properties in {html_lib.escape(city)}</a> &gt; <span>{escaped_headline}</span>
      </nav>
      <h1>{escaped_headline}</h1>
      <p class="listing-price">{escaped_price}</p>
      <p class="listing-location">{escaped_loc}</p>
      <img src="{escaped_img_src}" alt="{escaped_headline}" />
      <p class="listing-description">{escaped_desc_body}</p>
      <table class="listing-specs-table">
        <tbody>
          {specs_html}
        </tbody>
      </table>
      {more_locality_section}
      <section class="similar-listings-section">
        <h2>Similar Properties in {html_lib.escape(city)}</h2>
        <ul>
          {similar_html}
        </ul>
      </section>
    </article>
  </div>'''

    html = re.sub(r'<div\s+id=["\']root["\'][^>]*>.*?</div>', rendered_root, html, count=1, flags=re.DOTALL)
    return html


@router.api_route("/listing/{listing_id}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_listing_page_by_id(listing_id: str, request: Request, db: Session = Depends(get_db)):
    base_html = load_base_index_html()
    numeric_id = parse_listing_id(listing_id)

    # 1. ID in known deleted set -> 410 + noindex
    if not numeric_id or numeric_id in KNOWN_DELETED_LISTING_IDS:
        return HTMLResponse(content=build_410_html(base_html), status_code=status.HTTP_410_GONE)

    listing = db.query(Listing).filter(Listing.id == numeric_id).first()
    # 2. Listing not found -> 404 + noindex
    if not listing:
        return HTMLResponse(content=build_404_html(base_html), status_code=status.HTTP_404_NOT_FOUND)

    # 3. status != "approved" -> 410 + noindex
    if listing.status != "approved":
        return HTMLResponse(content=build_410_html(base_html), status_code=status.HTTP_410_GONE)

    # 4. Compare request path with canonical_path; redirect if different
    canonical_path = get_listing_path(listing.id, listing.title, listing.location, listing.form_data)
    req_path = request.url.path.rstrip("/").lower()
    canon_path = canonical_path.rstrip("/").lower()
    if req_path != canon_path:
        target_url = f"https://tradecall.in{canonical_path}"
        return RedirectResponse(url=target_url, status_code=status.HTTP_301_MOVED_PERMANENTLY)

    rendered_html = build_listing_html(listing, base_html, db)
    return HTMLResponse(content=rendered_html, status_code=status.HTTP_200_OK)


@router.api_route("/{city_slug}/{title_slug}/{unique_code}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_listing_page_by_slug(city_slug: str, title_slug: str, unique_code: str, request: Request, db: Session = Depends(get_db)):
    if city_slug.lower() == "hi" and title_slug.lower() == "properties":
        from app.routers.city_pages import get_hindi_city_properties_page
        return get_hindi_city_properties_page(city_slug=unique_code, request=request, db=db)

    # Guard against non-listing routes
    if city_slug.lower() in {
        "api", "uploads", "assets", "static", "docs", "redoc", "openapi.json",
        "sitemap", "properties", "pages", "blog", "search", "about", "contact",
        "cities", "business-directory", "privacy", "terms-of-use", "advertise", "post-listing"
    }:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    base_html = load_base_index_html()
    numeric_id = parse_listing_id(unique_code)

    # 1. ID in known deleted set -> 410 + noindex
    if not numeric_id or numeric_id in KNOWN_DELETED_LISTING_IDS:
        return HTMLResponse(content=build_410_html(base_html), status_code=status.HTTP_410_GONE)

    listing = db.query(Listing).filter(Listing.id == numeric_id).first()
    # 2. Listing not found -> 404 + noindex
    if not listing:
        return HTMLResponse(content=build_404_html(base_html), status_code=status.HTTP_404_NOT_FOUND)

    # 3. status != "approved" -> 410 + noindex
    if listing.status != "approved":
        return HTMLResponse(content=build_410_html(base_html), status_code=status.HTTP_410_GONE)

    # 4. Compare request path with canonical_path; redirect if different
    canonical_path = get_listing_path(listing.id, listing.title, listing.location, listing.form_data)
    req_path = request.url.path.rstrip("/").lower()
    canon_path = canonical_path.rstrip("/").lower()
    if req_path != canon_path:
        target_url = f"https://tradecall.in{canonical_path}"
        return RedirectResponse(url=target_url, status_code=status.HTTP_301_MOVED_PERMANENTLY)

    rendered_html = build_listing_html(listing, base_html, db)
    return HTMLResponse(content=rendered_html, status_code=status.HTTP_200_OK)
