# TradeCall India — Backend API

Production-grade FastAPI backend re-engineering the complete **TradeCall India** real estate and property directory platform.

## Technology Stack

- **Runtime**: Python 3.12+ (tested with Python 3.14)
- **Framework**: FastAPI
- **Database & ORM**: PostgreSQL (Supabase cloud compatible) / SQLite for local development, SQLAlchemy 2.x
- **Schema Migrations**: Alembic
- **Data Validation & Serialization**: Pydantic v2
- **Authentication**: JWT stored in secure `HttpOnly`, `SameSite=Lax` cookies (`access_token`)
- **Cryptography & Security**:
  - `bcrypt` for user password hashing
  - `cryptography` (Fernet authenticated AES-128-CBC + HMAC) for database secrets encryption at rest (SMTP credentials)
  - CSRF double-submit token protection
  - Path traversal and file upload magic bytes validation
- **Mail Delivery**: Python `smtplib` / `aiosmtplib` with dynamic runtime database configuration and local mock fallback
- **Payments**: Razorpay Orders & HMAC-SHA256 signature verification with idempotent webhook processing

---

## Core Modules & Capabilities

### 1. Authentication, RBAC & Users
- **Canonical Roles**: `Owner`, `Agent`, `Builder`, `Admin`.
- **Registration & OTP Flow**: Email-based 6-digit OTP verification with 10-minute expiry and resend cooldowns.
- **Session Management**: Secure HttpOnly cookies with CSRF token validation on state-changing requests.
- **Account Control**: In-place profile updates and password change with current password verification.
- **Admin User Management**: Admin user lookup, role reassignment, and soft deactivation.

### 2. Listings & Moderation Engine
- **Property Lifecycle**: Full moderation states (`pending`, `approved`, `sold`, `rented`, `suspended`, `deleted`).
- **Role-Based Listing Limits**: Configurable max listings per role (`Owner`, `Agent`, `Builder`). Uncapped when set to `0`. Paid subscription plans bypass role caps.
- **Field Associate Linkage**: Automatically attributes listings to active Field Associates via unique 6-character reference codes.
- **Media Uploads**: Multi-photo upload validation (JPEG, PNG, WebP) with strict file size and MIME-type enforcement.

### 3. Monetization & Buyer Engagement
- **Membership Plans**: Multi-tier plans defining price, lead balance credits, and active duration.
- **Razorpay Payment Integration**: Order generation, HMAC signature verification, and idempotent webhook handlers for automated lead credit.
- **Atomic Lead Reveal Engine**: Concurrency-safe contact reveal with database row locking (`select_for_update()`), preventing double-spend and guaranteeing balance integrity.
- **Wishlist / Shortlist**: User property bookmarking with optimistic frontend updates and automatic exclusion of deleted listings.

### 4. Field Associates (Tracker Module)
- **Reference Code Generator**: Generates 6-character uppercase alphanumeric tracking codes excluding ambiguous characters.
- **Performance Tracking**: Aggregated real-time metrics showing total listings tracked and active reference codes.
- **Public Reference Picker**: Endpoint exposing active associates for listing attribution during property submission.

### 5. Blog Management & Content
- **Public Feed**: Filterable by categories (`Buy`, `Rent`, `Invest`, `Real Estate`) and search keywords.
- **Draft Protection**: Public endpoints strictly reject draft articles with HTTP 404.
- **Admin Management**: Full CRUD with featured image upload and custom permalink slug generation.

### 6. SMTP Settings & Secret Encryption
- **Dynamic Configuration**: Admin can update SMTP host, port, mail ID, encryption (SSL/TLS), and password at runtime without restarting the server.
- **Encryption at Rest**: Passwords stored in `system_settings` are encrypted using Fernet symmetric encryption derived from `SECRET_KEY`.
- **Zero-Exposure Policy**: Passwords are never returned in GET responses and never written to application logs.
- **Test Email Dispatcher**: Admin endpoint allowing instant delivery tests to verify outbound SMTP credentials.

### 7. Legacy API Compatibility Layer
- **Complete Parity**: Maps all **51 original TradeCall PHP endpoints** directly to backend business logic under the `/api/*.php` prefix, ensuring full backward compatibility with legacy scripts and forms.

---

## Setup & Running

### 1. Create Virtual Environment & Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Key environment configurations:
```ini
# Application
APP_NAME="TradeCall API"
ENVIRONMENT="development"
DEBUG=True
SECRET_KEY="tradecall_secret_encryption_key_32_bytes_super_secure"

# Database (SQLite default; use postgresql+psycopg:// for PostgreSQL / Supabase)
DATABASE_URL="sqlite:///./tradecall.db"

# JWT & CSRF
JWT_SECRET_KEY="tradecall_local_dev_secret_key_32_bytes_super_secure_jwt_token"
CSRF_SECRET_KEY="tradecall_local_dev_csrf_secret_32_bytes_key_protection"

# SMTP Mail
SMTP_HOST="smtp.gmail.com"
SMTP_PORT=587
SMTP_USERNAME="tradecall.in@gmail.com"
SMTP_PASSWORD="your-app-password"
SMTP_USE_TLS=True
SMTP_MOCK=True  # Set to False for live outbound email delivery

# Razorpay
RAZORPAY_KEY_ID="rzp_test_placeholder"
RAZORPAY_KEY_SECRET="rzp_test_secret_placeholder"
RAZORPAY_MOCK=True
```

### 3. Run Database Migrations
```bash
alembic upgrade head
```

### 4. Bootstrap SuperAdmin Account
```bash
python -m app.cli create-admin --email admin@tradecall.in --password StrongAdminPassword123 --name "TradeCall SuperAdmin"
```

### 5. Start Development Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Interactive API documentation:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 6. Run Automated Test Suite
```bash
pytest -v
```
Runs all 30 tests covering authentication, concurrency, idempotent webhooks, role limits, employees, blogs, encrypted SMTP settings, and E2E flows.

---

## Docker Deployment
```bash
docker compose up -d --build
```
