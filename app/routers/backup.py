import io
import json
import mimetypes
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select, text, DateTime, Date
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.core.config import settings
from app.core.dependencies import get_current_admin, get_db
from app.db.base import Base
from app.db.models.user import User
from app.db.models.audit_log import AuditLog
from app.schemas.common import APIResponse
from app.services.storage_service import create_backend

router = APIRouter(prefix="/api/v1/admin/backup", tags=["Admin Backup"])

MAX_BACKUP_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB


def _json_serial(obj: Any) -> Any:
    """Helper for json.dumps to handle datetimes, decimals, and bytes."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"Type {type(obj)} is not JSON serializable")


def _is_safe_archive_path(path: str) -> bool:
    """Check that a zip entry does not escape destination directory (zip slip protection)."""
    if not path or path.startswith("/") or path.startswith("\\"):
        return False
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    if ".." in parts or any(p.strip() == "" for p in parts[:-1]):
        return False
    return True


def _get_uploads_stats() -> Dict[str, Any]:
    """Returns file count and total bytes under upload dir."""
    count = 0
    total_bytes = 0
    if os.path.exists(settings.UPLOAD_DIR):
        for root, _, files in os.walk(settings.UPLOAD_DIR):
            for f in files:
                if f.startswith(".") or f == "Thumbs.db":
                    continue
                full = os.path.join(root, f)
                try:
                    total_bytes += os.path.getsize(full)
                    count += 1
                except OSError:
                    pass
    return {"count": count, "total_bytes": total_bytes}


def _format_bytes(bytes_count: int) -> str:
    """Format bytes into readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} TB"


def _reset_postgres_sequences(db: Session) -> None:
    """Resets all PostgreSQL sequences to MAX(id) to avoid duplicate key errors."""
    if db.bind and db.bind.dialect.name == "postgresql":
        for table in Base.metadata.sorted_tables:
            if "id" in table.columns:
                try:
                    db.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                        f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table.name};"
                    ))
                except Exception:
                    # Ignore tables that don't use serial sequences
                    pass


