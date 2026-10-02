import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.core.security import hash_password
from app.db.models.user import User
from app.db.models.location import Location
from app.db.models.category import Category

# Support both SQLite (default) and PostgreSQL for testing
TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")

if TEST_DB_URL.startswith("sqlite"):
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
else:
    engine = create_engine(TEST_DB_URL)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)



@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    # Set test upload dir
    test_upload = "./test_uploads"
    settings.UPLOAD_DIR = test_upload
    settings.SMTP_MOCK = True
    settings.BREVO_API_KEY = ""  # tests must never send real email
    os.makedirs(os.path.join(test_upload, "listings"), exist_ok=True)
    yield
    import shutil
    if os.path.exists(test_upload):
        shutil.rmtree(test_upload)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session: Session) -> User:
    user = User(
        name="John Doe",
        phone="9876543210",
        email="john@example.com",
        password_hash=hash_password("password123"),
        role="Owner",
        status="active"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def inactive_user(db_session: Session) -> User:
    user = User(
        name="Banned User",
        phone="9876543211",
        email="banned@example.com",
        password_hash=hash_password("password123"),
        role="Owner",
        status="inactive"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session: Session) -> User:
    admin = User(
        name="Admin Boss",
        phone="9999999999",
        email="admin@example.com",
        password_hash=hash_password("adminpass123"),
        role="Admin",
        status="active"
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin
