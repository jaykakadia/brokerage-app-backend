"""
Property-type landing pages ("Plots in Palwal", "Flats in Faridabad") and the listing
display title shared by every server-rendered page.

A type hub lives at /properties/{city-slug}/{type-slug} and is indexable once the city
has at least MIN_TYPE_HUB_LISTINGS approved listings of that type.
"""
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

# Minimum approved listings of one type in one city for its hub to be indexable / in the sitemap
MIN_TYPE_HUB_LISTINGS: int = 3

# Saved propType values (lowercase) that count as each canonical type; older listings used some of the aliases
PROP_TYPE_ALIASES: Dict[str, tuple] = {
    "flat": ("flat", "apartment", "builder_floor", "builder floor", "studio"),
    "house": ("house", "villa", "kothi", "independent house", "bungalow"),
    "plot": ("plot", "plots"),
    "agriculture": ("agriculture", "agricultural", "farm_land", "farm land"),
    "commercial": ("commercial", "shop", "office", "showroom", "warehouse"),
}

_ALIAS_TO_TYPE: Dict[str, str] = {alias: pt for pt, aliases in PROP_TYPE_ALIASES.items() for alias in aliases}

# URL slug -> hub definition. `name` reads naturally in "… in Palwal"; `unit` is what one listing is called.
TYPE_HUBS: Dict[str, Dict[str, str]] = {
    "flats": {"type": "flat", "name": "Flats", "long": "Flats & Builder Floors", "unit": "flat", "deals": "for Sale & Rent"},
    "houses-villas": {"type": "house", "name": "Houses & Villas", "long": "Independent Houses & Villas", "unit": "house", "deals": "for Sale & Rent"},
    "plots": {"type": "plot", "name": "Plots", "long": "Residential Plots", "unit": "plot", "deals": "for Sale"},
    "agriculture-land": {"type": "agriculture", "name": "Agriculture Land", "long": "Agriculture Land & Farmland", "unit": "agriculture land parcel", "deals": "for Sale"},
    "commercial-property": {"type": "commercial", "name": "Commercial Property", "long": "Shops, Showrooms & Commercial Property", "unit": "commercial property", "deals": "for Sale & Rent"},
    "industrial-land": {"type": "industrial_land", "name": "Industrial Land", "long": "Industrial Land & Plots", "unit": "industrial plot", "deals": "for Sale"},
}

TYPE_TO_HUB_SLUG: Dict[str, str] = {hub["type"]: slug for slug, hub in TYPE_HUBS.items()}

# form_data fields holding the size of each property type (first non-empty pair wins)
_AREA_FIELDS: Dict[str, tuple] = {
    "plot": (("plotArea", "plotUnit", "Sq.Yd"),),
    "agriculture": (("agriArea", "agriUnit", "Acre"),),
    "industrial_land": (("agriArea", "agriUnit", "Acre"),),
    "r_zone_land": (("agriArea", "agriUnit", "Acre"),),
    "flat": (("area", "unit", "Sq.Ft"),),
    "house": (("area", "unit", "Sq.Ft"),),
    "commercial": (("totalArea", "totalUnit", "Sq.Ft"), ("builtArea", "builtUnit", "Sq.Ft")),
}


def canonical_prop_type(form_data: Any) -> Optional[str]:
    """The listing's property type as one of the filter values (flat, house, plot, …), or None."""
    if not isinstance(form_data, dict):
        return None
    raw = str(form_data.get("propType") or "").strip().lower()
    if not raw:
        return None
    return _ALIAS_TO_TYPE.get(raw, raw)


def listing_area_label(form_data: Any) -> str:
    """Size as entered in the post-listing form, e.g. "180 Sq.Yd"; '' when not given. Mirrors the frontend."""
    if not isinstance(form_data, dict) or form_data.get("kind") == "business":
        return ""
    for area_key, unit_key, default_unit in _AREA_FIELDS.get(str(form_data.get("propType") or ""), ()):
        area = str(form_data.get(area_key) or "").strip()
        try:
            if not area or float(area.replace(",", "")) <= 0:
                continue
        except ValueError:
            continue
        unit = str(form_data.get(unit_key) or default_unit).strip()
        return f"{area} {unit}" if unit else ""
    return ""


def listing_area_value(form_data: Any) -> Optional[float]:
    """Numeric size of the listing in its own unit, for size ranges on hub pages."""
    label = listing_area_label(form_data)
    if not label:
        return None
    try:
        return float(label.split(" ")[0].replace(",", ""))
    except ValueError:
        return None


def clean_listing_title(raw_title: Optional[str]) -> str:
    """Stored title without brand suffix or the BHK prefixes that older listings put on land."""
    title = re.sub(r"\s*\|\s*TradeCall.*$", "", (raw_title or "").strip(), flags=re.IGNORECASE).strip()
    title = re.sub(r"\b\d+\s*BHK\+?\s+(Agriculture(?:\s+Land)?)\b", r"\1", title, flags=re.IGNORECASE)
    title = re.sub(r"\b\d+\s*BHK\+?\s+(Plot)\b", r"\1", title, flags=re.IGNORECASE)
    title = re.sub(r"\b\d+\s*BHK\+?\s+(Commercial(?:\s+Property)?)\b", r"\1", title, flags=re.IGNORECASE)
    title = re.sub(r"\b\d+\s*BHK\+?\s+(Industrial(?:\s+Land)?)\b", r"\1", title, flags=re.IGNORECASE)
    return title


