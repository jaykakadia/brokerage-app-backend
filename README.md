# TradeCall Rebuild — Backend (Phase 1)

Production-grade FastAPI backend rebuilding TradeCall India platform.

## Technology Stack
- **Runtime**: Python 3.12+ (tested with Python 3.14)
- **Framework**: FastAPI
- **ORM & DB**: SQLAlchemy 2.x, PostgreSQL (Supabase compatible) / SQLite for local development
- **Migrations**: Alembic
- **Validation**: Pydantic v2
- **Auth**: JWT stored in `HttpOnly`, `SameSite=Lax` cookie (`access_token`)
- **Security**: bcrypt password hashing, CSRF double-submit token protection, MIME/magic bytes validation, path traversal prevention, secure UUID file naming
- **Storage**: Local filesystem storage behind `StorageService` abstraction (ready for Supabase Storage/S3 in future phases)

## Setup & Running

### 1. Create Virtualenv & Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Default configuration supports local SQLite (`sqlite:///./tradecall.db`) or PostgreSQL (`postgresql+psycopg://user:password@localhost:5432/tradecall`).

### 3. Run Database Migrations
```bash
alembic upgrade head
```

### 4. Bootstrap Initial Admin User
```bash
python -m app.cli create-admin --email admin@tradecall.in --password StrongAdminPassword123 --name "TradeCall SuperAdmin"
```

### 5. Start Development Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
API Documentation will be available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 6. Run Test Suite
```bash
pytest
```

## Docker Deployment
```bash
docker compose up -d --build
```
