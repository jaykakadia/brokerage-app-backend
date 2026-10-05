# TradeCall India — Backend API

# TradeCall India | Backend API

<div align="center">

### The API behind TradeCall India

FastAPI service for listings, accounts, moderation, subscriptions, and buyer leads.

![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.x-D71F00)
![License](https://img.shields.io/badge/license-proprietary-lightgrey)

</div>

## Contents

- [Overview](#overview)
- [Capabilities](#capabilities)
- [Technology](#technology)
- [Requirements](#requirements)
- [Run Locally](#run-locally)
- [Configuration](#configuration)
- [API Surface](#api-surface)
- [Database Migrations](#database-migrations)
- [Tests](#tests)
- [Docker](#docker)
- [Production Checklist](#production-checklist)

## Overview

TradeCall India is a real-estate and business directory. This service exposes the versioned `/api/v1` API used by the frontend, serves uploaded assets under `/uploads`, and provides a compatibility layer for legacy PHP-style API paths.

## Capabilities

- **Accounts and access:** registration and email OTP flows, cookie-based JWT sessions, CSRF protection, profile management, role-based access, and admin user management.
- **Listings:** searchable listings, listing submission with images, moderation states, role-based posting limits, and Field Associate attribution.
- **Plans and leads:** subscription plan management, Cashfree orders and payment verification, webhook reconciliation, lead credits, and contact reveal.
- **Buyer tools:** authenticated wishlist operations and listing statistics.
- **Operations:** manage locations, categories, users, Field Associates, blogs, payment settings, and SMTP settings.
- **Email and payments:** mock modes for local development; runtime SMTP configuration and encrypted stored SMTP credentials; payment signature verification and idempotent crediting.

## Technology

| Area                      | Tools                                                   |
| ------------------------- | ------------------------------------------------------- |
| Runtime and API           | Python 3.12, FastAPI, Uvicorn                           |
| Persistence               | SQLAlchemy 2.x, SQLite or PostgreSQL, Alembic           |
| Schemas and configuration | Pydantic v2, pydantic-settings                          |
| Integrations              | Cashfree PG HTTP API, SMTP, `httpx`                     |
| Tests                     | pytest, FastAPI TestClient, SQLite in-memory by default |

## Requirements

- Python 3.12
- pip
- PostgreSQL for a shared or production database; SQLite is supported for local development
- Docker and Docker Compose are optional

## Run Locally

From this directory, create and activate a virtual environment and install dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create the local environment file:

```bash
cp .env.example .env
```

For a simple SQLite development database, set this in `.env`:

```dotenv
DATABASE_URL=sqlite:///./tradecall.db
```

The checked-in `.env.example` uses a placeholder PostgreSQL URL. Replace it with your own database URL if you prefer PostgreSQL. Apply migrations, create an admin user, and start the API:

```bash
alembic upgrade head
python -m app.cli create-admin --email admin@example.com --name "TradeCall Admin"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The admin command prompts for the password without echoing it. It can also read `ADMIN_PASSWORD` from the environment; do not pass a password as a command-line argument.

- Health check: [http://localhost:8000/health](http://localhost:8000/health)
- OpenAPI / Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Configuration

Settings are loaded from environment variables and `.env` by `pydantic-settings`. The most important variables are:

| Variable                                            | Purpose                                                                   |
| --------------------------------------------------- | ------------------------------------------------------------------------- |
| `DATABASE_URL`                                      | SQLAlchemy database URL; defaults to local SQLite in application settings |
| `SECRET_KEY`                                        | Key material used to encrypt stored SMTP secrets                          |
| `JWT_SECRET_KEY`                                    | Signs authentication tokens                                               |
| `CSRF_SECRET_KEY`                                   | Signs CSRF tokens                                                         |
| `ALLOWED_ORIGINS`                                   | Comma-separated frontend origins allowed by CORS                          |
| `COOKIE_SECURE`                                     | Set `true` when serving over HTTPS                                        |
| `COOKIE_SAMESITE`, `COOKIE_DOMAIN`                  | Authentication cookie policy and optional domain                          |
| `UPLOAD_DIR`, `MAX_UPLOAD_SIZE_BYTES`               | Upload storage directory and per-file limit                               |
| `SMTP_*`, `SMTP_MOCK`                               | SMTP connection details and local mock mode                               |
| `CASHFREE_*`, `CASHFREE_MOCK`                       | Gateway App ID, secret key, environment, and local mock mode              |

Generate unique secret values for `SECRET_KEY`, `JWT_SECRET_KEY`, and `CSRF_SECRET_KEY` before deployment (for example, with `openssl rand -hex 32`). Keep them outside source control. Changing `SECRET_KEY` can make previously encrypted SMTP credentials unreadable. Leave SMTP and Cashfree mock modes enabled for local development; configure real credentials before disabling them.

For the frontend at `http://localhost:5173`, include that exact origin in `ALLOWED_ORIGINS`. Credentialed requests require explicit allowed origins.

## API Surface

The interactive OpenAPI documentation at `/docs` is the source of truth for request and response schemas. Main route groups include:

| Prefix                                           | Responsibility                                                       |
| ------------------------------------------------ | -------------------------------------------------------------------- |
| `/api/v1/auth`                                   | CSRF, registration, OTP, login, logout, current user, admin setup    |
| `/api/v1/users`                                  | User profile and admin user operations                               |
| `/api/v1/listings`                               | Search, detail, create, moderation, statistics                       |
| `/api/v1/locations`, `/api/v1/categories`        | Listing taxonomy                                                     |
| `/api/v1/wishlist`                               | Saved listings                                                       |
| `/api/v1/plans`, `/api/v1/payments`              | Plans, payment orders, verification, webhook, admin gateway settings |
| `/api/v1/leads`                                  | Lead balance and contact reveal                                      |
| `/api/v1/employees`, `/api/v1/admin/role-limits` | Field Associates and role posting caps                               |
| `/api/v1/blogs`, `/api/v1/admin/settings`        | Blog publishing and SMTP administration                              |
| `/api/*.php`                                     | Legacy compatibility handlers                                        |

Uploaded assets are served from `/uploads`. Listing and API data access is protected by user or admin authorization where applicable.

## Database Migrations

Apply all migrations with:

```bash
alembic upgrade head
```

The migration chain is in `alembic/versions/`. Generate a new revision after changing models with `alembic revision --autogenerate -m "describe change"`, then review the generated migration before applying it. Use `alembic downgrade -1` to revert one revision where the migration supports downgrade.

## Tests

Run the backend test suite from this directory:

```bash
pytest -v
```

Tests cover authentication, listings and uploads, plans and payments, lead reveals and transaction behavior, wishlists, users, locations and categories, Field Associates, blogs, and mail settings. The suite uses an in-memory SQLite database by default. Set `TEST_DATABASE_URL` to override it.

## Docker

The Compose service reads configuration from `.env`, exposes port `8000`, and persists uploads in the local `uploads/` directory.

```bash
cp .env.example .env
# Set DATABASE_URL and required secrets in .env.
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

## Production Checklist

- Use HTTPS, unique high-entropy secrets, `COOKIE_SECURE=true`, and an explicit `ALLOWED_ORIGINS` list.
- Set `DEBUG=false`; never use development secret defaults in a deployed environment.
- Configure a managed PostgreSQL database, apply migrations as a deployment step, and back up the database.
- Set `SMTP_MOCK=false` and `CASHFREE_MOCK=false` only after valid credentials are configured. Set `CASHFREE_ENVIRONMENT=production` for live payments, and point the Cashfree dashboard webhook at `/api/v1/payments/webhook`.
- Persist uploaded media outside ephemeral container storage and include it in backup/retention plans.
- Keep `.env`, payment secrets, and mail credentials out of Git and logs.
