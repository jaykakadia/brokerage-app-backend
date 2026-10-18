import re
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

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
    "gurugram": "Gurugram",
    "sonipat": "Sonipat",
    "hodal": "Hodal",
    "hathin": "Hathin",
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

    # Query DB Location table if db session provided
    if db is not None:
        from app.db.models.location import Location
        locations = db.query(Location.city_name).distinct().all()
        for loc in locations:
            city_name = loc[0]
            if city_name and slugify_city(city_name) == resolved:
                return city_name.strip()

    return None
