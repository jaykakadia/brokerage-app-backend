"""
Server-rendered property-type landing pages: /properties/{city}/{type}
("Plots in Palwal", "Flats in Faridabad"). Each page is built from live listing data:
counts, price and size ranges, top localities, the listings themselves, and FAQs.
"""
import html as html_lib
import json
import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.cities import get_city_display_name, slugify_city
from app.core.dependencies import get_db
from app.core.type_hubs import (
    MIN_TYPE_HUB_LISTINGS,
    approved_seller_rows,
    TYPE_HUBS,
    canonical_prop_type,
    compute_type_hub_counts,
    is_rental,
    listing_area_label,
    listing_area_value,
    listing_city_slug,
    listing_display_title,
)
from app.routers.city_pages import (
    BASE_URL,
    PAGE_SIZE,
    compute_price_stats,
    format_price,
    load_base_index_html,
    set_or_replace_canonical,
    set_or_replace_meta,
    set_or_replace_rel_links,
    slugify_locality,
)
from app.routers.sitemap import get_listing_path

router = APIRouter(tags=["Property Type Hubs"])

# What a buyer should check for each property type; shown in the page FAQ
_CHECKS: Dict[str, str] = {
    "flat": "check the builder's RERA registration, the occupancy certificate, the sale deed chain and society maintenance dues",
    "house": "check the registry (sale deed) chain, the approved building plan, property tax receipts and that the plot size on paper matches the site",
    "plot": "check the registry and jamabandi (nakal), the mutation (intkal), the approved layout or DTCP/HUDA status, and measure the plot and the front road on site",
    "agriculture": "check the jamabandi and mutation for the khasra numbers, confirm the access road (rasta) on the revenue map, and ask about any change-of-land-use restrictions",
    "commercial": "check the commercial land-use approval, the sale deed chain, parking and fire NOC, and the frontage on the main road",
    "industrial_land": "check the industrial land-use (CLU) status, road width for heavy vehicles, power and water availability, and the jamabandi for the khasra numbers",
}


