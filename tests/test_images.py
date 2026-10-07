import io
import pytest


def test_listing_image_upload_and_validation(client, test_user):
    # Log in
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})

    # Create dummy JPEG image with valid JPEG header (FF D8 FF E0 ...)
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00" + (b"\x00" * 100)

    # 1. Valid Image Upload with Listing
    res = client.post(
        "/api/v1/listings",
        data={
            "title": "Listing with Image",
            "location": "Gurugram",
            "price": 8500000,
            "owner_name": "John Doe",
            "owner_role": "Owner"
        },
        files=[
            ("photos", ("photo1.jpg", io.BytesIO(jpeg_bytes), "image/jpeg"))
        ]
    )
    assert res.status_code == 200
    listing = res.json()["data"]
    assert len(listing["images"]) == 1
    assert listing["images"][0]["file_path"].startswith("/uploads/listings/")

    # 2. Invalid File Signature / Extension Upload
    fake_exe = b"MZ\x90\x00\x03\x00\x00\x00"  # Executable signature
    res_bad = client.post(
        "/api/v1/listings",
        data={
            "title": "Listing with Malicious File",
            "location": "Gurugram",
            "price": 8500000,
            "owner_name": "John Doe",
            "owner_role": "Owner"
        },
        files=[
            ("photos", ("malicious.exe", io.BytesIO(fake_exe), "application/x-dosexec"))
        ]
    )
    assert res_bad.status_code == 400
    assert "Unsupported file extension" in res_bad.json()["detail"]

    # 3. Mismatched MIME / Spoofed extension
    fake_png = b"This is not a png"
    res_spoof = client.post(
        "/api/v1/listings",
        data={
            "title": "Listing with Spoofed PNG",
            "location": "Gurugram",
            "price": 8500000,
            "owner_name": "John Doe",
            "owner_role": "Owner"
        },
        files=[
            ("photos", ("fake.png", io.BytesIO(fake_png), "image/png"))
        ]
    )
    assert res_spoof.status_code == 400
    assert "Invalid image format" in res_spoof.json()["detail"]

    # 4. Oversized File (> 5 MB)
    oversized_data = jpeg_bytes + (b"\x00" * (5 * 1024 * 1024 + 100))
    res_oversized = client.post(
        "/api/v1/listings",
        data={
            "title": "Listing with Oversized Image",
            "location": "Gurugram",
            "price": 8500000,
            "owner_name": "John Doe",
            "owner_role": "Owner"
        },
        files=[
            ("photos", ("huge.jpg", io.BytesIO(oversized_data), "image/jpeg"))
        ]
    )
    assert res_oversized.status_code == 400
    assert "exceeds maximum allowed size" in res_oversized.json()["detail"]


def test_path_traversal_and_max_photos(client, test_user):
    # Log in
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00" + (b"\x00" * 100)

    # 1. Path traversal attempt in filename
    res_traversal = client.post(
        "/api/v1/listings",
        data={
            "title": "Listing with Traversal Attempt",
            "location": "Gurugram",
            "price": 8500000,
            "owner_name": "John Doe",
            "owner_role": "Owner"
        },
        files=[
            ("photos", ("../../../../etc/passwd.jpg", io.BytesIO(jpeg_bytes), "image/jpeg"))
        ]
    )
    assert res_traversal.status_code == 200
    listing = res_traversal.json()["data"]
    # Verify that file_path never contains .. and is safely contained in UUID
    saved_path = listing["images"][0]["file_path"]
    assert ".." not in saved_path
    assert "/etc/" not in saved_path
    assert saved_path.startswith("/uploads/listings/")

    # 2. Maximum photos limit (capped at 10)
    many_files = [("photos", (f"img_{i}.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")) for i in range(12)]
    res_many = client.post(
        "/api/v1/listings",
        data={
            "title": "Listing with Many Images",
            "location": "Gurugram",
            "price": 8500000,
            "owner_name": "John Doe",
            "owner_role": "Owner"
        },
        files=many_files
    )
    assert res_many.status_code == 200
    listing_many = res_many.json()["data"]
    assert len(listing_many["images"]) <= 10



def test_edit_listing_removes_and_adds_photos(client, test_user):
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00" + (b"\x00" * 100)

    def photo(name):
        return ("photos", (name, io.BytesIO(jpeg_bytes), "image/jpeg"))

    listing = client.post(
        "/api/v1/listings",
        data={"title": "Two photos", "location": "Palwal", "price": 100, "owner_name": "John", "owner_role": "Owner"},
        files=[photo("a.jpg"), photo("b.jpg")]
    ).json()["data"]
    first, second = listing["images"]

    res = client.patch(
        f"/api/v1/listings/{listing['id']}",
        data={"remove_image_ids": str(first["id"])},
        files=[photo("c.jpg")]
    )
    assert res.status_code == 200
    images = res.json()["data"]["images"]
    assert [img["id"] for img in images][0] == second["id"]
    assert len(images) == 2
    assert first["id"] not in [img["id"] for img in images]
    # New photos go after the ones that are kept
    assert images[1]["sort_order"] > second["sort_order"]
