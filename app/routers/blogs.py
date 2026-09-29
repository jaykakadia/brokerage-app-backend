import random
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin, get_db
from app.db.models.user import User
from app.db.models.blog import Blog
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.blog import BlogRead, BlogCreate, BlogUpdate

router = APIRouter(prefix="/api/v1/blogs", tags=["Blogs"])


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
        if req.image_url:
            blog.image_url = req.image_url
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
            image_url=req.image_url
        )
        db.add(blog)
        db.commit()
        db.refresh(blog)

    return APIResponse(status="success", data=BlogRead.model_validate(blog))


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