def _not_found(base_html: str, title: str) -> HTMLResponse:
    html = re.sub(r"<title>.*?</title>", f"<title>{html_lib.escape(title)}</title>", base_html, count=1, flags=re.DOTALL)
    html = set_or_replace_meta(html, "name", "robots", "noindex, follow")
    html = re.sub(r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>', "", html, flags=re.IGNORECASE)
    return HTMLResponse(content=html, status_code=status.HTTP_404_NOT_FOUND, media_type="text/html")


def get_city_seller_listings(city_slug: str, db: Session) -> List[Any]:
    """Approved seller listings whose own city is `city_slug` (featured first, newest next)."""
    return [l for l in approved_seller_rows(db) if listing_city_slug(l.location, l.form_data) == city_slug]


def _size_range(listings: List[Any]) -> str:
    """ "50 to 500 Sq.Yd" for the unit most listings use, or '' when sizes are unknown."""
    by_unit: Dict[str, List[float]] = {}
    for l in listings:
        label = listing_area_label(l.form_data)
        value = listing_area_value(l.form_data)
        if label and value:
            by_unit.setdefault(label.split(" ", 1)[1], []).append(value)
    if not by_unit:
        return ""
    unit, values = max(by_unit.items(), key=lambda kv: len(kv[1]))
    if len(values) < 2:
        return ""
    fmt = lambda v: f"{v:g}"
    low, high = min(values), max(values)
    return f"{fmt(low)} {unit}" if low == high else f"{fmt(low)} to {fmt(high)} {unit}"


def _top_localities(listings: List[Any], city_name: str) -> List[tuple]:
    counter: Counter = Counter()
    for l in listings:
        loc = str(l.form_data.get("locality") or "").strip() if isinstance(l.form_data, dict) else ""
        if not loc and l.location:
            loc = l.location.split(",")[0].strip()
        if loc and loc.lower() != city_name.lower():
            counter[loc] += 1
    return counter.most_common(8)


def build_type_hub_data(city_slug: str, type_slug: str, db: Session) -> Optional[Dict[str, Any]]:
    """
    Everything a "{type} in {city}" page says, built from live listings. The server-rendered page and
    the app (through /api/v1/listings/type-hubs/{city}/{type}) both use this, so visitors and search
    engines read the same content. None when the city or type is unknown.
    """
    type_key = type_slug.strip().lower()
    hub = TYPE_HUBS.get(type_key)
    city_name = get_city_display_name(city_slug, db=db)
    if not hub or not city_name:
        return None

    norm_city = slugify_city(city_slug)
    name, unit, deals = hub["name"], hub["unit"], hub["deals"]
    path = f"/properties/{norm_city}/{type_key}"

    city_listings = get_city_seller_listings(norm_city, db)
    listings = [l for l in city_listings if canonical_prop_type(l.form_data) == hub["type"]]
    total = len(listings)

    # --- Facts from the listings ---
    stats = compute_price_stats(listings)
    priced = len([l for l in listings if l.price and float(l.price) > 0])
    min_p, med_p, max_p = format_price(stats["min"]), format_price(stats["median"]), format_price(stats["max"])
    has_prices = priced >= 3 and bool(min_p and max_p)
    size_range = _size_range(listings)
    rent_count = len([l for l in listings if is_rental(l.form_data, l.title)])
    sale_count = total - rent_count
    top_localities = _top_localities(listings, city_name)
    locality_names = [loc for loc, _ in top_localities]

    # Localities that have their own hub page (2+ approved listings in the city)
    city_locality_counts: Counter = Counter()
    for l in city_listings:
        loc = str(l.form_data.get("locality") or "").strip()
        if loc:
            city_locality_counts[slugify_locality(loc)] += 1
    localities = []
    for loc, count in top_localities:
        loc_slug = slugify_locality(loc)
        has_page = bool(loc_slug) and loc_slug != norm_city and city_locality_counts.get(loc_slug, 0) >= 2
        localities.append({"name": loc, "count": count, "path": f"/{norm_city}/{loc_slug}" if has_page else None})

    # --- Head ---
    title = f"{name} in {city_name} {deals} | TradeCall India"
    if total:
        bits = [f"{total} verified {name.lower()} in {city_name}"]
        if has_prices:
            bits.append(f"priced from {min_p} to {max_p}")
        description = (
            f"{', '.join(bits)}. See photos, sizes and locations, and contact owners and dealers directly "
            f"with zero brokerage on TradeCall India."
        )
    else:
        description = (
            f"Looking for {name.lower()} in {city_name}? No verified listings right now. Explore other property types "
            f"in {city_name} or post your requirement free on TradeCall India."
        )

    # --- Body copy ---
    intro: List[str] = []
    if total:
        first = f"TradeCall India currently lists {total} verified {name.lower()} in {city_name}"
        if sale_count and rent_count:
            first += f": {sale_count} for sale and {rent_count} for rent"
        elif rent_count:
            first += ", all available for rent"
        intro.append(first + ".")
        if has_prices:
            intro.append(f"Asking prices run from {min_p} to {max_p}, with a median of about {med_p}.")
        if size_range:
            intro.append(f"Sizes on offer range from {size_range}.")
        if locality_names:
            intro.append(f"Most of these listings are in {', '.join(locality_names[:5])}.")
        intro.append(
            "Every listing shows the size, price, photos and exact locality, and you contact the owner or dealer "
            "directly, so there is no brokerage to pay."
        )
    else:
        intro.append(
            f"There are no verified {name.lower()} listed in {city_name} right now. New listings are added every day; "
            f"check the other property types in {city_name} below, or post your requirement free and let sellers contact you."
        )

    faqs = []
    if has_prices:
        faqs.append({
            "question": f"What is the price of {name.lower()} in {city_name}?",
            "answer": f"The {priced} priced {name.lower()} listed in {city_name} on TradeCall India range from {min_p} to {max_p}. "
                      f"The median asking price is about {med_p}.",
        })
    if total and locality_names:
        faqs.append({
            "question": f"Which areas of {city_name} have {name.lower()} available?",
            "answer": (f"Current listings are in {', '.join(locality_names[:6])}. "
                       + (f"Sizes range from {size_range}." if size_range else "")).strip(),
        })
    faqs.append({
        "question": f"Do I pay brokerage to buy or rent a {unit} in {city_name} through TradeCall India?",
        "answer": "No. TradeCall India charges buyers and tenants zero brokerage. You see the owner's or dealer's contact "
                  "on the listing and deal with them directly.",
    })
    faqs.append({
        "question": f"What should I check before buying a {unit} in {city_name}?",
        "answer": f"Before paying any token amount, {_CHECKS.get(hub['type'], 'check the ownership documents and visit the site')}.",
    })
    faqs.append({
        "question": f"How do I list my {unit} in {city_name} for free?",
        "answer": f"Click 'Post Free', choose {name} as the property type and {city_name} as the city, add the size, price "
                  f"and photos, and submit. Listings go live after a quick verification.",
    })

    all_hubs = compute_type_hub_counts(db)
    link = lambda h: {"label": f'{h["name"]} in {h["city"]}', "count": h["count"], "path": f'/properties/{h["city_slug"]}/{h["type_slug"]}'}
    same_city = [link(h) for h in all_hubs if h["city_slug"] == norm_city and h["type_slug"] != type_key]
    same_type = [
        link(h) for h in all_hubs
        if h["type_slug"] == type_key and h["city_slug"] != norm_city and h["count"] >= MIN_TYPE_HUB_LISTINGS
    ][:10]

    return {
        "city": city_name,
        "city_slug": norm_city,
        "type": hub["type"],
        "type_slug": type_key,
        "name": name,
        "deals": deals,
        "heading": f"{name} in {city_name}",
        "path": path,
        "title": title,
        "description": description,
        "total": total,
        "indexable": total >= MIN_TYPE_HUB_LISTINGS,
        "intro": " ".join(intro),
        "faqs": faqs,
        "localities": localities,
        "other_types": same_city,
        "other_cities": same_type,
        "_listings": listings,
    }


@router.get("/api/v1/listings/type-hubs/{city_slug}/{type_slug}")
def get_type_hub_data(city_slug: str, type_slug: str, db: Session = Depends(get_db)):
    """Content of one property-type landing page, for the app to show the same text the server renders."""
    data = build_type_hub_data(city_slug, type_slug, db)
    if data is None:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"status": "error", "message": "Unknown city or property type"})
    return {"status": "success", "data": {k: v for k, v in data.items() if not k.startswith("_")}}


