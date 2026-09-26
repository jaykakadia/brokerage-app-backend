import os
import uuid
import shutil
from typing import Tuple, List, Optional
from fastapi import UploadFile, HTTPException, status
from app.core.config import settings

ALLOWED_MIME_TYPES = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp"
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class StorageService:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or settings.UPLOAD_DIR
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(os.path.join(self.base_dir, "listings"), exist_ok=True)

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

    async def validate_and_save_listing_image(
        self,
        listing_id: int,
        file: UploadFile
    ) -> Tuple[str, str, int, str]:
        """
        Validates an uploaded image and saves it to local disk under listing directory.
        Returns: (file_path_relative, original_filename, file_size, mime_type)
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

        # Ensure safe listing directory
        listing_dir = os.path.join(self.base_dir, "listings", str(listing_id))
        os.makedirs(listing_dir, exist_ok=True)

        # Generate secure UUID filename
        unique_filename = f"{uuid.uuid4().hex}.{detected_ext}"
        destination_path = os.path.join(listing_dir, unique_filename)

        # Prevent path traversal
        real_dest = os.path.realpath(destination_path)
        real_base = os.path.realpath(self.base_dir)
        if not real_dest.startswith(real_base):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path traversal detected."
            )

        with open(destination_path, "wb") as f:
            f.write(content)

        relative_path = f"/uploads/listings/{listing_id}/{unique_filename}"
        mime_type = file.content_type or f"image/{detected_ext}"
        return relative_path, filename, file_size, mime_type

    def delete_file(self, relative_path: str) -> bool:
        """Deletes a single physical file safely."""
        if not relative_path.startswith("/uploads/"):
            return False
        clean_rel = relative_path.replace("/uploads/", "", 1)
        full_path = os.path.join(self.base_dir, clean_rel)
        real_path = os.path.realpath(full_path)
        real_base = os.path.realpath(self.base_dir)
        if not real_path.startswith(real_base):
            return False
        if os.path.exists(real_path) and os.path.isfile(real_path):
            try:
                os.remove(real_path)
                return True
            except OSError:
                return False
        return False

    def delete_listing_folder(self, listing_id: int) -> bool:
        """Deletes the entire folder for a listing upon cascade delete."""
        listing_dir = os.path.join(self.base_dir, "listings", str(listing_id))
        real_path = os.path.realpath(listing_dir)
        real_base = os.path.realpath(self.base_dir)
        if not real_path.startswith(real_base):
            return False
        if os.path.exists(real_path) and os.path.isdir(real_path):
            try:
                shutil.rmtree(real_path)
                return True
            except OSError:
                return False
        return False


storage_service = StorageService()
