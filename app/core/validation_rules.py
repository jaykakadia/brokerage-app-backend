"""
Central validation configuration and rules for listings on TradeCall India.
All price thresholds, locality regexes, and indexing criteria live in this single file.
"""

import re
from typing import Optional, Tuple, Dict, Any

# ==============================================================================
# 1. PRICE THRESHOLDS (All thresholds in one place for easy tuning)
# ==============================================================================

# Hard rejection limits (Invalid values)
INVALID_PRICE_MIN_SALE: float = 10_000.0        # ₹10,000 minimum for complete property sale
INVALID_PRICE_MIN_RENT: float = 500.0           # ₹500 minimum for rent
INVALID_PRICE_MAX: float = 10_000_000_000.0     # ₹1,000 Crore hard ceiling

# Suspicious / Unusual limits (Requires confirmation / flagged for review)
UNUSUAL_RENT_HIGH: float = 500_000.0            # > ₹5 Lac/month rent is unusual (likely full sale price)
UNUSUAL_SALE_LOW: float = 50_000.0              # < ₹50,000 sale is suspicious (likely per sq yd rate or token)
UNUSUAL_RESIDENTIAL_SALE_HIGH: float = 500_000_000.0 # > ₹50 Crore for residential flat/house
UNUSUAL_LAND_COMMERCIAL_HIGH: float = 1_000_000_000.0 # > ₹100 Crore for land/commercial/industrial

# ==============================================================================
# 2. LOCALITY VALIDATION & CLEANING
# ==============================================================================

# Reject words that represent generic or junk placeholders
JUNK_LOCALITY_WORDS = {
    "anywhere", "any where", "any-where", "all", "any", "none", "n/a", "na", "null", "nil",
    "test", "testing", "demo", "unknown", "xyz", "asdf", "random",
    "somewhere", "everywhere", "city", "location", "area"
}

# Distance / directions phrase regex
# Rejects phrases like "500-mtr-away-from-highway", "2 km from bypass", "opposite to bus stand"
# BUT preserves legitimate names containing Road or Highway (e.g. "South Delhi", "Nahar Road", "Mathura Road")
DISTANCE_PHRASE_REGEX = re.compile(
    r'\b(?:\d+[\s-]*(?:mtr|meter|metre|km|kilometer|feet|ft|mile)s?[\s-]*(?:away|from|off)?(?:[\s-]+(?:from|to|near|off))?[\s-]*(?:highway|bypass|station|metro|road|expressway|stand|airport))\b'
    r'|(?:\b(?:opposite|opp|behind|near|beside|adjacent)[\s-]+(?:to[\s-]+)?(?:the[\s-]+)?(?:highway|station|metro|road|bus|expressway|stand|bypass|airport)\b)',
    re.IGNORECASE
)

# Reject phone numbers (10 digits or with Indian prefix)
PHONE_IN_LOCALITY_REGEX = re.compile(
    r'(?:\+?91[\s-]?)?[6-9]\d{9}\b|\b\d{10,}\b'
)

# Reject URLs or domain extensions
URL_IN_LOCALITY_REGEX = re.compile(
    r'https?://|www\.|\b[a-z0-9-]+\.(?:com|in|org|net|io|co|biz)\b',
    re.IGNORECASE
)

# Acronyms and special words to preserve in proper uppercase
PRESERVED_ACRONYMS = {"RPS", "NH", "BPTP", "HUDA", "Omaxe", "SRS", "VIP", "TDI", "NCR", "DLF", "BHK", "PO"}


def clean_and_normalize_locality(value: Optional[str]) -> str:
    """
    Cleans up whitespace, removes accidental quotes/punctuation,
    and formats words cleanly without ruining legitimate acronyms.
    """
    if not value:
        return ""
    # Replace multiple hyphens/underscores/spaces with single space
    cleaned = re.sub(r'[\s_\-]+', ' ', value).strip(" ,.-;/")
    if not cleaned:
        return ""

    words = cleaned.split()
    formatted_words = []
    for w in words:
        upper = w.upper()
        if upper in PRESERVED_ACRONYMS:
            formatted_words.append(upper)
        elif len(w) > 1 and w[0].isalpha() and w.isupper() and len(w) <= 4:
            # Short abbreviations like 'SEC' or 'KUK'
            formatted_words.append(upper)
        else:
            formatted_words.append(w.capitalize())
    return " ".join(formatted_words)


