import asyncio
from httpx import ASGITransport, AsyncClient
from app.main import app

async def test():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        resp = await client.get('/')
        print(f'Status: {resp.status_code}')
        print(f'Title: {"FOUND" if "<title>" in resp.text else "MISSING"}')
        print(f'Canonical: {"FOUND" if "canonical" in resp.text else "MISSING"}')
        print(f'Length: {len(resp.text)}')
        if resp.status_code != 200:
            print(resp.text[:2000])

asyncio.run(test())