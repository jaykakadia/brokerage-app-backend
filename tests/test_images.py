import io
import os
import pytest
from PIL import Image
from app.services.storage_service import storage_service, MAX_IMAGE_SIDE


def _jpeg_bytes(width=64, height=48):
    """A real, decodable JPEG (uploads are re-encoded, so fake header-only bytes are rejected)."""
    out = io.BytesIO()
    Image.new("RGB", (width, height), (12, 98, 83)).save(out, "JPEG")
    return out.getvalue()


def test_listing_image_upload_and_validation(client, test_user):
    # Log in
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})

    jpeg_bytes = _jpeg_bytes()

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
    jpeg_bytes = _jpeg_bytes()

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
    jpeg_bytes = _jpeg_bytes()

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


def test_uploaded_photos_are_resized_and_compressed(client, test_user):
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})

    # A noisy 4000x3000 photo compresses poorly as-is, like a real camera picture
    big = Image.effect_noise((4000, 3000), 12).convert("RGB")
    raw = io.BytesIO()
    big.save(raw, "JPEG", quality=90)  # ~4.5 MB, just under the 5 MB upload limit
    original = raw.getvalue()

    res = client.post(
        "/api/v1/listings",
        data={"title": "Big photo", "location": "Palwal", "price": 100, "owner_name": "John", "owner_role": "Owner"},
        files=[("photos", ("camera.jpg", io.BytesIO(original), "image/jpeg"))]
    )
    assert res.status_code == 200, res.text
    image = res.json()["data"]["images"][0]
    assert image["file_path"].endswith(".webp")
    assert image["mime_type"] == "image/webp"
    assert image["file_size"] < len(original) * 0.4

    saved_path = os.path.join(storage_service.base_dir, image["file_path"].replace("/uploads/", "", 1))
    with Image.open(saved_path) as saved:
        assert max(saved.size) == MAX_IMAGE_SIDE
        assert saved.size == (MAX_IMAGE_SIDE, 1200)  # aspect ratio kept

    # A file with a JPEG header but broken contents is rejected
    broken = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 200
    res_broken = client.post(
        "/api/v1/listings",
        data={"title": "Broken photo", "location": "Palwal", "price": 100, "owner_name": "John", "owner_role": "Owner"},
        files=[("photos", ("broken.jpg", io.BytesIO(broken), "image/jpeg"))]
    )
    assert res_broken.status_code == 400
    assert "Invalid or corrupted image" in res_broken.json()["detail"]
