import pytest


def test_blogs_system_and_lifecycle(client, admin_user, test_user):
    # 1. Non-admin blocked from admin blog endpoints
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    res_unauth = client.post("/api/v1/blogs/admin", json={
        "title": "Unauthorized Blog",
        "content": "Should fail"
    })
    assert res_unauth.status_code == 403

    # 2. Admin login & create published blog
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    res_b1 = client.post("/api/v1/blogs/admin", json={
        "title": "Property Prices in Palwal 2025: Complete Guide",
        "category": "market",
        "content": "Comprehensive guide to real estate in Haryana NCR.",
        "permalink": "property-prices-palwal-2025",
        "tags": "palwal, real estate, investment",
        "status": "published",
        "author": "TradeCall Research Team"
    })
    assert res_b1.status_code == 200
    blog1 = res_b1.json()["data"]
    assert blog1["permalink"] == "property-prices-palwal-2025"
    blog1_id = blog1["id"]

    # 3. Admin create draft blog
    res_b2 = client.post("/api/v1/blogs/admin", json={
        "title": "Secret Upcoming Projects in Gurugram",
        "category": "investment",
        "content": "Internal draft not ready for public viewing.",
        "status": "draft"
    })
    assert res_b2.status_code == 200
    blog2 = res_b2.json()["data"]
    blog2_id = blog2["id"]

    # 4. Public blog list: ONLY published blogs must be visible
    client.post("/api/v1/auth/logout")
    res_pub = client.get("/api/v1/blogs")
    assert res_pub.status_code == 200
    pub_ids = [b["id"] for b in res_pub.json()["data"]]
    assert blog1_id in pub_ids
    assert blog2_id not in pub_ids  # Draft must not leak to public

    # 5. Public lookup by slug and by id
    res_slug = client.get("/api/v1/blogs/detail/property-prices-palwal-2025")
    assert res_slug.status_code == 200
    assert res_slug.json()["data"]["id"] == blog1_id

    res_id = client.get(f"/api/v1/blogs/detail/{blog1_id}")
    assert res_id.status_code == 200
    assert res_id.json()["data"]["permalink"] == "property-prices-palwal-2025"

    # Category filter
    res_cat = client.get("/api/v1/blogs?category=market")
    assert res_cat.status_code == 200
    assert len(res_cat.json()["data"]) >= 1

    # 6. Admin edit blog (publish draft)
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    res_edit = client.post(f"/api/v1/blogs/admin?blog_id={blog2_id}", json={
        "title": "Secret Upcoming Projects in Gurugram (Now Published)",
        "category": "investment",
        "content": "Now ready for buyers.",
        "status": "published"
    })
    assert res_edit.status_code == 200
    assert res_edit.json()["data"]["status"] == "published"

    # 7. Admin delete blog
    res_del = client.delete(f"/api/v1/blogs/admin/{blog2_id}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "success"
