def test_signup_guide_links(client, admin_user, test_user):
    # Public read works without login and defaults to empty links
    res = client.get("/api/v1/settings/signup-guide")
    assert res.status_code == 200
    assert res.json()["data"] == {"blog_url": "", "video_url": ""}

    # Non-admin cannot change the links
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    res = client.post("/api/v1/admin/settings/signup-guide", json={"blog_url": "https://a.com", "video_url": ""})
    assert res.status_code == 403

    # Admin saves links
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    payload = {"blog_url": "https://tradecall.in/blog/how-to-register", "video_url": "https://youtu.be/abc123"}
    res = client.post("/api/v1/admin/settings/signup-guide", json=payload)
    assert res.status_code == 200
    assert res.json()["data"] == payload

    # Non-http links are rejected
    res = client.post("/api/v1/admin/settings/signup-guide", json={"blog_url": "javascript:alert(1)", "video_url": ""})
    assert res.status_code == 400

    # Public read returns the saved links
    client.cookies.clear()
    res = client.get("/api/v1/settings/signup-guide")
    assert res.json()["data"] == payload