@router.get("/stats", response_model=APIResponse[Dict[str, Any]])
def get_backup_stats(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Returns current counts of all database tables and uploaded media assets."""
    table_counts: Dict[str, int] = {}
    total_records = 0
    for table in Base.metadata.sorted_tables:
        count = db.execute(select(table)).rowcount
        # rowcount may be -1 for some dialects on plain select
        if count is None or count < 0:
            count = len(db.execute(select(table)).mappings().all())
        table_counts[table.name] = count
        total_records += count

    uploads_stats = _get_uploads_stats()

    return APIResponse(
        status="success",
        data={
            "tables": table_counts,
            "total_tables": len(table_counts),
            "total_records": total_records,
            "images_count": uploads_stats["count"],
            "images_size_bytes": uploads_stats["total_bytes"],
            "images_size_formatted": _format_bytes(uploads_stats["total_bytes"]),
            "storage_backend": settings.STORAGE_BACKEND,
            "upload_dir": settings.UPLOAD_DIR
        }
    )


@router.get("/export")
@router.get("/download")
def export_backup_archive(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """
    Exports a full system backup archive (.zip) containing:
    1. tables/*.json - All database table records serialized to JSON
    2. uploads/* - All uploaded media files (photos, images, documents)
    3. manifest.json - Metadata and record counts
    Only accessible by administrators.
    """
    tmp_fd, tmp_zip_path = tempfile.mkstemp(suffix=".zip", prefix="tradecall_backup_")
    os.close(tmp_fd)

    try:
        with zipfile.ZipFile(tmp_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            table_counts: Dict[str, int] = {}
            # 1. Export all database tables in topological dependency order
            for table in Base.metadata.sorted_tables:
                rows = [dict(r) for r in db.execute(select(table)).mappings().all()]
                table_counts[table.name] = len(rows)
                json_bytes = json.dumps(rows, default=_json_serial, indent=2).encode("utf-8")
                zf.writestr(f"tables/{table.name}.json", json_bytes)

            # 2. Export all media uploads
            images_count = 0
            storage_backend = (settings.STORAGE_BACKEND or "local").lower()
            if storage_backend == "local":
                if os.path.exists(settings.UPLOAD_DIR):
                    for root, _, files in os.walk(settings.UPLOAD_DIR):
                        for file in files:
                            if file.startswith(".") or file == "Thumbs.db":
                                continue
                            full_path = os.path.join(root, file)
                            rel_path = os.path.relpath(full_path, settings.UPLOAD_DIR)
                            # Store with forward slash
                            arcname = f"uploads/{rel_path.replace(os.sep, '/')}"
                            zf.write(full_path, arcname=arcname)
                            images_count += 1
            else:
                try:
                    storage = create_backend()
                    for key in storage.list_keys():
                        data = storage.read(key)
                        zf.writestr(f"uploads/{key}", data)
                        images_count += 1
                except Exception as err:
                    # Non-fatal if remote storage list fails
                    pass

            # 3. Create manifest
            now_iso = datetime.now(timezone.utc).isoformat()
            manifest = {
                "app": settings.APP_NAME,
                "version": "1.0.0",
                "exported_at": now_iso,
                "exported_by": current_admin.email,
                "exported_by_id": current_admin.id,
                "table_counts": table_counts,
                "total_records": sum(table_counts.values()),
                "total_images": images_count,
                "tables_order": [t.name for t in Base.metadata.sorted_tables]
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))

        # Log audit trail
        try:
            audit = AuditLog(
                table_name="system",
                record_id=0,
                record_name="Full Data Backup Archive",
                action="EXPORT_BACKUP",
                changes={"total_records": sum(table_counts.values()), "total_images": images_count},
                actor_id=current_admin.id,
                actor_email=current_admin.email,
                actor_role=current_admin.role,
                created_at=datetime.now(timezone.utc)
            )
            db.add(audit)
            db.commit()
        except Exception:
            db.rollback()

        filename = f"tradecall_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"
        return FileResponse(
            path=tmp_zip_path,
            media_type="application/zip",
            filename=filename,
            background=BackgroundTask(lambda: os.path.exists(tmp_zip_path) and os.unlink(tmp_zip_path))
        )
    except Exception as exc:
        if os.path.exists(tmp_zip_path):
            os.unlink(tmp_zip_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate backup archive: {str(exc)}"
        )


@router.post("/restore", response_model=APIResponse[Dict[str, Any]])
@router.post("/upload", response_model=APIResponse[Dict[str, Any]])
async def restore_backup_archive(
    file: UploadFile = File(...),
    mode: str = Query("replace", pattern="^(replace|upsert)$", description="'replace' wipes and imports clean; 'upsert' merges records"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """
    Restores full database data and media images from an uploaded .zip backup archive.
    - Validates zip structure and security (path traversal protection)
    - Restores database records in dependency order
    - Automatically updates database sequences (PostgreSQL)
    - Restores uploaded images/media
    - Preserves current admin access
    - Admin protected only
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Please upload a .zip backup archive."
        )

    # Save uploaded file to temp path to avoid buffering entire file in memory
    tmp_fd, tmp_zip_path = tempfile.mkstemp(suffix=".zip", prefix="tradecall_upload_")
    bytes_written = 0
    try:
        with os.fdopen(tmp_fd, "wb") as f_out:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                bytes_written += len(chunk)
                if bytes_written > MAX_BACKUP_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Backup file exceeds maximum allowed size ({MAX_BACKUP_SIZE_BYTES // (1024*1024)} MB)."
                    )
                f_out.write(chunk)

        if not zipfile.is_zipfile(tmp_zip_path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded file is not a valid or readable ZIP archive."
            )

        with zipfile.ZipFile(tmp_zip_path, "r") as zf:
            namelist = zf.namelist()

            # Security check: Zip Slip path traversal verification
            for name in namelist:
                if not _is_safe_archive_path(name):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Security violation: Archive contains unsafe file path '{name}'."
                    )

            # Load table records from archive
            # Supports tables/<name>.json or data/<name>.json or root <name>.json
            table_files: Dict[str, str] = {}
            for name in namelist:
                if name.endswith(".json"):
                    base_name = os.path.basename(name)
                    tbl_name = base_name[:-5]
                    if any(t.name == tbl_name for t in Base.metadata.sorted_tables):
                        table_files[tbl_name] = name

            if not table_files:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Archive does not contain recognizable database table dumps."
                )

            # Disable automatic audit logging during bulk restoration
            db._audit_disabled = True  # type: ignore

            # Parse table data from zip
            table_data: Dict[str, List[Dict[str, Any]]] = {}
            for tbl_name, zip_path in table_files.items():
                try:
                    content = zf.read(zip_path).decode("utf-8")
                    data = json.loads(content)
                    if isinstance(data, list):
                        table_data[tbl_name] = data
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to parse table JSON '{zip_path}': {str(e)}"
                    )

            # Safety check: ensure current admin is in the users list so they aren't locked out
            if "users" in table_data:
                backup_emails = {u.get("email") for u in table_data["users"] if isinstance(u, dict)}
                if current_admin.email not in backup_emails:
                    admin_row = {
                        c.name: getattr(current_admin, c.name, None)
                        for c in User.__table__.columns
                    }
                    table_data["users"].append(admin_row)

            restored_counts: Dict[str, int] = {}
            total_records_restored = 0

            # 1. Database Restoration in safe transaction
            try:
                # In replace mode: wipe tables in REVERSE dependency order
                if mode == "replace":
                    for table in reversed(Base.metadata.sorted_tables):
                        if table.name in table_data:
                            db.execute(table.delete())
                    db.flush()

                # Restore tables in FORWARD dependency order
                for table in Base.metadata.sorted_tables:
                    if table.name not in table_data:
                        continue

                    raw_rows = table_data[table.name]
                    clean_rows: List[Dict[str, Any]] = []

                    for r in raw_rows:
                        if not isinstance(r, dict):
                            continue
                        row_dict: Dict[str, Any] = {}
                        for col in table.columns:
                            if col.name not in r:
                                continue
                            val = r[col.name]
                            if val is not None and isinstance(col.type, (DateTime, Date)) and isinstance(val, str):
                                try:
                                    val = datetime.fromisoformat(val)
                                except Exception:
                                    pass
                            row_dict[col.name] = val
                        clean_rows.append(row_dict)

                    if not clean_rows:
                        restored_counts[table.name] = 0
                        continue

                    if mode == "replace":
                        # Bulk insert in batches of 500
                        chunk_size = 500
                        for i in range(0, len(clean_rows), chunk_size):
                            chunk = clean_rows[i:i + chunk_size]
                            db.execute(table.insert(), chunk)
                        restored_counts[table.name] = len(clean_rows)
                        total_records_restored += len(clean_rows)
                    else:
                        # Upsert mode: update existing or insert new
                        pk_col = list(table.primary_key.columns)[0].name if table.primary_key else "id"
                        cnt = 0
                        for row in clean_rows:
                            if pk_col in row and row[pk_col] is not None:
                                existing = db.execute(
                                    select(table).where(table.c[pk_col] == row[pk_col])
                                ).first()
                                if existing:
                                    update_vals = {k: v for k, v in row.items() if k != pk_col}
                                    if update_vals:
                                        db.execute(
                                            table.update().where(table.c[pk_col] == row[pk_col]).values(**update_vals)
                                        )
                                else:
                                    db.execute(table.insert().values(**row))
                            else:
                                db.execute(table.insert().values(**row))
                            cnt += 1
                        restored_counts[table.name] = cnt
                        total_records_restored += cnt

                    db.flush()

                # Reset PostgreSQL sequences after inserting explicit primary keys
                _reset_postgres_sequences(db)

                # Commit DB transaction
                db.commit()

            except Exception as db_err:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Database restoration failed: {str(db_err)}"
                )
            finally:
                db._audit_disabled = False  # type: ignore

            # 2. Extract and restore media files
            images_restored = 0
            storage_backend = (settings.STORAGE_BACKEND or "local").lower()
            storage = create_backend() if storage_backend != "local" else None

            for name in namelist:
                if name.startswith("uploads/") and not name.endswith("/"):
                    rel_path = name[len("uploads/"):].strip()
                    if not rel_path or not _is_safe_archive_path(rel_path):
                        continue

                    file_data = zf.read(name)
                    if storage_backend == "local":
                        dest_path = os.path.join(settings.UPLOAD_DIR, rel_path.replace("/", os.sep))
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        with open(dest_path, "wb") as f_img:
                            f_img.write(file_data)
                    else:
                        # S3 or other remote storage
                        content_type, _ = mimetypes.guess_type(rel_path)
                        storage.save(rel_path, file_data, content_type or "application/octet-stream")

                    images_restored += 1

            # Log audit trail for restoration
            try:
                audit = AuditLog(
                    table_name="system",
                    record_id=0,
                    record_name=f"Backup Restore ({file.filename})",
                    action="RESTORE_BACKUP",
                    changes={
                        "filename": file.filename,
                        "mode": mode,
                        "total_records": total_records_restored,
                        "images_restored": images_restored,
                        "tables": restored_counts
                    },
                    actor_id=current_admin.id,
                    actor_email=current_admin.email,
                    actor_role=current_admin.role,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(audit)
                db.commit()
            except Exception:
                db.rollback()

            return APIResponse(
                status="success",
                message=f"Backup restored successfully: {total_records_restored} database records and {images_restored} media files restored ({mode} mode).",
                data={
                    "mode": mode,
                    "filename": file.filename,
                    "tables_restored": restored_counts,
                    "total_records": total_records_restored,
                    "images_restored": images_restored
                }
            )

    finally:
        if os.path.exists(tmp_zip_path):
            try:
                os.unlink(tmp_zip_path)
            except OSError:
                pass
