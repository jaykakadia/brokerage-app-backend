"""Property-type landing pages: /properties/{city}/{type} ("Plots in Palwal")."""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.type_hubs import clear_type_hub_cache, listing_display_title
from app.db.models.listing import Listing
from app.db.models.user import User


def _seed(db: Session) -> None:
    user = User(email="type_hub_test@tradecall.in", password_hash="x", name="Hub Owner", phone="9999999981", role="owner", status="active")
    db.add(user)
    db.commit()
    db.refresh(user)

    def add(title, locality, price, form):
        db.add(Listing(
            user_id=user.id, title=title, location=f"{locality}, Palwal, Haryana", price=price,
            owner_name="Hub Owner", status="approved",
            form_data={"kind": "owner", "city": "Palwal", "locality": locality, "forWhat": "sale", **form},
        ))

    for i, (area, price) in enumerate([("100", 1500000), ("150", 2250000), ("200", 3000000), ("180", 14400000)]):
        add(f"Plot for Sale in Omaxe City, Palwal", "Omaxe City" if i < 3 else "Village Kithwari", price,
            {"propType": "plot", "plotArea": area, "plotUnit": "Sq.Yd"})
    add("Agriculture Land for Sale in Village Khambi, Palwal", "Village Khambi", 78000000,
        {"propType": "agriculture", "agriArea": "6", "agriUnit": "Acre"})
    add("2BHK Flat / Builder Floor for Sale in Sector 2, Palwal", "Sector 2", 4000000,
        {"propType": "flat", "area": "1200", "unit": "Sq.Ft"})
    # A buyer requirement must not count as a plot for sale
    db.add(Listing(
        user_id=user.id, title="Looking to Buy Plot in Kithwari, Palwal", location="Kithwari, Palwal, Haryana",
        price=2500000, owner_name="Buyer", status="approved",
        form_data={"kind": "buyer", "city": "Palwal", "propType": "plot", "plotArea": "100", "plotUnit": "Sq.Yd"},
    ))
    # A listing in another city whose locality merely contains "Palwal" is not a Palwal plot
    db.add(Listing(
        user_id=user.id, title="Plot for Sale in Palwal Colony, Kurukshetra", location="Palwal Colony, Kurukshetra, Haryana",
        price=4000000, owner_name="Hub Owner", status="approved",
        form_data={"kind": "owner", "city": "Kurukshetra", "locality": "Palwal Colony", "propType": "plot", "plotArea": "306", "plotUnit": "Sq.Yd"},
    ))
    db.commit()
    clear_type_hub_cache()


def test_display_title_leads_with_area():
    plot = {"kind": "owner", "propType": "plot", "plotArea": "180", "plotUnit": "Sq.Yd"}
    assert listing_display_title("Plot for Sale in Omaxe City, Palwal", plot) == "180 Sq.Yd Plot for Sale in Omaxe City, Palwal"
    # Already states the size: not repeated
    assert listing_display_title("180 Sq.Yd Plot for Sale", plot) == "180 Sq.Yd Plot for Sale"
    # No area entered, or a business: unchanged
    assert listing_display_title("Plot for Sale", {"propType": "plot", "plotArea": ""}) == "Plot for Sale"
    assert listing_display_title("Sharma Architects", {"kind": "business", "area": "Sector 2"}) == "Sharma Architects"
    # Old land titles lose the BHK prefix
    agri = {"propType": "agriculture", "agriArea": "6", "agriUnit": "Acre"}
    assert listing_display_title("2BHK Agriculture Land for Sale in Khambi", agri) == "6 Acre Agriculture Land for Sale in Khambi"


