import asyncio
import re
from httpx import ASGITransport, AsyncClient
from app.main import app

async def test_route(path, description):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        resp = await client.get(path)
        title = re.search(r'<title>(.*?)</title>', resp.text)
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', resp.text)
        robots = re.search(r'<meta name="robots" content="([^"]+)"', resp.text)
        h1_count = len(re.findall(r'<h1>', resp.text))
        has_schema = 'application/ld+json' in resp.text
        print(f'{description} ({path}):')
        print(f'  Status: {resp.status_code}, Title: {title.group(1)[:60] if title else "MISSING"}')
        print(f'  Canonical: {canonical.group(1) if canonical else "MISSING"}')
        print(f'  Robots: {robots.group(1) if robots else "MISSING"}')
        print(f'  H1: {h1_count}, Schema: {has_schema}')
        print()

async def test():
    routes = [
        ('/', 'Homepage'),
        ('/about', 'About'),
        ('/contact', 'Contact'),
        ('/cities', 'Cities'),
        ('/business-directory', 'Business Directory'),
        ('/blog', 'Blog Index'),
        ('/privacy', 'Privacy'),
        ('/terms-of-use', 'Terms'),
        ('/advertise', 'Advertise'),
        ('/post-listing', 'Post Listing'),
        ('/properties/palwal', 'Palwal City Page'),
        ('/properties/mumbai', 'Mumbai City Page (should 404 or noindex)'),
        ('/hi/properties/palwal', 'Hindi Palwal Page'),
        ('/nonexistent-page-xyz', '404 Page'),
    ]
    for path, desc in routes:
        await test_route(path, desc)

asyncio.run(test())