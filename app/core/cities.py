import re
import os
import json
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

# Minimum approved listings required for a city hub to be indexable and included in sitemap-hubs
MIN_HUB_LISTINGS: int = 5

# Top Cities matching the frontend TOP_CITIES
TOP_CITIES: List[Dict[str, str]] = [
    {"name": "Mumbai", "slug": "mumbai", "state": "Maharashtra"},
    {"name": "Bangalore", "slug": "bangalore", "state": "Karnataka"},
    {"name": "Pune", "slug": "pune", "state": "Maharashtra"},
    {"name": "Delhi NCR", "slug": "delhi-ncr", "state": "Delhi"},
    {"name": "Hyderabad", "slug": "hyderabad", "state": "Telangana"},
    {"name": "Chennai", "slug": "chennai", "state": "Tamil Nadu"},
    {"name": "Ahmedabad", "slug": "ahmedabad", "state": "Gujarat"},
    {"name": "Kolkata", "slug": "kolkata", "state": "West Bengal"},
]

# Baseline known Indian cities dictionary: slug -> display_name
CITY_SLUG_MAP: Dict[str, str] = {
    "mumbai": "Mumbai",
    "bangalore": "Bangalore",
    "pune": "Pune",
    "delhi-ncr": "Delhi NCR",
    "hyderabad": "Hyderabad",
    "chennai": "Chennai",
    "ahmedabad": "Ahmedabad",
    "kolkata": "Kolkata",
    "palwal": "Palwal",
    "faridabad": "Faridabad",
    "ballabgarh": "Ballabgarh",
    "gurugram": "Gurugram",
    "sonipat": "Sonipat",
    "hodal": "Hodal",
    "hathin": "Hathin",
    "hasanpur": "Hasanpur",
    "nuh-mewat": "Nuh Mewat",
    "panipat": "Panipat",
    "karnal": "Karnal",
    "ambala": "Ambala",
    "rohtak": "Rohtak",
    "hisar": "Hisar",
    "panchkula": "Panchkula",
    "rewari": "Rewari",
    "noida": "Noida",
    "greater-noida": "Greater Noida",
    "ghaziabad": "Ghaziabad",
    "mathura-vrindavan": "Mathura-Vrindavan",
    "mathura": "Mathura",
    "vrindavan": "Vrindavan",
    "lucknow": "Lucknow",
    "kanpur": "Kanpur",
    "varanasi": "Varanasi",
    "agra": "Agra",
    "prayagraj": "Prayagraj",
    "meerut": "Meerut",
    "aligarh": "Aligarh",
    "moradabad": "Moradabad",
    "gorakhpur": "Gorakhpur",
    "nagpur": "Nagpur",
    "thane": "Thane",
    "nashik": "Nashik",
    "navi-mumbai": "Navi Mumbai",
    "aurangabad": "Aurangabad",
    "solapur": "Solapur",
    "mysore": "Mysore",
    "mangalore": "Mangalore",
    "hubli": "Hubli",
    "surat": "Surat",
    "vadodara": "Vadodara",
    "rajkot": "Rajkot",
    "bhavnagar": "Bhavnagar",
    "jamnagar": "Jamnagar",
    "jaipur": "Jaipur",
    "jodhpur": "Jodhpur",
    "kota": "Kota",
    "bikaner": "Bikaner",
    "ajmer": "Ajmer",
    "udaipur": "Udaipur",
    "chandigarh": "Chandigarh",
    "ludhiana": "Ludhiana",
    "amritsar": "Amritsar",
    "jalandhar": "Jalandhar",
    "bhopal": "Bhopal",
    "indore": "Indore",
    "gwalior": "Gwalior",
    "jabalpur": "Jabalpur",
    "ujjain": "Ujjain",
    "coimbatore": "Coimbatore",
    "madurai": "Madurai",
    "salem": "Salem",
    "kochi": "Kochi",
    "thiruvananthapuram": "Thiruvananthapuram",
    "kozhikode": "Kozhikode",
    "visakhapatnam": "Visakhapatnam",
    "vijayawada": "Vijayawada",
    "warangal": "Warangal",
    "patna": "Patna",
    "ranchi": "Ranchi",
    "jamshedpur": "Jamshedpur",
    "dhanbad": "Dhanbad",
    "bhubaneswar": "Bhubaneswar",
    "rourkela": "Rourkela",
    "siliguri": "Siliguri",
    "guwahati": "Guwahati",
    "dehradun": "Dehradun",
    "raipur": "Raipur",
}

