import os
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.config import settings
from app.routers.auth import router as auth_router
from app.routers.users import router as users_router
from app.routers.listings import router as listings_router
from app.routers.locations import router as locations_router
from app.routers.categories import router as categories_router
from app.routers.wishlist import router as wishlist_router
from app.routers.plans import router as plans_router
from app.routers.leads import router as leads_router
from app.routers.payments import router as payments_router
from app.routers.employees import router as employees_router
from app.routers.role_limits import router as role_limits_router
from app.routers.blogs import router as blogs_router
from app.routers.settings import router as settings_router, public_router as public_settings_router
from app.routers.legacy_compat import router as legacy_router


app = FastAPI(
    title=settings.APP_NAME,
    description="TradeCall Real Estate & Business Directory API (Re-Engineered)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 1. CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Static File Serving for Uploaded Assets
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "listings"), exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# 3. Include API Routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(listings_router)
app.include_router(locations_router)
app.include_router(categories_router)
app.include_router(wishlist_router)
app.include_router(plans_router)
app.include_router(leads_router)
app.include_router(payments_router)
app.include_router(employees_router)
app.include_router(role_limits_router)
app.include_router(blogs_router)
app.include_router(settings_router)
app.include_router(public_settings_router)
app.include_router(legacy_router)


# 4. Standardized Error Handling
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = errors[0].get("msg") if errors else "Validation error"
    field = errors[0].get("loc", [""])[-1] if errors else ""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "message": f"{field}: {msg}" if field else msg,
            "errors": errors
        }
    )


@app.get("/health", tags=["Health"])
@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "success",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0"
    }
