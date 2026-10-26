from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
import pytest

import app.api.routes as routes
import app.services.assistant as assistant_service
from app.db.session import get_db
from app.main import app
from app.models import Merchant, PasswordResetToken, UserAccount
from app.services.auth import password_hasher, token_digest


@contextmanager
def database_session():
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        yield db
    finally:
        generator.close()


@pytest.fixture(autouse=True)
def reset_auth_rate_limits():
    routes._assistant_requests.clear()
    from app.services import auth

    auth._request_windows.clear()


def register(client, *, email="owner@example.com", password="secure-password-123", business="My shop"):
    return client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Shop Owner",
            "business_name": business,
        },
    )


def bearer(response):
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_registration_hashes_password_and_returns_scoped_profile(client):
    response = register(client, email=" Owner@Example.com ")
    assert response.status_code == 201
    profile = response.json()["profile"]
    assert profile["email"] == "owner@example.com"
    assert profile["business_name"] == "My shop"
    assert profile["currency"] == "INR"
    assert profile["theme"] == "system"
    assert response.cookies["udyamai_refresh"]
    assert response.cookies.get("udyamai_csrf")

    with database_session() as db:
        user = db.scalar(select(UserAccount).where(UserAccount.email == "owner@example.com"))
        assert user is not None
        assert user.password_hash != "secure-password-123"
        assert password_hasher.verify("secure-password-123", user.password_hash)
        merchant = db.scalar(select(Merchant).where(Merchant.owner_user_id == user.id))
        assert merchant is not None
        assert merchant.is_demo is False

    read_profile = client.get("/api/auth/profile", headers=bearer(response))
    assert read_profile.status_code == 200
    assert read_profile.json()["merchant_id"] == profile["merchant_id"]
    assert client.get(
        f"/api/merchants/{profile['merchant_id']}",
        headers=bearer(response),
    ).status_code == 200


def test_registration_rejects_duplicate_normalized_email_and_weak_password(client):
    assert register(client).status_code == 201
    duplicate = register(client, email="OWNER@example.com")
    assert duplicate.status_code == 409
    weak = client.post(
        "/api/auth/register",
        json={"email": "another@example.com", "password": "short"},
    )
    assert weak.status_code == 422


def test_login_rejects_invalid_credentials_and_session_logout_revokes_access(client):
    created = register(client)
    assert created.status_code == 201
    invalid = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "wrong-password"},
    )
    assert invalid.status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"email": "OWNER@example.com", "password": "secure-password-123"},
    )
    assert login.status_code == 200
    csrf = login.cookies["udyamai_csrf"]
    access = bearer(login)
    missing_csrf = client.delete("/api/auth/session")
    assert missing_csrf.status_code == 403
    logged_out = client.delete(
        "/api/auth/session",
        headers={"X-CSRF-Token": csrf},
    )
    assert logged_out.status_code == 204
    assert client.get(f"/api/merchants/{login.json()['profile']['merchant_id']}", headers=access).status_code == 401


def test_refresh_rotates_cookie_and_rejects_missing_csrf(client):
    login = register(client)
    old_access = login.json()["access_token"]
    csrf = login.cookies["udyamai_csrf"]
    missing_csrf = client.post("/api/auth/session")
    assert missing_csrf.status_code == 403
    refreshed = client.post("/api/auth/session", headers={"X-CSRF-Token": csrf})
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != old_access
    assert refreshed.cookies["udyamai_refresh"] != login.cookies["udyamai_refresh"]
    assert client.get(
        f"/api/merchants/{refreshed.json()['profile']['merchant_id']}",
        headers=bearer(refreshed),
    ).status_code == 200


def test_account_token_cannot_access_another_merchants_data(client):
    first = register(client, email="first@example.com")
    second = register(client, email="second@example.com")
    first_profile = first.json()["profile"]
    second_profile = second.json()["profile"]
    assert client.get(
        f"/api/merchants/{second_profile['merchant_id']}",
        headers=bearer(first),
    ).status_code == 403
    update = client.patch(
        "/api/auth/profile",
        headers=bearer(first),
        json={"business_name": "Updated name", "theme": "dark", "goals": ["margins", "expenses"]},
    )
    assert update.status_code == 200
    assert update.json()["business_name"] == "Updated name"
    assert update.json()["theme"] == "dark"
    assert update.json()["goals"] == ["margins", "expenses"]
    assert client.get("/api/auth/profile", headers=bearer(second)).json()["merchant_id"] == second_profile["merchant_id"]
    protected_field = client.patch("/api/auth/profile", headers=bearer(first), json={"email": "intruder@example.com"})
    assert protected_field.status_code == 422