@router.api_route("/properties/{city_slug}/{type_slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_type_hub_page(
    city_slug: str,
    type_slug: str,
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    base_html = load_base_index_html()
    data = build_type_hub_data(city_slug, type_slug, db)
    if data is None:
        return _not_found(base_html, "404 - Page Not Found | TradeCall India")

    name, city_name, norm_city, path = data["name"], data["city"], data["city_slug"], data["path"]
    listings: List[Any] = data["_listings"]
    total = data["total"]
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    if page > total_pages:
        return _not_found(base_html, f"Page {page} Not Found - {name} in {city_name} | TradeCall India")

    page_listings = listings[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    page_suffix = f" - Page {page}" if page > 1 else ""
    canonical = f"{BASE_URL}{path}" if page == 1 else f"{BASE_URL}{path}?page={page}"
    prev_url = f"{BASE_URL}{path}" if page == 2 else (f"{BASE_URL}{path}?page={page - 1}" if page > 2 else None)
    next_url = f"{BASE_URL}{path}?page={page + 1}" if page < total_pages else None

    extra_filters = any(k != "page" for k in request.query_params.keys())
    robots_content = "index, follow" if data["indexable"] and not extra_filters else "noindex, follow"

    title = data["title"].replace(" | TradeCall India", f"{page_suffix} | TradeCall India")
    description = data["description"] + page_suffix
    faqs = data["faqs"]

    # --- Structured data ---
    breadcrumb_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": f"Properties in {city_name}", "item": f"{BASE_URL}/properties/{norm_city}"},
            {"@type": "ListItem", "position": 3, "name": data["heading"], "item": f"{BASE_URL}{path}"},
        ],
    }
    item_list_ld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"{data['heading']}{page_suffix}",
        "numberOfItems": len(page_listings),
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": (page - 1) * PAGE_SIZE + idx,
                "name": listing_display_title(l.title, l.form_data) or data["heading"],
                "url": f"{BASE_URL}{get_listing_path(l.id, l.title, l.location, l.form_data)}",
            }
            for idx, l in enumerate(page_listings, start=1)
        ],
    }
    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": f["question"], "acceptedAnswer": {"@type": "Answer", "text": f["answer"]}}
            for f in faqs
        ],
    }
    schemas = "\n".join(
        f'  <script type="application/ld+json">\n{json.dumps(ld, indent=2)}\n  </script>'
        for ld in (breadcrumb_ld, item_list_ld, faq_ld)
    )

    html = base_html
    html = re.sub(r"<title>.*?</title>", lambda _m: f"<title>{html_lib.escape(title)}</title>", html, count=1, flags=re.DOTALL)
    html = set_or_replace_meta(html, "name", "description", description)
    html = set_or_replace_canonical(html, canonical)
    html = set_or_replace_rel_links(html, prev_url, next_url)
    html = set_or_replace_meta(html, "name", "robots", robots_content)
    html = set_or_replace_meta(html, "property", "og:title", title)
    html = set_or_replace_meta(html, "property", "og:description", description)
    html = set_or_replace_meta(html, "property", "og:url", canonical)
    html = set_or_replace_meta(html, "name", "twitter:title", title)
    html = set_or_replace_meta(html, "name", "twitter:description", description)
    html = html.replace("</head>", f"{schemas}\n</head>")

    # --- Body markup ---
    esc = html_lib.escape
    listing_items = []
    for l in page_listings:
        l_path = get_listing_path(l.id, l.title, l.location, l.form_data)
        p_str = format_price(float(l.price)) if l.price else ""
        price_tag = f" - <strong>{esc(p_str)}</strong>" if p_str else ""
        listing_items.append(
            f'<li><a href="{l_path}">{esc(listing_display_title(l.title, l.form_data) or name)}</a>{price_tag}'
            f' in {esc(l.location or city_name)}</li>'
        )

    locality_items = [
        (f'<li><a href="{loc["path"]}">{esc(loc["name"])} ({loc["count"]})</a></li>' if loc["path"]
         else f'<li>{esc(loc["name"])} ({loc["count"]})</li>')
        for loc in data["localities"]
    ]
    link_item = lambda h: f'<li><a href="{h["path"]}">{esc(h["label"])}</a> ({h["count"]})</li>'
    same_city_items = [link_item(h) for h in data["other_types"]]
    same_type_items = [link_item(h) for h in data["other_cities"]]

    pagination_nav = ""
    if total_pages > 1:
        active_attr = ' class="active"'
        links = "\n".join(
            '<li><a href="{}"{}>{}</a></li>'.format(path if p == 1 else f"{path}?page={p}", active_attr if p == page else "", p)
            for p in range(1, total_pages + 1)
        )
        pagination_nav = f'<nav aria-label="Pagination" class="pagination-nav"><ul class="pagination-links">\n{links}\n</ul></nav>'

    faq_markup = "\n".join(f"<dt>{esc(f['question'])}</dt>\n<dd>{esc(f['answer'])}</dd>" for f in faqs)

    def section(heading: str, items: List[str]) -> str:
        if not items:
            return ""
        joined = "\n            ".join(items)
        return f"""<section>
          <h2>{esc(heading)}</h2>
          <ul>
            {joined}
          </ul>
        </section>"""

    root_ssr = f"""<div id="root">
    <div class="ssr-fallback" style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;">
      <main class="city-ssr-wrap">
        <nav aria-label="Breadcrumb"><a href="/">Home</a> &rarr; <a href="/properties/{norm_city}">Properties in {esc(city_name)}</a> &rarr; {esc(data["heading"])}</nav>
        <h1>{esc(data["heading"])}{esc(page_suffix)}</h1>
        <p>{esc(data["intro"])}</p>
        {section(f"{name} {data['deals']} in {city_name} (Showing {len(page_listings)} of {total})", listing_items)}
        {pagination_nav}
        {section(f"Localities with {name} in {city_name}", locality_items)}
        {section(f"Other Property Types in {city_name}", same_city_items)}
        {section(f"{name} in Other Cities", same_type_items)}
        <section>
          <h2>Frequently Asked Questions about {esc(data["heading"])}</h2>
          <dl>
{faq_markup}
          </dl>
        </section>
        <p><a href="/properties/{norm_city}">All properties in {esc(city_name)}</a> · <a href="/post-listing">Post a free listing in {esc(city_name)}</a></p>
      </main>
    </div>
  </div>"""

    html = re.sub(r'<div\s+id=["\']root["\'][^>]*>.*?</div>', lambda _m: root_ssr, html, count=1, flags=re.DOTALL)
    return HTMLResponse(content=html, status_code=status.HTTP_200_OK, media_type="text/html")