def validate_locality(value: Optional[str], city: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Validates locality field against junk values, distance phrases, URLs, and phone numbers.
    Returns (is_valid, error_message).
    Legitimate names like 'South Delhi', 'Nahar Road', 'NH-19' pass cleanly.
    """
    if not value or not value.strip():
        return False, "Locality is required."

    raw = value.strip()
    norm = clean_and_normalize_locality(raw)

    if len(norm) < 2:
        return False, "Locality name is too short."
    if len(norm) > 60:
        return False, "Locality name cannot exceed 60 characters."

    lower = norm.lower()
    compact = re.sub(r'[\s\-_]+', '', lower)
    if lower in JUNK_LOCALITY_WORDS or compact in {"anywhere", "all", "any", "none", "na", "null", "nil", "test", "testing", "demo", "unknown", "xyz", "asdf"}:
        return False, f"'{raw}' is not a valid locality name. Please specify your sector, colony, or area."

    if URL_IN_LOCALITY_REGEX.search(raw):
        return False, "Locality cannot contain URLs or web links."

    if PHONE_IN_LOCALITY_REGEX.search(raw):
        return False, "Locality cannot contain phone numbers."

    if DISTANCE_PHRASE_REGEX.search(raw):
        return False, (
            "Please provide a specific locality/sector name instead of distance phrases "
            "(e.g., use 'Sector 2' or 'Nahar Road' instead of '500 mtr away from highway')."
        )

    return True, None


# ==============================================================================
# 3. PRICE VALIDATION
# ==============================================================================

def validate_price(
    price: float,
    for_what: str = "sale",
    prop_type: str = ""
) -> Tuple[bool, Optional[str], bool, Optional[str]]:
    """
    Validates listing price according to transaction type and property category.
    Returns: (is_valid, error_message, is_suspicious, warning_message)
    - If is_valid is False: Hard reject with error_message.
    - If is_valid is True and is_suspicious is True: Allow with warning_message.
    """
    if price is None or price <= 0:
        return False, "Price must be a positive number greater than zero.", False, None

    is_rent = str(for_what).lower() == "rent"
    prop_lower = str(prop_type).lower()

    if is_rent:
        if price < INVALID_PRICE_MIN_RENT:
            return False, f"Rent price must be at least ₹{int(INVALID_PRICE_MIN_RENT):,}/month.", False, None
        if price > UNUSUAL_RENT_HIGH:
            return (
                True, None, True,
                f"Monthly rent of ₹{price:,.0f} is unusually high. If this is a property sale, please select 'For Sale'."
            )
    else:
        # Sale transaction
        if price < INVALID_PRICE_MIN_SALE:
            return False, f"Sale price must be at least ₹{int(INVALID_PRICE_MIN_SALE):,}.", False, None

        if price < UNUSUAL_SALE_LOW:
            return (
                True, None, True,
                f"Total sale price of ₹{price:,.0f} is unusually low. Please confirm this is the total property price and not a per-sq.ft rate."
            )

        is_land_or_commercial = any(
            t in prop_lower for t in ["land", "plot", "agriculture", "industrial", "commercial"]
        )
        if is_land_or_commercial and price > UNUSUAL_LAND_COMMERCIAL_HIGH:
            return (
                True, None, True,
                f"Property price of ₹{price:,.0f} (> ₹100 Crore) is exceptionally high. Please verify the amount."
            )
        elif not is_land_or_commercial and price > UNUSUAL_RESIDENTIAL_SALE_HIGH:
            return (
                True, None, True,
                f"Residential price of ₹{price:,.0f} (> ₹50 Crore) is exceptionally high. Please verify the amount."
            )

    return True, None, False, None


# ==============================================================================
# 4. INDEXABILITY RULES
# ==============================================================================

def is_buyer_requirement(listing_or_title: Any, form_data: Optional[Dict[str, Any]] = None) -> bool:
    """
    Returns True if the listing is a buyer requirement post (e.g. 'Looking to buy...').
    Buyer requirements must be kept noindex and omitted from the sitemap.
    Accepts either (title, form_data) or a listing object / dictionary.
    """
    if isinstance(listing_or_title, dict):
        fd = listing_or_title.get("form_data") or {}
        if not fd and "kind" in listing_or_title:
            fd = listing_or_title
        title = listing_or_title.get("title") or ""
    elif hasattr(listing_or_title, "title") and hasattr(listing_or_title, "form_data"):
        fd = getattr(listing_or_title, "form_data") or {}
        title = getattr(listing_or_title, "title") or ""
    else:
        title = str(listing_or_title or "")
        fd = form_data or {}

    if fd.get("kind") == "buyer" or fd.get("posterRole") == "real_buyer":
        return True
    if fd.get("forWhat") == "buyer":
        return True

    clean_title = (title or "").lower().strip()
    if (
        clean_title.startswith("looking to buy")
        or clean_title.startswith("looking to rent")
        or clean_title.startswith("looking for rent")
        or clean_title.startswith("wanted")
        or clean_title.startswith("requirement:")
        or "looking to buy" in clean_title
        or "looking to rent" in clean_title
    ):
        return True
    return False


def is_thin_business(listing: Any) -> bool:
    """
    Determines if a business listing is 'thin' (lacks description and useful details).
    Thin business pages must be marked noindex, follow and excluded from XML sitemaps.
    Accepts a DB model, Pydantic model, or dict.
    """
    if isinstance(listing, dict):
        fd = listing.get("form_data") or {}
        desc = (listing.get("description") or "").strip()
    else:
        fd = getattr(listing, "form_data", None) or {}
        desc = (getattr(listing, "description", None) or "").strip()

    is_biz = fd.get("kind") == "business" or bool(fd.get("businessName") and not fd.get("propType"))
    if not is_biz:
        return False

    has_phone = bool(fd.get("mobile") or fd.get("phone") or fd.get("whatsapp"))
    has_website = bool(fd.get("websiteUrl") or fd.get("website"))
    has_address = bool(fd.get("plot") or fd.get("building") or fd.get("street") or fd.get("landmark"))

    # Thin if no meaningful description AND no useful contact/address details
    if len(desc) < 20 and not (has_phone or has_website or has_address):
        return True
    return False


def should_index_business(listing: Any) -> bool:
    """
    Returns True if a business listing should be indexed in search engines and included in sitemaps.
    """
    return not is_thin_business(listing)

