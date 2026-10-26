import asyncio
import re
from httpx import ASGITransport, AsyncClient
from app.main import app

async def test():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        # Test 404
        resp = await client.get('/nonexistent-page-xyz')
        title = re.search(r'<title>(.*?)</title>', resp.text)
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', resp.text)
        robots = re.search(r'<meta name="robots" content="([^"]+)"', resp.text)
        h1_count = len(re.findall(r'<h1>', resp.text))
        print(f'404 Page:')
        print(f'  Status: {resp.status_code}')
        print(f'  Title: {title.group(1) if title else "MISSING"}')
        print(f'  Canonical: {canonical.group(1) if canonical else "MISSING (correct for 404)"}')
        print(f'  Robots: {robots.group(1) if robots else "MISSING"}')
        print(f'  H1: {h1_count}')
        print()
        
        # Test sitemap
        resp = await client.get('/sitemap.xml')
        print(f'Sitemap index:')
        print(f'  Status: {resp.status_code}')
        print(f'  Content-Type: {resp.headers.get("content-type")}')
        print(f'  Has sitemap-pages: {"sitemap-pages" in resp.text}')
        print(f'  Has sitemap-hubs: {"sitemap-hubs" in resp.text}')
        print(f'  Has sitemap-listings: {"sitemap-listings" in resp.text}')
        print(f'  Has sitemap-blog: {"sitemap-blog" in resp.text}')
        print()
        
        # Test sitemap-pages
        resp = await client.get('/sitemap-pages.xml')
        print(f'Sitemap pages:')
        print(f'  Status: {resp.status_code}')
        urls = re.findall(r'<loc>(.*?)</loc>', resp.text)
        print(f'  URL count: {len(urls)}')
        for u in urls[:5]:
            print(f'    {u}')

asyncio.run(test())