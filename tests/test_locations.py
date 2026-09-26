def test_locations_flow(client, admin_user, test_user):
    # 1. Public cities endpoint
    cities_res = client.get("/api/v1/locations/cities")
    assert cities_res.status_code == 200
    assert len(cities_res.json()["data"]) >= 1

    # 2. Non-admin cannot create location
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    forbidden_res = client.post("/api/v1/locations", json={
        "city_name": "Rewari",
        "state": "Haryana"
    })
    assert forbidden_res.status_code == 403

    # 3. Admin can create location
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    create_res = client.post("/api/v1/locations", json={
        "city_name": "Rewari",
        "state": "Haryana",
        "category": "NCR Tier 2",
        "latitude": 28.18,
        "longitude": 76.61
    })
    assert create_res.status_code == 200
    loc_id = create_res.json()["data"]["id"]

    # 4. Verify in list
    list_res = client.get("/api/v1/locations")
    assert any(l["city_name"] == "Rewari" for l in list_res.json()["data"])

    # 5. Delete location
    del_res = client.delete(f"/api/v1/locations/{loc_id}")
    assert del_res.status_code == 200
