def test_categories_flow(client, admin_user, test_user):
    # 1. Public categories endpoint (seeds defaults if empty)
    cats_res = client.get("/api/v1/categories")
    assert cats_res.status_code == 200
    assert len(cats_res.json()["data"]) >= 1

    # 2. Non-admin forbidden
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    forbidden_res = client.post("/api/v1/categories", json={
        "name": "Warehouse & Logistics",
        "description": "Industrial spaces"
    })
    assert forbidden_res.status_code == 403

    # 3. Admin create category
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    create_res = client.post("/api/v1/categories", json={
        "name": "Warehouse & Logistics",
        "description": "Industrial spaces"
    })
    assert create_res.status_code == 200
    cat_id = create_res.json()["data"]["id"]

    # 4. Detail view
    detail_res = client.get(f"/api/v1/categories/{cat_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["data"]["name"] == "Warehouse & Logistics"

    # 5. Delete category
    del_res = client.delete(f"/api/v1/categories/{cat_id}")
    assert del_res.status_code == 200
