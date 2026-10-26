from datetime import date

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.seed as seed_module
from app.db.base import Base
from app.models import (
    AutopilotTask,
    BusinessInsight,
    CampaignDraft,
    Expense,
    Merchant,
    Sale,
    Scenario,
)


def test_demo_seed_is_repeatable_and_reset_preserves_personal_records(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(seed_module, "SessionLocal", TestingSession)

    try:
        seed_module.seed()
        with TestingSession() as db:
            personal_sale = Sale(
                id="personal-preserved-sale",
                merchant_id="personal",
                amount=25,
                date=date.today(),
                quantity=1,
                note="Personal record",
            )
            db.add(personal_sale)
            db.commit()

        seed_module.seed()
        with TestingSession() as db:
            for model in (Sale, Expense, CampaignDraft, Scenario, AutopilotTask):
                first_count = db.scalar(
                    select(func.count()).select_from(model).where(model.merchant_id == "coconut")
                )
                assert first_count > 0
            assert db.scalar(
                select(func.count()).select_from(BusinessInsight).where(BusinessInsight.merchant_id == "coconut")
            ) > 0

        seed_module.seed(reset_demo=True)
        with TestingSession() as db:
            assert db.get(Sale, "personal-preserved-sale") is not None
            assert db.get(Merchant, "personal") is not None
            assert db.scalar(
                select(func.count()).select_from(CampaignDraft).where(CampaignDraft.merchant_id == "coconut")
            ) == 1
            assert db.scalar(
                select(func.count()).select_from(Scenario).where(Scenario.merchant_id == "coconut")
            ) == 1
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
