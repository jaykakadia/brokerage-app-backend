import asyncio
import re
from httpx import ASGITransport, AsyncClient
from app.main import app

async def test():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        resp = await client.get('/')
        print(f'Status: {resp.status_code}')
        title = re.search(r'<title>(.*?)</title>', resp.text)
        print(f'Title: {title.group(1) if title else "MISSING"}')
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', resp.text)
        print(f'Canonical: {canonical.group(1) if canonical else "MISSING"}')
        desc = re.search(r'<meta name="description" content="([^"]+)"', resp.text)
        print(f'Description: {desc.group(1)[:80] if desc else "MISSING"}...')
        robots = re.search(r'<meta name="robots" content="([^"]+)"', resp.text)
        print(f'Robots: {robots.group(1) if robots else "MISSING"}')
        h1_count = len(re.findall(r'<h1>', resp.text))
        print(f'H1 count: {h1_count}')
        has_hubs = 'Indexable City Real Estate Hubs' in resp.text
        print(f'Has city hubs section: {has_hubs}')
        has_faq = 'Frequently Asked Questions' in resp.text
        print(f'Has FAQ section: {has_faq}')
        has_schema = 'application/ld+json' in resp.text
        print(f'Has JSON-LD schema: {has_schema}')

asyncio.run(test())