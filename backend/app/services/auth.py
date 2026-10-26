import hashlib
import secrets
import smtplib
import ssl
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from uuid import uuid4

import jwt
from fastapi import HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuthSession, Merchant, PasswordResetToken, UserAccount
from app.schemas.api import ProfileOut

password_hasher = PasswordHash.recommended()
dummy_password_hash = password_hasher.hash("not-a-real-user-password")
_request_windows: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def enforce_rate_limit(request: Request, action: str, limit: int, window_seconds: int = 60) -> None:
    address = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = _request_windows[(action, address)]
    while attempts and attempts[0] <= now - window_seconds:
        attempts.popleft()
    if len(attempts) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests. Try again shortly.")
    attempts.append(now)


def new_session(db: Session, user: UserAccount) -> tuple[str, str, int]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    session = AuthSession(
        id=str(uuid4()),
        user_id=user.id,
        refresh_token_hash="",
        expires_at=now + timedelta(days=settings.auth_refresh_token_days),
    )
    refresh_token = secrets.token_urlsafe(48)
    session.refresh_token_hash = token_digest(refresh_token)
    db.add(session)
    db.commit()
    access_token = jwt.encode(
        {
            "sub": user.id,
            "sid": session.id,
            "typ": "access",
            "exp": now + timedelta(minutes=settings.auth_access_token_minutes),
            "iat": now,
            "jti": secrets.token_urlsafe(16),
        },
        settings.auth_secret_key,
        algorithm="HS256",
    )
    return access_token, refresh_token, settings.auth_access_token_minutes * 60


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_access_token(token: str) -> dict:
    try:
        claims = jwt.decode(token, get_settings().auth_secret_key, algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Sign in to continue.") from exc
    if claims.get("typ") != "access" or not isinstance(claims.get("sid"), str):
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return claims


def get_account_for_session(db: Session, claims: dict) -> tuple[UserAccount, AuthSession]:
    session = db.get(AuthSession, claims["sid"])
    user = db.get(UserAccount, claims.get("sub"))
    now = datetime.now(timezone.utc)
    expires_at = session.expires_at.replace(tzinfo=timezone.utc) if session and session.expires_at.tzinfo is None else (session.expires_at if session else now)
    if (
        session is None
        or user is None
        or not user.is_active
        or session.user_id != user.id
        or session.revoked_at is not None
        or expires_at <= now
    ):
        raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.")
    return user, session


def make_profile(user: UserAccount, merchant: Merchant) -> ProfileOut:
    return ProfileOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        merchant_id=merchant.id,
        business_name=merchant.name,
        business_category=merchant.category,
        business_model=merchant.business_model,
        sales_channels=merchant.sales_channels or [],
        business_stage=merchant.business_stage,
        sales_tracking=merchant.sales_tracking,
        business_size=merchant.business_size,
        currency=merchant.currency,
        business_location=merchant.business_location,
        goals=merchant.goals or [],
        preferred_language=merchant.preferred_language,
        response_detail=merchant.response_detail,
        interaction_mode=merchant.interaction_mode,
        theme=merchant.theme,
        notifications=merchant.notifications or {},
        onboarding_step=merchant.onboarding_step,
        onboarding_answers=merchant.onboarding_answers or {},
        onboarding_completed=merchant.onboarding_completed,
    )


def owned_merchant(db: Session, user: UserAccount) -> Merchant:
    merchant = db.scalar(select(Merchant).where(Merchant.owner_user_id == user.id, Merchant.is_demo.is_(False)))
    if merchant is None:
        raise HTTPException(status_code=404, detail="Business profile not found.")
    return merchant


def set_session_cookies(response, refresh_token: str, csrf_token: str) -> None:
    settings = get_settings()
    secure = settings.app_env.lower() == "production"
    response.set_cookie(
        "udyamai_refresh",
        refresh_token,
        max_age=settings.auth_refresh_token_days * 86400,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/auth/session",
    )
    response.set_cookie(
        "udyamai_csrf",
        csrf_token,
        max_age=settings.auth_refresh_token_days * 86400,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response) -> None:
    secure = get_settings().app_env.lower() == "production"
    response.delete_cookie("udyamai_refresh", path="/api/auth/session", secure=secure, httponly=True, samesite="lax")
    response.delete_cookie("udyamai_csrf", path="/", secure=secure, samesite="lax")


def verify_csrf(request: Request, supplied: str | None) -> None:
    cookie = request.cookies.get("udyamai_csrf")
    origin = request.headers.get("origin")
    if (
        not cookie
        or not supplied
        or not secrets.compare_digest(cookie, supplied)
        or (origin and origin.rstrip("/") not in get_settings().allowed_origins)
    ):
        raise HTTPException(status_code=403, detail="Request verification failed. Refresh the page and try again.")


def deliver_password_reset(email: str, reset_url: str | None) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        raise HTTPException(status_code=503, detail="Password recovery email is not configured.")
    message = EmailMessage()
    message["Subject"] = "Reset your UdyamAI password"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    if reset_url:
        body = f"Use this single-use link within 30 minutes to reset your password:\n\n{reset_url}\n\nIf you did not request this, you can ignore this email."
    else:
        body = "If an account exists for this address, a password reset link will be sent. If you did not request this, you can ignore this email."
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise HTTPException(status_code=503, detail="Password recovery email could not be sent. Try again later.") from exc


def password_reset_token(db: Session, user: UserAccount) -> tuple[PasswordResetToken, str]:
    raw_token = secrets.token_urlsafe(48)
    record = PasswordResetToken(
        id=str(uuid4()),
        user_id=user.id,
        token_hash=token_digest(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    db.add(record)
    db.flush()
    return record, raw_token