def test_type_hub_page_is_indexable_and_built_from_listings(client: TestClient, db_session: Session):
    _seed(db_session)
    res = client.get("/properties/palwal/plots")
    assert res.status_code == 200
    html = res.text
    assert "<title>Plots in Palwal for Sale | TradeCall India</title>" in html
    assert "<h1>Plots in Palwal</h1>" in html
    assert '<link rel="canonical" href="https://tradecall.in/properties/palwal/plots" />' in html
    assert '<meta name="robots" content="index, follow" />' in html
    # 4 seller plots; the buyer requirement, the flat and the agriculture land are left out
    assert "currently lists 4 verified plots in Palwal" in html
    assert "100 Sq.Yd Plot for Sale in Omaxe City, Palwal" in html
    assert "Looking to Buy" not in html
    assert "Agriculture Land for Sale in Village Khambi" not in html
    assert "Kurukshetra" not in html
    # Facts and structured data
    assert "100 to 200 Sq.Yd" in html
    assert '"@type": "FAQPage"' in html and '"@type": "ItemList"' in html and '"@type": "BreadcrumbList"' in html
    # Links to the city hub and to this city's other type pages
    assert 'href="/properties/palwal"' in html
    assert 'href="/properties/palwal/flats"' in html


def test_thin_unknown_and_filtered_type_hubs_are_not_indexable(client: TestClient, db_session: Session):
    _seed(db_session)
    # Only 1 flat in Palwal: page works for visitors but is kept out of the index
    thin = client.get("/properties/palwal/flats")
    assert thin.status_code == 200
    assert '<meta name="robots" content="noindex, follow" />' in thin.text
    # Filter parameters never create indexable duplicates
    filtered = client.get("/properties/palwal/plots?minPrice=100")
    assert '<meta name="robots" content="noindex, follow" />' in filtered.text
    # Unknown type or city, or a page past the end
    assert client.get("/properties/palwal/castles").status_code == 404
    assert client.get("/properties/atlantis/plots").status_code == 404
    assert client.get("/properties/palwal/plots?page=9").status_code == 404


def test_type_hubs_api_sitemap_and_internal_links(client: TestClient, db_session: Session):
    _seed(db_session)
    hubs = client.get("/api/v1/listings/type-hubs").json()["data"]
    assert hubs == [{"city": "Palwal", "city_slug": "palwal", "type": "plot", "type_slug": "plots", "name": "Plots", "count": 4}]

    from app.routers.sitemap import get_hubs_sitemap_urls
    locs = [u["loc"] for u in get_hubs_sitemap_urls(db_session)]
    assert "https://tradecall.in/properties/palwal/plots" in locs
    assert "https://tradecall.in/properties/palwal/flats" not in locs

    # City hub, home page and listing pages link to the type hub
    assert 'href="/properties/palwal/plots">Plots in Palwal</a> (4)' in client.get("/properties/palwal").text
    assert 'href="/properties/palwal/plots">Plots in Palwal</a> (4)' in client.get("/").text
    plot = db_session.query(Listing).filter(Listing.title.like("Plot for Sale%")).first()
    listing_html = client.get(f"/listing/{plot.id}", follow_redirects=True).text
    assert 'href="/properties/palwal/plots">Plots in Palwal</a>' in listing_html
    assert "<h1>100 Sq.Yd Plot for Sale in Omaxe City, Palwal</h1>" in listing_html


def test_type_hub_data_api_matches_the_page(client: TestClient, db_session: Session):
    _seed(db_session)
    data = client.get("/api/v1/listings/type-hubs/palwal/plots").json()["data"]
    assert data["heading"] == "Plots in Palwal" and data["total"] == 4 and data["indexable"] is True
    assert data["path"] == "/properties/palwal/plots"
    assert "_listings" not in data
    # The app shows the same intro and FAQs the server renders
    page = client.get("/properties/palwal/plots").text
    assert data["intro"] in page
    assert all(f["question"] in page for f in data["faqs"])
    assert {"name": "Omaxe City", "count": 3, "path": "/palwal/omaxe-city"} in data["localities"]
    assert client.get("/api/v1/listings/type-hubs/palwal/castles").status_code == 404