def listing_display_title(raw_title: Optional[str], form_data: Any) -> str:
    """
    Public title of a property listing, led by its size: "180 Sq.Yd Plot for Sale in Omaxe City, Palwal".
    Same rule as the frontend's publicListingTitle, so server HTML and the app show one title.
    """
    title = clean_listing_title(raw_title)
    area = listing_area_label(form_data)
    if not title or not area:
        return title
    amount = re.escape(area.split(" ")[0])
    if re.search(rf"(^|[^\d.]){amount}\s*[a-z]", title, flags=re.IGNORECASE):
        return title
    looking = re.match(r"^(Looking (?:to Buy|for Rent|for))\s+", title, flags=re.IGNORECASE)
    if looking:
        return f"{looking.group(1)} {area} {title[looking.end():]}"
    return f"{area} {title}"


def is_rental(form_data: Any, title: Optional[str] = None) -> bool:
    """True when the listing is offered for rent or lease."""
    raw = ""
    if isinstance(form_data, dict):
        raw = str(form_data.get("forWhat") or form_data.get("deal") or form_data.get("purpose") or "").lower()
    if raw:
        return "rent" in raw or "lease" in raw
    return bool(re.search(r"\bfor rent\b", title or "", flags=re.IGNORECASE))


def listing_city_slug(location: Optional[str], form_data: Any) -> str:
    """Slug of the city a listing belongs to: its saved city, else the city part of "Locality, City, State"."""
    from app.core.cities import slugify_city

    raw_city = form_data.get("city") if isinstance(form_data, dict) else None
    if not raw_city and location:
        parts = [p.strip() for p in location.split(",") if p.strip()]
        raw_city = parts[-2] if len(parts) >= 3 else (parts[0] if parts else None)
    return slugify_city(str(raw_city)) if raw_city else ""


_hub_counts_cache: Dict[str, Any] = {"timestamp": 0.0, "data": None}
HUB_COUNTS_TTL_SECONDS = 300
_seller_rows_cache: Dict[str, Any] = {"timestamp": 0.0, "data": None}
SELLER_ROWS_TTL_SECONDS = 60


def clear_type_hub_cache() -> None:
    _hub_counts_cache["timestamp"] = 0.0
    _hub_counts_cache["data"] = None
    _seller_rows_cache["timestamp"] = 0.0
    _seller_rows_cache["data"] = None


def approved_seller_rows(db) -> List[Any]:
    """
    Approved property listings from sellers (no buyer requirements, no businesses), featured first then newest.
    Light rows (id, title, location, price, form_data) cached for a minute: hub pages read them on every request.
    """
    import time
    from app.db.models.listing import Listing

    now = time.time()
    if _seller_rows_cache["data"] is not None and now - _seller_rows_cache["timestamp"] < SELLER_ROWS_TTL_SECONDS:
        return _seller_rows_cache["data"]
    rows = (
        db.query(Listing.id, Listing.title, Listing.location, Listing.price, Listing.form_data)
        .filter(Listing.status == "approved")
        .order_by(Listing.is_featured.desc(), Listing.id.desc())
        .all()
    )
    rows = [r for r in rows if isinstance(r.form_data, dict) and r.form_data.get("kind") not in ("business", "buyer")]
    _seller_rows_cache["data"] = rows
    _seller_rows_cache["timestamp"] = now
    return rows


def compute_type_hub_counts(db) -> List[Dict[str, Any]]:
    """
    Every (city, type) pair with approved, non-buyer property listings:
    [{"city", "city_slug", "type", "type_slug", "name", "count"}], largest first.
    Cached for a few minutes: every server-rendered page links to these hubs.
    """
    import time
    from app.core.cities import get_city_display_name
    from app.db.models.listing import Listing

    now = time.time()
    if _hub_counts_cache["data"] is not None and now - _hub_counts_cache["timestamp"] < HUB_COUNTS_TTL_SECONDS:
        return _hub_counts_cache["data"]

    rows = db.query(Listing.location, Listing.form_data).filter(Listing.status == "approved").all()
    counts: Dict[tuple, int] = defaultdict(int)
    for location, form_data in rows:
        if not isinstance(form_data, dict) or form_data.get("kind") in ("business", "buyer"):
            continue
        hub_slug = TYPE_TO_HUB_SLUG.get(canonical_prop_type(form_data) or "")
        if not hub_slug:
            continue
        city_slug = listing_city_slug(location, form_data)
        if city_slug:
            counts[(city_slug, hub_slug)] += 1

    names: Dict[str, Optional[str]] = {}
    hubs: List[Dict[str, Any]] = []
    for (city_slug, hub_slug), count in counts.items():
        if city_slug not in names:
            names[city_slug] = get_city_display_name(city_slug, db=db)
        if not names[city_slug]:
            continue
        hub = TYPE_HUBS[hub_slug]
        hubs.append({
            "city": names[city_slug],
            "city_slug": city_slug,
            "type": hub["type"],
            "type_slug": hub_slug,
            "name": hub["name"],
            "count": count,
        })
    hubs.sort(key=lambda h: (-h["count"], h["city_slug"], h["type_slug"]))
    _hub_counts_cache["data"] = hubs
    _hub_counts_cache["timestamp"] = now
    return hubs
