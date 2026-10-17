import os
import re
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.db.models.listing import Listing
from app.core.cities import get_city_display_name, slugify_city, TOP_CITY_SLUGS

router = APIRouter(tags=["City Pages"])

BASE_URL = "https://tradecall.in"


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


def city_has_active_listings(city_slug: str, db: Session) -> bool:
    """Checks if there is at least 1 approved listing in the city."""
    norm_slug = slugify_city(city_slug)
    rows = db.query(Listing.location, Listing.form_data).filter(Listing.status == "approved").all()
    for loc_str, f_data in rows:
        raw_city = None
        if loc_str:
            parts = [p.strip() for p in loc_str.split(",") if p.strip()]
            raw_city = parts[-2] if len(parts) >= 3 else (parts[0] if parts else None)
        if not raw_city and isinstance(f_data, dict):
            raw_city = f_data.get("city")
        if raw_city and slugify_city(raw_city) == norm_slug:
            return True
    return False


@router.api_route("/properties/{city_slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_city_properties_page(city_slug: str, db: Session = Depends(get_db)):
    """
    Renders index.html with server-injected meta tags, title, canonical,
    and BreadcrumbList JSON-LD for the requested city.
    Unknown city returns 404 status code for both GET and HEAD.
    Cities with zero listings receive <meta name="robots" content="noindex">,
    except for top cities.
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
    is_top_city = norm_slug in TOP_CITY_SLUGS
    has_listings = is_top_city or city_has_active_listings(norm_slug, db)

    title = f"Properties in {city_name} | Buy, Rent & Commercial | Tradecall"
    description = f"Find the best residential and commercial properties in {city_name} on Tradecall..."
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

    # 3. Replace or inject canonical
    if re.search(r'<link\s+rel=["\']canonical["\']', html):
        html = re.sub(
            r'<link\s+rel=["\']canonical["\']\s+href=["\'][^"\']*["\']\s*/?>',
            f'<link rel="canonical" href="{canonical}" />',
            html,
            count=1
        )
    else:
        html = html.replace("</head>", f'  <link rel="canonical" href="{canonical}" />\n</head>')

    # 4. Robots meta tag: noindex for non-top cities with zero active listings
    robots_content = "index, follow" if has_listings else "noindex"
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
    html = re.sub(
        r'<meta\s+property=["\']og:title["\']\s+content=["\'][^"\']*["\']\s*/?>',
        f'<meta property="og:title" content="{title}" />',
        html,
        count=1
    )
    html = re.sub(
        r'<meta\s+property=["\']og:description["\']\s+content=["\'][^"\']*["\']\s*/?>',
        f'<meta property="og:description" content="{description}" />',
        html,
        count=1
    )
    html = re.sub(
        r'<meta\s+property=["\']og:url["\']\s+content=["\'][^"\']*["\']\s*/?>',
        f'<meta property="og:url" content="{canonical}" />',
        html,
        count=1
    )
    html = re.sub(
        r'<meta\s+name=["\']twitter:title["\']\s+content=["\'][^"\']*["\']\s*/?>',
        f'<meta name="twitter:title" content="{title}" />',
        html,
        count=1
    )
    html = re.sub(
        r'<meta\s+name=["\']twitter:description["\']\s+content=["\'][^"\']*["\']\s*/?>',
        f'<meta name="twitter:description" content="{description}" />',
        html,
        count=1
    )

    # 6. Inject BreadcrumbList JSON-LD before </head>
    html = html.replace("</head>", f"{breadcrumb_ld}\n</head>")

    return HTMLResponse(content=html, status_code=status.HTTP_200_OK, media_type="text/html")
