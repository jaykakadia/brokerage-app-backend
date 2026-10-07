import os
from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_NAME: str = "TradeCall API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite:///./tradecall.db"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if isinstance(v, str) and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v

    # Security & JWT
    SECRET_KEY: str = "tradecall_secret_encryption_key_32_bytes_super_secure"
    JWT_SECRET_KEY: str = "tradecall_local_dev_secret_key_32_bytes_super_secure_jwt_token"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days
    CSRF_SECRET_KEY: str = "tradecall_local_dev_csrf_secret_32_bytes_key_protection"

    # Cookies
    COOKIE_NAME: str = "access_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: Optional[str] = None

    # Storage
    # "local": files on this server's disk under UPLOAD_DIR (VPS / local dev).
    # "s3": any S3-compatible bucket (Supabase Storage, Cloudflare R2, AWS S3, Backblaze B2, MinIO).
    STORAGE_BACKEND: str = "local"
    # Prefix that turns a stored key into a public URL: "/uploads" for local, or the bucket's
    # public URL, e.g. "https://<ref>.supabase.co/storage/v1/object/public/<bucket>" or "https://pub-xxxx.r2.dev".
    MEDIA_BASE_URL: str = "/uploads"
    UPLOAD_DIR: str = "./uploads"
    # Supabase: https://<ref>.supabase.co/storage/v1/s3 · R2: https://<account_id>.r2.cloudflarestorage.com · AWS: empty
    S3_ENDPOINT_URL: str = ""
    S3_BUCKET: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_REGION: str = "auto"  # Supabase: the project's region (e.g. ap-south-1); R2: "auto"
    MAX_UPLOAD_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB
    MAX_IMAGES_PER_LISTING: int = 10

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    # Cashfree Payments
    CASHFREE_APP_ID: str = ""
    CASHFREE_SECRET_KEY: str = ""
    CASHFREE_ENVIRONMENT: str = "sandbox"  # sandbox | production
    CASHFREE_API_VERSION: str = "2025-01-01"
    CASHFREE_MOCK: bool = False  # true only for local dev/tests: orders are treated as paid
    # Optional https webhook URL sent with each order; leave empty to use the one set in the Cashfree dashboard
    CASHFREE_NOTIFY_URL: str = ""

    # SMTP Mail Service
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@tradecall.in"
    SMTP_FROM_NAME: str = "TradeCall India"
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    SMTP_MOCK: bool = True

    # Brevo transactional email API (HTTPS). When set, used instead of SMTP —
    # needed on hosts that block outbound SMTP ports (e.g. Render free tier).
    BREVO_API_KEY: str = ""
    BREVO_SENDER_EMAIL: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
