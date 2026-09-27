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
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB
    MAX_IMAGES_PER_LISTING: int = 10

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    # Razorpay Payments
    RAZORPAY_KEY_ID: str = "rzp_test_placeholder"
    RAZORPAY_KEY_SECRET: str = "rzp_test_secret_placeholder"
    RAZORPAY_WEBHOOK_SECRET: str = "rzp_test_webhook_secret_placeholder"
    RAZORPAY_MOCK: bool = True
    RAZORPAY_TEST_MODE: bool = True

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
