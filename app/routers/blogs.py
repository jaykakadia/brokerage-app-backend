import random
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text

from app.core.dependencies import get_current_admin, get_db
from app.db.session import engine
from app.db.models.user import User
from app.db.models.blog import Blog
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.blog import BlogRead, BlogCreate, BlogUpdate

router = APIRouter(prefix="/api/v1/blogs", tags=["Blogs"])


def ensure_blog_meta_column():
    try:
        inspector = inspect(engine)
        if "blogs" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("blogs")]
            if "meta_description" not in cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE blogs ADD COLUMN meta_description TEXT"))
    except Exception as e:
        print("ensure_blog_meta_column warning:", e)

ensure_blog_meta_column()


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


# --- PUBLIC BLOG ENDPOINTS ---

@router.get("", response_model=APIResponse[List[BlogRead]])
def list_public_blogs(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Public endpoint to fetch published blogs."""
    query = db.query(Blog).filter(Blog.status.in_(["published", "publish"]))
    if category and category.lower() != "all":
        query = query.filter(Blog.category.ilike(category.strip()))
    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            (Blog.title.ilike(search_term)) |
            (Blog.content.ilike(search_term)) |
            (Blog.tags.ilike(search_term))
        )
    blogs = query.order_by(Blog.id.desc()).all()
    data = [BlogRead.model_validate(b) for b in blogs]
    return APIResponse(status="success", data=data)


@router.get("/detail/{id_or_slug}", response_model=APIResponse[BlogRead])
def get_public_blog(
    id_or_slug: str,
    db: Session = Depends(get_db)
):
    """Public endpoint to view single blog by ID or permalink slug."""
    if id_or_slug.isdigit():
        blog = db.query(Blog).filter(Blog.id == int(id_or_slug)).first()
    else:
        blog = db.query(Blog).filter(Blog.permalink == id_or_slug.strip().lower()).first()

    if not blog or blog.status not in ["published", "publish"]:
        raise HTTPException(status_code=404, detail="Blog not found.")

    return APIResponse(status="success", data=BlogRead.model_validate(blog))


# --- ADMIN BLOG ENDPOINTS ---

@router.get("/admin/all", response_model=APIResponse[List[BlogRead]])
def list_admin_blogs(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin endpoint to list all blogs including drafts."""
    blogs = db.query(Blog).order_by(Blog.id.desc()).all()
    data = [BlogRead.model_validate(b) for b in blogs]
    return APIResponse(status="success", data=data)


@router.get("/admin/{blog_id}", response_model=APIResponse[BlogRead])
def get_admin_blog(
    blog_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin endpoint to fetch single blog for editing."""
    blog = db.query(Blog).filter(Blog.id == blog_id).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found.")
    return APIResponse(status="success", data=BlogRead.model_validate(blog))


@router.post("/admin", response_model=APIResponse[BlogRead])
def create_or_update_blog(
    req: BlogCreate,
    blog_id: Optional[int] = Query(None),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin create or update blog article."""
    permalink = slugify(req.permalink) if req.permalink else slugify(req.title)
    if not permalink:
        permalink = f"post-{random.randint(1000, 9999)}"

    # Normalize status to published / draft
    status_clean = "published" if req.status in {"publish", "published"} else "draft"

    if blog_id and blog_id > 0:
        blog = db.query(Blog).filter(Blog.id == blog_id).first()
        if not blog:
            raise HTTPException(status_code=404, detail="Blog not found.")

        # Check permalink uniqueness
        existing = db.query(Blog).filter(Blog.permalink == permalink, Blog.id != blog_id).first()
        if existing:
            permalink = f"{permalink}-{blog_id}"

        blog.title = req.title.strip()
        blog.category = req.category.strip()
        blog.content = req.content
        blog.permalink = permalink
        blog.tags = req.tags
        blog.status = status_clean
        blog.author = req.author or admin.name
        if req.image_url is not None:
            blog.image_url = req.image_url
        if req.meta_description is not None:
            blog.meta_description = req.meta_description
        db.commit()
        db.refresh(blog)
    else:
        # Check permalink uniqueness
        existing = db.query(Blog).filter(Blog.permalink == permalink).first()
        if existing:
            permalink = f"{permalink}-{random.randint(100, 999)}"

        blog = Blog(
            title=req.title.strip(),
            category=req.category.strip(),
            content=req.content,
            permalink=permalink,
            tags=req.tags,
            status=status_clean,
            author=req.author or admin.name,
            image_url=req.image_url,
            meta_description=req.meta_description,
        )
        db.add(blog)
        db.commit()
        db.refresh(blog)

    return APIResponse(status="success", data=BlogRead.model_validate(blog))


@router.post("/admin/upload-image", response_model=APIResponse[dict])
async def upload_blog_image(
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin),
):
    """Admin endpoint to upload blog thumbnail/content image."""
    from app.services.storage_service import storage_service, ALLOWED_EXTENSIONS
    import os, uuid
    from starlette.concurrency import run_in_threadpool

    filename = file.filename or "image.jpg"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Allowed: {list(ALLOWED_EXTENSIONS)}"
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")

    detected_ext = storage_service._validate_image_bytes(content[:16]) or "jpg"
    content, detected_ext = await run_in_threadpool(storage_service._optimize_image, content, detected_ext)

    key = f"blogs/{uuid.uuid4().hex}.{detected_ext}"
    mime_type = "image/jpeg" if detected_ext == "jpg" else f"image/{detected_ext}"
    await run_in_threadpool(storage_service.backend.save, key, content, mime_type)

    url = f"/uploads/{key}"
    return APIResponse(status="success", data={"url": url, "key": key})


@router.delete("/admin/{blog_id}", response_model=MessageResponse)
def delete_blog(
    blog_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin delete blog article."""
    blog = db.query(Blog).filter(Blog.id == blog_id).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found.")
    db.delete(blog)
    db.commit()
    return MessageResponse(status="success", message="Blog deleted successfully.")