# Active towns and cities with approved listings
ACTIVE_CITIES_EXTRAS: Dict[str, str] = {
    "chhata": "Chhata",
    "assandh": "Assandh",
    "tiruvallur": "Tiruvallur",
    "dharamshala": "Dharamshala",
    "mathura-vrindavan": "Mathura-Vrindavan",
    "vrindavan": "Vrindavan",
    "mathura": "Mathura",
    "hasanpur": "Hasanpur",
    "ballabgarh": "Ballabgarh",
    "nuh-mewat": "Nuh Mewat",
    "kota": "Kota",
    "patna": "Patna",
    "varanasi": "Varanasi",
}
CITY_SLUG_MAP.update(ACTIVE_CITIES_EXTRAS)

# Also load all cities from india_locations.json
try:
    _json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "scripts", "data", "india_locations.json"
    )
    if os.path.exists(_json_path):
        with open(_json_path, "r", encoding="utf-8") as _f:
            _loc_data = json.load(_f)
            for _state, _clist in _loc_data.get("states", {}).items():
                for _item in _clist:
                    if isinstance(_item, dict) and "city" in _item:
                        _cname = _item["city"].strip()
                        if _cname:
                            _clean = _cname.lower()
                            _slug = re.sub(r"[^\w\s-]", "", _clean, flags=re.ASCII)
                            _slug = re.sub(r"[\s-]+", "-", _slug)
                            if _slug and _slug not in CITY_SLUG_MAP:
                                CITY_SLUG_MAP[_slug] = _cname
except Exception:
    pass

TOP_CITY_SLUGS = {c["slug"] for c in TOP_CITIES}

ALIASES: Dict[str, str] = {
    "bengaluru": "bangalore",
    "bengaluru-bangalore": "bangalore",
    "bengaluru-urban": "bangalore",
    "bengaluru-rural": "bangalore",
    "delhi": "delhi-ncr",
    "ncr": "delhi-ncr",
    "new-delhi": "delhi-ncr",
    "central-delhi": "delhi-ncr",
    "north-delhi": "delhi-ncr",
    "south-delhi": "delhi-ncr",
    "east-delhi": "delhi-ncr",
    "west-delhi": "delhi-ncr",
    "bombay": "mumbai",
    "calcutta": "kolkata",
    "madras": "chennai",
    "gurgaon": "gurugram",
    "allahabad": "prayagraj",
    "g-noida": "greater-noida",
    "gnida": "greater-noida",
    "nuh": "nuh-mewat",
    "mewat": "nuh-mewat",
    "vrindavan": "mathura-vrindavan",
    "vrindaban": "mathura-vrindavan",
}


def slugify_city(name: str) -> str:
    """Matches frontend getCitySlug()."""
    if not name:
        return ""
    clean = name.strip().lower()
    if re.match(r"^bengaluru", clean) or re.match(r"^bangalore", clean):
        return "bangalore"
    if re.match(r"^delhi(\s*ncr)?$", clean) or clean == "ncr":
        return "delhi-ncr"
    if clean == "gurgaon":
        return "gurugram"

    slug = re.sub(r"[^\w\s-]", "", clean, flags=re.ASCII)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return ALIASES.get(slug, slug)


def get_city_display_name(slug: str, db: Optional[Session] = None) -> Optional[str]:
    """Resolves slug to formatted City display name, checking static map and DB locations."""
    if not slug:
        return None
    clean = slug.strip().lower()
    resolved = ALIASES.get(clean, clean)

    if resolved in CITY_SLUG_MAP:
        return CITY_SLUG_MAP[resolved]

    # Query DB Location & Listing table if db session provided
    if db is not None:
        from app.db.models.location import Location
        from app.db.models.listing import Listing
        locations = db.query(Location.city_name).distinct().all()
        for loc in locations:
            city_name = loc[0]
            if city_name and slugify_city(city_name) == resolved:
                return city_name.strip()
        listings = db.query(Listing.location, Listing.form_data).filter(Listing.status == "approved").all()
        for loc_str, f_data in listings:
            raw = None
            if isinstance(f_data, dict) and f_data.get("city"):
                raw = f_data.get("city")
            elif loc_str:
                parts = [p.strip() for p in loc_str.split(",") if p.strip()]
                raw = parts[-2] if len(parts) >= 3 else (parts[0] if parts else None)
            if raw and slugify_city(str(raw)) == resolved:
                return str(raw).strip().title()

    return None
