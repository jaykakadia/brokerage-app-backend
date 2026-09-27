def test_user_profile_and_password(client, test_user):
    # Log in as test user
    client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "password123"
    })

    # Read profile
    res = client.get("/api/v1/users/profile")
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "John Doe"

    # Update profile
    upd = client.put("/api/v1/users/profile", json={
        "name": "John Updated",
        "phone": "9998881112"
    })
    assert upd.status_code == 200
    assert "Profile updated" in upd.json()["message"]

    # Verify updated profile
    res2 = client.get("/api/v1/users/profile")
    assert res2.json()["data"]["name"] == "John Updated"

    # Change password
    pwd_res = client.post("/api/v1/users/change-password", json={
        "current_password": "password123",
        "new_password": "newsecurepass999",
        "confirm_password": "newsecurepass999"
    })
    assert pwd_res.status_code == 200

    # Log in with new password
    login_new = client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "newsecurepass999"
    })
    assert login_new.status_code == 200


def test_admin_user_management(client, admin_user, test_user):
    # Log in as admin
    client.post("/api/v1/auth/login", json={
        "email": admin_user.email,
        "password": "adminpass123"
    })

    # List all users
    list_res = client.get("/api/v1/admin/users")
    assert list_res.status_code == 200
    users = list_res.json()["data"]
    assert len(users) >= 2

    # Update test user role to Builder
    role_res = client.post(f"/api/v1/admin/users/{test_user.id}/role", json={"role": "Builder"})
    assert role_res.status_code == 200

    # Update test user role to Agent
    role_res2 = client.post(f"/api/v1/admin/users/{test_user.id}/role", json={"role": "Agent"})
    assert role_res2.status_code == 200

    # Reject invalid role (e.g. Broker or Superuser)
    invalid_role = client.post(f"/api/v1/admin/users/{test_user.id}/role", json={"role": "Broker"})
    assert invalid_role.status_code == 422  # Pydantic Literal validation

    # Non-admin access forbidden
    client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "password123"
    })
    forbidden = client.get("/api/v1/admin/users")
    assert forbidden.status_code == 403
