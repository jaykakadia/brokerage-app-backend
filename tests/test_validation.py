import pytest
from app.core.validation_rules import (
    validate_locality,
    clean_and_normalize_locality,
    validate_price,
    is_buyer_requirement,
    is_thin_business,
    should_index_business,
    INVALID_PRICE_MIN_SALE,
    INVALID_PRICE_MIN_RENT,
    UNUSUAL_RENT_HIGH,
    UNUSUAL_LAND_COMMERCIAL_HIGH,
)


class TestLocalityValidation:
    def test_valid_localities(self):
        valid_samples = [
            "South Delhi",
            "Nahar Road",
            "Sector 2",
            "Omaxe City",
            "Grand Trunk Road",
            "Highway City",
            "East of Kailash",
            "North Colony",
            "Village Joharkhera",
            "Palwal Camp",
        ]
        for name in valid_samples:
            is_valid, err = validate_locality(name)
            assert is_valid, f"Expected '{name}' to be valid, got error: {err}"
            assert err is None

    def test_reject_junk_localities(self):
        junk_samples = [
            ("anywhere", "junk or placeholder"),
            ("any where", "junk or placeholder"),
            ("all", "not a valid locality name"),
            ("n/a", "not a valid locality name"),
            ("none", "not a valid locality name"),
            ("test", "not a valid locality name"),
        ]
        for name, expected_substr in junk_samples:
            is_valid, err = validate_locality(name)
            assert not is_valid, f"Expected '{name}' to be rejected"
            assert expected_substr.lower() in err.lower() or "not a valid locality" in err.lower()

    def test_reject_distance_and_highway_phrases(self):
        phrases = [
            "500-mtr-away-from-highway",
            "2 km from bypass",
            "near highway",
            "opposite highway",
        ]
        for phrase in phrases:
            is_valid, err = validate_locality(phrase)
            assert not is_valid, f"Expected '{phrase}' to be rejected as distance phrase"
            assert "distance" in err.lower() or "sector" in err.lower()

    def test_reject_urls_and_contacts(self):
        contacts = [
            "Sector 2 www.tradecall.in",
            "Call 9992292828 for details",
            "Near metro +91 9876543210",
        ]
        for val in contacts:
            is_valid, err = validate_locality(val)
            assert not is_valid, f"Expected '{val}' to be rejected for URL/contact info"
            assert "url" in err.lower() or "phone" in err.lower()

    def test_whitespace_normalization(self):
        clean = clean_and_normalize_locality("   Sector   12   Palwal   ")
        assert clean == "Sector 12 Palwal"


class TestPriceValidation:
    def test_valid_normal_prices(self):
        # 50 Lakh sale
        is_valid, err, is_suspicious, warning = validate_price(5000000, "sale", "flat")
        assert is_valid
        assert err is None
        assert not is_suspicious
        assert warning is None

        # 15,000 / month rent
        is_valid, err, is_suspicious, warning = validate_price(15000, "rent", "flat")
        assert is_valid
        assert err is None
        assert not is_suspicious
        assert warning is None

    def test_reject_negative_or_zero_price(self):
        for bad_price in [0, -500, -1]:
            is_valid, err, is_suspicious, warning = validate_price(bad_price, "sale", "flat")
            assert not is_valid
            assert "greater than zero" in err.lower()

    def test_reject_below_absolute_minimum(self):
        # Sale below min (e.g. 500 Rs for sale)
        is_valid, err, is_suspicious, warning = validate_price(500, "sale", "flat")
        assert not is_valid
        assert f"{int(INVALID_PRICE_MIN_SALE):,}" in err

        # Rent below min (e.g. 100 Rs for rent)
        is_valid, err, is_suspicious, warning = validate_price(100, "rent", "flat")
        assert not is_valid
        assert f"{int(INVALID_PRICE_MIN_RENT):,}" in err

    def test_reject_above_absolute_maximum(self):
        # 15,000 Crore -> absurd
        is_valid, err, is_suspicious, warning = validate_price(150_000_000_000, "sale", "commercial")
        assert not is_valid
        assert "exceeds" in err.lower()

    def test_suspicious_rent_triggers_warning_not_reject(self):
        # Rent of 45 Lakh/month is suspicious but valid with warning
        is_valid, err, is_suspicious, warning = validate_price(4_500_000, "rent", "flat")
        assert is_valid
        assert err is None
        assert is_suspicious is True
        assert warning is not None
        assert "unusually high" in warning.lower()

    def test_high_value_land_warning(self):
        # 140 Crore industrial land: warning, not an automatic reject
        is_valid, err, is_suspicious, warning = validate_price(1_400_000_000, "sale", "industrial_land")
        assert is_valid
        assert err is None
        assert is_suspicious is True
        assert warning is not None
        assert "exceptionally high" in warning.lower()


class TestIndexingRules:
    def test_buyer_requirement_detection(self):
        # Kind = buyer
        assert is_buyer_requirement({"kind": "buyer", "title": "Need 3BHK flat"}) is True

        # Looking to buy in title
        assert is_buyer_requirement({"title": "Looking to buy plot in Sector 2"}) is True
        assert is_buyer_requirement({"title": "Looking to rent office space"}) is True
        assert is_buyer_requirement({"title": "Requirement: 2 BHK Flat"}) is True

        # Genuine sale listing
        assert is_buyer_requirement({"title": "3 BHK Luxury Villa in Sector 2", "kind": "property"}) is False

    def test_thin_business_detection(self):
        # Thin business: no description, no address, no contact
        thin = {
            "form_data": {"kind": "business"},
            "description": "",
            "location": "",
            "owner_phone": "",
        }
        assert is_thin_business(thin) is True
        assert should_index_business(thin) is False

        # Rich business: has description and location
        rich = {
            "form_data": {
                "kind": "business",
                "categoryName": "Interior Designer",
                "description": "Full home interiors and turnkey architectural services in Palwal.",
            },
            "description": "Interior design services",
            "location": "Palwal, Haryana",
            "owner_phone": "9992292828",
        }
        assert is_thin_business(rich) is False
        assert should_index_business(rich) is True


class TestApiValidationIntegration:
    def test_create_listing_with_junk_locality(self, client, test_user):
        # Login sets session cookie on test client
        login_res = client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
        assert login_res.status_code == 200

        # Attempt to create with junk locality
        payload = {
            "title": "3 BHK Apartment in Anywhere",
            "price": "4500000",
            "location": "Anywhere, Palwal",
            "locality": "Anywhere",
            "owner_name": "John Doe",
            "owner_role": "Owner",
        }
        res = client.post("/api/v1/listings", data=payload)
        assert res.status_code in (400, 422)
        assert "locality" in res.text.lower() or "valid locality" in res.text.lower()

    def test_create_listing_with_invalid_price(self, client, test_user):
        login_res = client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
        assert login_res.status_code == 200

        # Attempt to create with zero price
        payload = {
            "title": "3 BHK Apartment in Sector 2",
            "price": "0",
            "location": "Sector 2, Palwal",
            "locality": "Sector 2",
            "owner_name": "John Doe",
            "owner_role": "Owner",
        }
        res = client.post("/api/v1/listings", data=payload)
        assert res.status_code in (400, 422)
        assert "price" in res.text.lower()
