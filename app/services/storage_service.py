import io
import os
import uuid
import shutil
from typing import Tuple, List, Optional, Iterator
from fastapi import UploadFile, HTTPException, status
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool
from app.core.config import settings

# Uploaded photos are re-encoded to keep storage small without visible quality loss:
# longest side capped at MAX_IMAGE_SIDE px and saved as WebP at WEBP_QUALITY.
MAX_IMAGE_SIDE = 1600
WEBP_QUALITY = 80
# Reject "decompression bomb" images (tiny file, enormous pixel count)
Image.MAX_IMAGE_PIXELS = 50_000_000

ALLOWED_MIME_TYPES = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp"
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# File names are random UUIDs and never overwritten, so browsers/CDNs may cache them forever.
CACHE_CONTROL = "public, max-age=31536000, immutable"


# ---------------------------------------------------------------------------
# Storage keys
#
# The database stores only a storage key such as "listings/10/<uuid>.webp" — never a host
# or URL — so moving files between backends (local disk, R2, S3, ...) needs no data change.
# Rows written before keys existed hold "/uploads/listings/..."; to_key() accepts both.
# ---------------------------------------------------------------------------

def to_key(path: str) -> str:
    """Normalizes a stored path, legacy "/uploads/..." path or public URL to a storage key."""
    if not path:
        return ""
    base = settings.MEDIA_BASE_URL.rstrip("/")
    if base and path.startswith(base + "/"):
        path = path[len(base) + 1:]
    elif path.startswith("/uploads/"):
        path = path[len("/uploads/"):]
    return path.lstrip("/")


def public_url(path: str) -> str:
    """Public URL for a stored path, built from MEDIA_BASE_URL (e.g. "/uploads" or an R2/CDN domain)."""
    if not path or path.startswith(("http://", "https://")):
        return path
    return f"{settings.MEDIA_BASE_URL.rstrip('/')}/{to_key(path)}"


def _is_safe_key(key: str) -> bool:
    return bool(key) and not key.startswith("/") and ".." not in key.split("/")


# ---------------------------------------------------------------------------
# Backends — each one stores bytes under a key. Pick one with STORAGE_BACKEND.
# ---------------------------------------------------------------------------

