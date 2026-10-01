def _login(client, user, password):
    client.post("/api/v1/auth/login", json={"email": user.email, "password": password})


def test_contact_form_creates_enquiry_and_admin_manages_it(client, admin_user):
    res = client.post("/api/v1/enquiries", json={
        "name": "Ravi Kumar",
        "email": "Ravi@Example.com",
        "phone": "+91 98765-43210",
        "message": "Looking for a 2BHK in Palwal."
    })
    assert res.status_code == 200, res.text

    # Bots that fill the hidden honeypot get a success reply but nothing is stored
    bot = client.post("/api/v1/enquiries", json={
        "name": "Spam", "email": "spam@example.com", "phone": "9999999999",
        "message": "buy now", "website": "http://spam.example"
    })
    assert bot.status_code == 200

    # Validation
    assert client.post("/api/v1/enquiries", json={
        "name": "X", "email": "not-an-email", "phone": "9876543210", "message": "hi"
    }).status_code == 422

    # Admin endpoints are protected
    assert client.get("/api/v1/admin/enquiries").status_code == 401

    _login(client, admin_user, "adminpass123")
    rows = client.get("/api/v1/admin/enquiries").json()["data"]
    assert len(rows) == 1
    enquiry = rows[0]
    assert enquiry["email"] == "ravi@example.com"
    assert enquiry["phone"] == "9876543210"
    assert enquiry["status"] == "new"

    counts = client.get("/api/v1/admin/enquiries/counts").json()["data"]
    assert counts == {"new": 1, "in_progress": 0, "resolved": 0, "all": 1}

    upd = client.patch(f"/api/v1/admin/enquiries/{enquiry['id']}", json={
        "status": "resolved", "admin_note": "Called back, shared 3 listings."
    })
    assert upd.status_code == 200
    assert upd.json()["data"]["status"] == "resolved"
    assert upd.json()["data"]["admin_note"] == "Called back, shared 3 listings."

    assert client.patch(f"/api/v1/admin/enquiries/{enquiry['id']}", json={"status": "bogus"}).status_code == 422
    assert len(client.get("/api/v1/admin/enquiries?status=new").json()["data"]) == 0
    assert len(client.get("/api/v1/admin/enquiries?search=2BHK").json()["data"]) == 1

    assert client.delete(f"/api/v1/admin/enquiries/{enquiry['id']}").status_code == 200
    assert client.get("/api/v1/admin/enquiries").json()["data"] == []


def test_non_admin_cannot_read_enquiries(client, test_user):
    _login(client, test_user, "password123")
    assert client.get("/api/v1/admin/enquiries").status_code == 403
