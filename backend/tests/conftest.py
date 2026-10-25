from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Merchant, Product


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    with TestingSession() as db:
        db.add_all([
            Merchant(id="personal", name="Test shop", category="Kirana", is_demo=False),
            Merchant(id="other", name="Other shop", category="Vendor", is_demo=False),
            Merchant(id="coconut", name="Demo cart", category="Street vendor", is_demo=True),
        ])
        db.add_all([
            Product(id="rice", merchant_id="personal", name="Rice", quantity=2, cost=5, price=10),
            Product(id="other-rice", merchant_id="other", name="Other rice", quantity=100, cost=2, price=8),
        ])
        db.commit()

    def override_get_db():
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def auth():
    return {"Authorization": "Bearer dev-personal-token"}
