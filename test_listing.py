import asyncio
import re
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.db.session import SessionLocal
from app.db.models.listing import Listing

async def test():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        # First, create a test listing in DB
        db = SessionLocal()
        try:
            test_listing = Listing(
                user_id=1,
                title="Test 2BHK Flat in Palwal",
                location="Sector 2, Palwal, Haryana",
                price=3500000,
                description="Beautiful 2BHK flat in Omaxe City",
                owner_name="Test Owner",
                owner_role="Owner",
                status="approved",
                verified=1,
                is_featured=False,
                form_data={"propType": "flat", "bhk": "2BHK", "city": "Palwal", "locality": "Sector 2"}
            )
            db.add(test_listing)
            db.commit()
            db.refresh(test_listing)
            listing_id = test_listing.id
            print(f"Created test listing ID: {listing_id}")
        finally:
            db.close()
        
        # Test listing page by ID
        resp = await client.get(f'/listing/{listing_id}')
        print(f'Listing by ID (/listing/{listing_id}):')
        print(f'  Status: {resp.status_code}')
        title = re.search(r'<title>(.*?)</title>', resp.text)
        print(f'  Title: {title.group(1) if title else "MISSING"}')
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', resp.text)
        print(f'  Canonical: {canonical.group(1) if canonical else "MISSING"}')
        robots = re.search(r'<meta name="robots" content="([^"]+)"', resp.text)
        print(f'  Robots: {robots.group(1) if robots else "MISSING"}')
        h1_count = len(re.findall(r'<h1>', resp.text))
        print(f'  H1: {h1_count}')
        has_schema = 'application/ld+json' in resp.text
        print(f'  Schema: {has_schema}')
        og_image = re.search(r'<meta property="og:image" content="([^"]+)"', resp.text)
        print(f'  OG Image: {og_image.group(1) if og_image else "MISSING"}')
        breadcrumbs = re.search(r'BreadcrumbList', resp.text)
        print(f'  Breadcrumbs schema: {"YES" if breadcrumbs else "NO"}')
        print()
        
        # Test listing page by slug (canonical path)
        canonical_path = f'/palwal/test-2bhk-flat-in-palwal/TC011P-{listing_id}'
        resp = await client.get(canonical_path)
        print(f'Listing by slug ({canonical_path}):')
        print(f'  Status: {resp.status_code}')
        title = re.search(r'<title>(.*?)</title>', resp.text)
        print(f'  Title: {title.group(1) if title else "MISSING"}')
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', resp.text)
        print(f'  Canonical: {canonical.group(1) if canonical else "MISSING"}')
        print()
        
        # Test non-existent listing
        resp = await client.get('/listing/999999')
        print(f'Non-existent listing (/listing/999999):')
        print(f'  Status: {resp.status_code}')
        title = re.search(r'<title>(.*?)</title>', resp.text)
        print(f'  Title: {title.group(1) if title else "MISSING"}')
        robots = re.search(r'<meta name="robots" content="([^"]+)"', resp.text)
        print(f'  Robots: {robots.group(1) if robots else "MISSING"}')

asyncio.run(test())