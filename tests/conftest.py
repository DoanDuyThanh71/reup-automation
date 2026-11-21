import os
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app as fastapi_app
import app.config
import app.database
import app.agents.orchestrator  # ensure loaded
config_module = sys.modules["app.config"]
database_module = sys.modules["app.database"]
orchestrator_module = sys.modules["app.agents.orchestrator"]

@pytest.fixture()
def db_session(monkeypatch):
    """Provides an isolated in-memory SQLite database for each test."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    # Monkeypatch SessionLocal across modules so ConfigManager and Orchestrator use the test DB
    monkeypatch.setattr(database_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(config_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(orchestrator_module, "SessionLocal", TestingSessionLocal)

    # Re-initialize default configs in the in-memory DB
    config_module.config._init_defaults()

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)

@pytest.fixture()
def client(db_session):
    """Provides a FastAPI TestClient wired to the isolated test DB."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()