def test_profile_validation_persists_onboarding_and_personalizes_assistant_context(client):
    account = register(client)
    profile_path = "/api/auth/profile"
    profile_update = client.patch(
        profile_path,
        headers=bearer(account),
        json={
            "business_model": "services",
            "business_stage": "operating",
            "sales_tracking": "digital",
            "business_size": "2-5",
            "business_location": "Pune",
            "goals": ["margins", "expenses"],
            "preferred_language": "hinglish",
            "response_detail": "simple",
            "theme": "dark",
            "onboarding_step": 4,
            "onboarding_answers": {"business": "service business", "products": "tailoring", "goals": ["margins"]},
        },
    )
    assert profile_update.status_code == 200
    assert profile_update.json()["sales_tracking"] == "digital"
    assert profile_update.json()["preferred_language"] == "hinglish"
    assert profile_update.json()["onboarding_step"] == 4
    assert profile_update.json()["onboarding_answers"]["business"] == "service business"
    assert profile_update.json()["onboarding_answers"]["products"] == "tailoring"
    with database_session() as db:
        context = assistant_service.merchant_context(db, profile_update.json()["merchant_id"])
    assert context["merchant_profile"]["business_model"] == "services"
    assert context["merchant_profile"]["goals"] == ["margins", "expenses"]
    assert context["merchant_profile"]["response_detail"] == "simple"

    duplicate_goals = client.patch(profile_path, headers=bearer(account), json={"goals": ["sales", "sales"]})
    invalid_language = client.patch(profile_path, headers=bearer(account), json={"preferred_language": "xx"})
    invalid_notification = client.patch(
        profile_path,
        headers=bearer(account),
        json={"notifications": {"send_passwords": True}},
    )
    assert duplicate_goals.status_code == invalid_language.status_code == invalid_notification.status_code == 422


def test_password_reset_is_single_use_and_revokes_sessions(client, monkeypatch):
    delivery = {}

    def fake_delivery(email, reset_url):
        delivery["email"] = email
        delivery["url"] = reset_url

    monkeypatch.setattr(routes, "deliver_password_reset", fake_delivery)
    created = register(client)
    requested = client.post(
        "/api/auth/password-reset/request",
        json={"email": "OWNER@example.com"},
    )
    assert requested.status_code == 202
    reset_token = delivery["url"].split("reset_token=", 1)[1]
    assert reset_token
    with database_session() as db:
        assert db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == reset_token)) is None
        record = db.scalar(select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_digest(reset_token),
        ))
        assert record is not None
        expiry = record.expires_at.replace(tzinfo=timezone.utc) if record.expires_at.tzinfo is None else record.expires_at
        assert expiry > datetime.now(timezone.utc)

    completed = client.post(
        "/api/auth/password-reset/complete",
        json={"token": reset_token, "password": "new-secure-password-456"},
    )
    assert completed.status_code == 204
    reused = client.post(
        "/api/auth/password-reset/complete",
        json={"token": reset_token, "password": "another-secure-password-789"},
    )
    assert reused.status_code == 400
    assert client.get(
        f"/api/merchants/{created.json()['profile']['merchant_id']}",
        headers=bearer(created),
    ).status_code == 401
    login = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "new-secure-password-456"},
    )
    assert login.status_code == 200


def test_expired_password_reset_token_is_rejected(client):
    created = register(client)
    with database_session() as db:
        user = db.scalar(select(UserAccount).where(UserAccount.email == "owner@example.com"))
        db.add(PasswordResetToken(
            id="expired-reset",
            user_id=user.id,
            token_hash=token_digest("expired-reset-token-value-1234567890"),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        ))
        db.commit()
    response = client.post(
        "/api/auth/password-reset/complete",
        json={"token": "expired-reset-token-value-1234567890", "password": "new-secure-password-456"},
    )
    assert response.status_code == 400
    assert client.get(
        f"/api/merchants/{created.json()['profile']['merchant_id']}",
        headers=bearer(created),
    ).status_code == 200


def test_password_reset_request_does_not_disclose_unknown_email(client, monkeypatch):
    monkeypatch.setattr(routes, "deliver_password_reset", lambda email, reset_url: None)
    registered = client.post("/api/auth/password-reset/request", json={"email": "known@example.com"})
    unknown = client.post("/api/auth/password-reset/request", json={"email": "unknown@example.com"})
    assert registered.status_code == unknown.status_code == 202
    assert registered.json() == unknown.json()