class LocalBackend:
    """Files on this server's disk under UPLOAD_DIR, served by the app at /uploads (VPS / local dev)."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(os.path.join(self.base_dir, "listings"), exist_ok=True)

    def _full_path(self, key: str) -> Optional[str]:
        if not _is_safe_key(key):
            return None
        real_path = os.path.realpath(os.path.join(self.base_dir, key))
        real_base = os.path.realpath(self.base_dir)
        if not real_path.startswith(real_base + os.sep):
            return None
        return real_path

    def save(self, key: str, data: bytes, content_type: str) -> None:
        full_path = self._full_path(key)
        if not full_path:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path traversal detected.")
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(data)

    def read(self, key: str) -> bytes:
        full_path = self._full_path(key)
        if not full_path:
            raise FileNotFoundError(key)
        with open(full_path, "rb") as f:
            return f.read()

    def delete(self, key: str) -> bool:
        full_path = self._full_path(key)
        if full_path and os.path.isfile(full_path):
            try:
                os.remove(full_path)
                return True
            except OSError:
                return False
        return False

    def delete_prefix(self, prefix: str) -> bool:
        full_path = self._full_path(prefix.rstrip("/"))
        if full_path and os.path.isdir(full_path):
            try:
                shutil.rmtree(full_path)
                return True
            except OSError:
                return False
        return False

    def list_keys(self, prefix: str = "") -> Iterator[str]:
        root = os.path.realpath(self.base_dir)
        for dirpath, _, filenames in os.walk(os.path.join(root, prefix)):
            for name in filenames:
                yield os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")


class S3Backend:
    """Any S3-compatible bucket: Supabase Storage, Cloudflare R2, AWS S3, Backblaze B2, MinIO, ..."""

    def __init__(self):
        import boto3  # only needed when this backend is in use
        from botocore.config import Config

        missing = [name for name in ("S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
                   if not getattr(settings, name)]
        if missing:
            raise RuntimeError(f"STORAGE_BACKEND=s3 needs these settings: {', '.join(missing)}")
        self.bucket = settings.S3_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            region_name=settings.S3_REGION,
            # Path-style URLs: required by Supabase Storage, also accepted by R2, MinIO and AWS
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )

    def save(self, key: str, data: bytes, content_type: str) -> None:
        if not _is_safe_key(key):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path traversal detected.")
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, CacheControl=CACHE_CONTROL
        )

    def read(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> bool:
        if not _is_safe_key(key):
            return False
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete_prefix(self, prefix: str) -> bool:
        if not _is_safe_key(prefix):
            return False
        try:
            keys = list(self.list_keys(prefix))
            for start in range(0, len(keys), 1000):
                batch = [{"Key": k} for k in keys[start:start + 1000]]
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": batch, "Quiet": True})
            return True
        except Exception:
            return False

    def list_keys(self, prefix: str = "") -> Iterator[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                yield obj["Key"]


def create_backend(kind: Optional[str] = None, base_dir: Optional[str] = None):
    kind = (kind or settings.STORAGE_BACKEND).lower()
    if kind == "local":
        return LocalBackend(base_dir or settings.UPLOAD_DIR)
    if kind == "s3":
        return S3Backend()
    raise RuntimeError(f"Unknown STORAGE_BACKEND '{kind}'. Use 'local' or 's3'.")


class StorageService:
    def __init__(self, base_dir: Optional[str] = None, backend=None):
        self.base_dir = base_dir or settings.UPLOAD_DIR
        self.backend = backend or create_backend(base_dir=self.base_dir)

    def _validate_image_bytes(self, header: bytes) -> Optional[str]:
        """Validate image magic bytes to ensure file is legitimate image."""
        if len(header) < 12:
            return None
        # JPEG: FF D8 FF
        if header.startswith(b"\xff\xd8\xff"):
            return "jpg"
        # PNG: 89 50 4E 47 0D 0A 1A 0A
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        # WEBP: RIFF .... WEBP
        if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
            return "webp"
        return None

    def _optimize_image(self, content: bytes, detected_ext: str) -> Tuple[bytes, str]:
        """Re-encodes a photo as a resized WebP. Keeps the original if that is already smaller."""
        try:
            with Image.open(io.BytesIO(content)) as img:
                img = ImageOps.exif_transpose(img)  # apply phone camera rotation before EXIF is dropped
                img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
                img = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")
                out = io.BytesIO()
                img.save(out, "WEBP", quality=WEBP_QUALITY, method=4)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or corrupted image file."
            )
        optimized = out.getvalue()
        if len(optimized) >= len(content):
            return content, detected_ext
        return optimized, "webp"

    async def validate_and_save_listing_image(
        self,
        listing_id: int,
        file: UploadFile
    ) -> Tuple[str, str, int, str]:
        """
        Validates an uploaded image and saves it to the configured storage backend.
        Returns: (storage_key, original_filename, file_size, mime_type)
        """
        # Validate extension
        filename = file.filename or "unknown"
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file extension '{ext}'. Allowed extensions: {list(ALLOWED_EXTENSIONS)}"
            )

        # Read content and validate size
        content = await file.read()
        file_size = len(content)
        if file_size > settings.MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_BYTES // (1024*1024)}MB."
            )
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty file upload is not allowed."
            )

        # Validate magic bytes
        detected_ext = self._validate_image_bytes(content[:16])
        if not detected_ext:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid image format. Content does not match JPEG, PNG, or WEBP signatures."
            )

        content, detected_ext = await run_in_threadpool(self._optimize_image, content, detected_ext)

        # Generate secure UUID filename
        key = f"listings/{int(listing_id)}/{uuid.uuid4().hex}.{detected_ext}"
        mime_type = "image/jpeg" if detected_ext == "jpg" else f"image/{detected_ext}"
        await run_in_threadpool(self.backend.save, key, content, mime_type)
        return key, filename, len(content), mime_type

    def delete_file(self, path: str) -> bool:
        """Deletes a single stored file. Accepts a storage key or a legacy "/uploads/..." path."""
        return self.backend.delete(to_key(path))

    def delete_listing_folder(self, listing_id: int) -> bool:
        """Deletes every file of a listing upon cascade delete."""
        return self.backend.delete_prefix(f"listings/{int(listing_id)}/")


storage_service = StorageService()
