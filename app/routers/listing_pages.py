import html as html_lib
import json
import re
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.db.models.listing import Listing
from app.routers.city_pages import load_base_index_html, set_or_replace_canonical
from app.routers.sitemap import get_listing_path

router = APIRouter(tags=["Listing Share Pages"])

BASE_URL = "https://tradecall.in"


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


def clean_meta_description(text: str, max_len: int = 160) -> str:
    """Truncates description cleanly at a word boundary without trailing commas or broken words."""
    clean = re.sub(r"<[^>]*>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    if len(clean) <= max_len:
        return clean
    truncated = clean[: max_len - 3]
    # Remove partial trailing word
    truncated = re.sub(r"\s+\S*$", "", truncated).strip()
    # Strip any dangling punctuation (commas, semicolons, dashes, periods)
    truncated = re.sub(r"[,;:\.\-\s]+$", "", truncated).strip()
    return f"{truncated}..."


def pick_og_image(images: list) -> str:
    """Selects JPEG/PNG image if available; otherwise falls back to first WebP or default OG image."""
    if not images:
        return f"{BASE_URL}/og-image.png"

    chosen_fp = None
    # 1. Prefer JPEG / PNG
    for img in images:
        fp = (getattr(img, "file_path", None) or "").strip()
        if not fp:
            continue
        lower = fp.lower()
        if lower.endswith(".jpg") or lower.endswith(".jpeg") or lower.endswith(".png"):
            chosen_fp = fp
            break

    # 2. Fall back to first available image (e.g. .webp)
    if not chosen_fp and images[0].file_path:
        chosen_fp = images[0].file_path.strip()

    if not chosen_fp:
        return f"{BASE_URL}/og-image.png"

    fp_clean = chosen_fp.lstrip("/")
    if fp_clean.startswith("http://") or fp_clean.startswith("https://"):
        return fp_clean
    if fp_clean.startswith("uploads/"):
        return f"{BASE_URL}/{fp_clean}"
    return f"{BASE_URL}/uploads/{fp_clean}"


def set_or_replace_meta(html: str, attr: str, key: str, content: str) -> str:
    """Replaces existing <meta> tag or injects before </head> if missing."""
    escaped_content = html_lib.escape(content, quote=True)
    pattern = rf'<meta\s+{attr}=["\']{re.escape(key)}["\'][^>]*>'
    if re.search(pattern, html, flags=re.IGNORECASE):
        return re.sub(pattern, f'<meta {attr}="{key}" content="{escaped_content}" />', html, count=1, flags=re.IGNORECASE)
    return html.replace("</head>", f'  <meta {attr}="{key}" content="{escaped_content}" />\n</head>')


def build_listing_html(listing: Listing, base_html: str) -> str:
    """Injects listing title, description, canonical, OG tags, and Schema.org JSON-LD."""
    raw_title = listing.title.strip() if listing.title else "Property Listing"
    headline = re.sub(r"\s*\|\s*Tradecall.*$", "", raw_title, flags=re.IGNORECASE).strip() or "Property Listing"
    full_title = f"{headline} | Tradecall"

    price_str = format_price(float(listing.price)) if listing.price else ""
    summary_parts = [p for p in [price_str, listing.location] if p]
    summary_str = " · ".join(summary_parts)

    raw_desc = (listing.description or "").strip()
    clean_desc = re.sub(r"<[^>]*>", " ", raw_desc)
    clean_desc = re.sub(r"\s+", " ", clean_desc).strip()
    if not clean_desc:
        clean_desc = "Verified property listing on TradeCall India with zero brokerage."

    combined_desc = f"{summary_str}. {clean_desc} Contact the owner directly on TradeCall India, zero brokerage." if summary_str else f"{clean_desc} Contact the owner directly on TradeCall India, zero brokerage."
    meta_desc = clean_meta_description(combined_desc, max_len=160)

    canonical_path = get_listing_path(listing.id, listing.title, listing.location, listing.form_data)
    canonical_url = f"{BASE_URL}{canonical_path}"

    image_url = pick_og_image(listing.images or [])

    # Prepare Schema.org JSON-LD
    schema_data = {
        "@context": "https://schema.org",
        "@type": "RealEstateListing",
        "name": headline,
        "description": meta_desc,
        "url": canonical_url,
        "image": [image_url],
    }
    if listing.price and float(listing.price) > 0:
        schema_data["offers"] = {
            "@type": "Offer",
            "price": float(listing.price),
            "priceCurrency": "INR"
        }

    schema_ld = f"""  <!-- RealEstateListing Schema -->
  <script type="application/ld+json">
{json.dumps(schema_data, indent=2)}
  </script>"""

    html = base_html

    # 1. Title (single in-place replacement)
    html = re.sub(r"<title>.*?</title>", f"<title>{html_lib.escape(full_title)}</title>", html, count=1, flags=re.DOTALL)

    # 2. Meta description (single in-place replacement)
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

    # 3. Canonical (self-referencing to canonical listing URL, guaranteed exactly one)
    html = set_or_replace_canonical(html, canonical_url)

    # 4. Robots meta tag (noindex if not approved)
    robots_content = "index, follow" if listing.status == "approved" else "noindex, follow"
    if re.search(r'<meta\s+name=["\']robots["\']', html):
        html = re.sub(
            r'<meta\s+name=["\']robots["\']\s+content=["\'][^"\']*["\']\s*/?>',
            f'<meta name="robots" content="{robots_content}" />',
            html,
            count=1
        )
    else:
        html = html.replace("</head>", f'  <meta name="robots" content="{robots_content}" />\n</head>')

    # 5. OpenGraph and Twitter tags
    # Remove hardcoded 1200x630 dimension tags
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

    # 6. Inject Schema.org JSON-LD before </head>
    html = html.replace("</head>", f"{schema_ld}\n</head>")

    # 7. Inject real, HTML-escaped content inside <div id="root">
    escaped_headline = html_lib.escape(headline)
    escaped_price = html_lib.escape(price_str)
    escaped_loc = html_lib.escape(listing.location or "")
    escaped_desc_body = html_lib.escape(clean_desc)
    escaped_img_src = html_lib.escape(image_url, quote=True)

    root_parts = [
        f"<h1>{escaped_headline}</h1>"
    ]
    if escaped_price:
        root_parts.append(f'<p class="listing-price">{escaped_price}</p>')
    if escaped_loc:
        root_parts.append(f'<p class="listing-location">{escaped_loc}</p>')
    if image_url:
        root_parts.append(f'<img src="{escaped_img_src}" alt="{escaped_headline}" />')
    if escaped_desc_body:
        root_parts.append(f'<p class="listing-description">{escaped_desc_body}</p>')

    root_inner_html = "\n      ".join(root_parts)
    rendered_root = f'<div id="root">\n    <article class="listing-ssr-preview" style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;">\n      {root_inner_html}\n    </article>\n  </div>'

    html = re.sub(r'<div\s+id=["\']root["\'][^>]*>.*?</div>', rendered_root, html, count=1, flags=re.DOTALL)

    return html


def build_404_html(base_html: str) -> str:
    """Builds a real 404 response with noindex for missing listings."""
    html = re.sub(
        r"<title>.*?</title>",
        "<title>404 - Listing Not Found | Tradecall</title>",
        base_html,
        count=1,
        flags=re.DOTALL
    )
    if re.search(r'<meta\s+name=["\']robots["\']', html):
        html = re.sub(
            r'<meta\s+name=["\']robots["\']\s+content=["\'][^"\']*["\']\s*/?>',
            '<meta name="robots" content="noindex, follow" />',
            html,
            count=1
        )
    else:
        html = html.replace("</head>", '  <meta name="robots" content="noindex, follow" />\n</head>')
    return html


@router.api_route("/listing/{listing_id}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_listing_page_by_id(listing_id: str, db: Session = Depends(get_db)):
    base_html = load_base_index_html()
    numeric_id = parse_listing_id(listing_id)
    if not numeric_id:
        return HTMLResponse(content=build_404_html(base_html), status_code=status.HTTP_404_NOT_FOUND)

    listing = db.query(Listing).filter(Listing.id == numeric_id).first()
    if not listing:
        return HTMLResponse(content=build_404_html(base_html), status_code=status.HTTP_404_NOT_FOUND)

    rendered_html = build_listing_html(listing, base_html)
    return HTMLResponse(content=rendered_html, status_code=status.HTTP_200_OK)


@router.api_route("/{city_slug}/{title_slug}/{unique_code}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_listing_page_by_slug(city_slug: str, title_slug: str, unique_code: str, db: Session = Depends(get_db)):
    # Guard against non-listing routes (API endpoints, static assets, docs)
    if city_slug.lower() in {"api", "uploads", "assets", "static", "docs", "redoc", "openapi.json"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    numeric_id = parse_listing_id(unique_code)
    if not numeric_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid listing code")

    base_html = load_base_index_html()

    listing = db.query(Listing).filter(Listing.id == numeric_id).first()
    if not listing:
        return HTMLResponse(content=build_404_html(base_html), status_code=status.HTTP_404_NOT_FOUND)

    rendered_html = build_listing_html(listing, base_html)
    return HTMLResponse(content=rendered_html, status_code=status.HTTP_200_OK)
