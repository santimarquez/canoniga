from __future__ import annotations

import hashlib
import os
import re
import secrets
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from als_intel.store import EvidenceStore


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class AuthConfig:
    app_base_url: str
    magic_link_ttl_seconds: int
    session_ttl_seconds: int
    session_renew_window_seconds: int
    cookie_name: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_starttls: bool
    dev_mode: bool
    request_rate_limit_count: int
    request_rate_limit_window_seconds: int
    request_rate_limit_ip_count: int
    cookie_secure: bool
    cookie_same_site: str
    cookie_http_only: bool
    cookie_path: str
    cookie_domain: str


class AuthService:
    def __init__(self, config: AuthConfig) -> None:
        self.config = config

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def normalize_email(raw_email: str) -> str:
        return str(raw_email or "").strip().lower()

    @staticmethod
    def is_valid_email(email: str) -> bool:
        return bool(_EMAIL_PATTERN.match(email))

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _build_magic_link(self, token: str) -> str:
        return f"{self.config.app_base_url.rstrip('/')}/?magic_token={token}"

    def create_magic_link(
        self,
        *,
        store: EvidenceStore,
        email: str,
        requested_ip: str,
    ) -> tuple[str, str]:
        normalized_email = self.normalize_email(email)
        if not self.is_valid_email(normalized_email):
            raise ValueError("A valid email is required")

        # Lightweight per-email throttling to reduce abuse.
        if self.config.request_rate_limit_count > 0 and self.config.request_rate_limit_window_seconds > 0:
            since = self._now() - timedelta(seconds=self.config.request_rate_limit_window_seconds)
            recent_count = store.count_recent_magic_link_requests(
                email=normalized_email,
                since_iso=since.isoformat(),
            )
            if recent_count >= self.config.request_rate_limit_count:
                raise ValueError("Too many magic-link requests. Please try again shortly.")
            if requested_ip and self.config.request_rate_limit_ip_count > 0:
                recent_ip_count = store.count_recent_magic_link_requests_by_ip(
                    requested_ip=requested_ip,
                    since_iso=since.isoformat(),
                )
                if recent_ip_count >= self.config.request_rate_limit_ip_count:
                    raise ValueError("Too many magic-link requests. Please try again shortly.")

        token = secrets.token_urlsafe(32)
        token_hash = self.token_hash(token)
        expires_at = self._now() + timedelta(seconds=self.config.magic_link_ttl_seconds)
        store.create_magic_link(
            email=normalized_email,
            token_hash=token_hash,
            expires_at=expires_at.isoformat(),
            requested_ip=requested_ip,
        )
        return token, self._build_magic_link(token)

    def consume_magic_token(
        self,
        *,
        store: EvidenceStore,
        token: str,
        user_agent: str,
        ip_address: str,
    ) -> tuple[dict[str, str], str]:
        token_hash = self.token_hash(token)
        consumed = store.consume_magic_link(token_hash=token_hash, now_iso=self._now().isoformat())
        if consumed is None:
            raise ValueError("Magic link is invalid or expired")
        status = str(consumed.get("status", ""))
        email_for_event = self.normalize_email(str(consumed.get("email", "")))
        if status == "replayed":
            user = store.get_user_by_email(email_for_event)
            if user is not None:
                store.log_user_activity(
                    user_id=str(user["user_id"]),
                    activity_type="auth_verify_replayed",
                    endpoint="/api/auth/verify-link",
                    payload={},
                )
            raise ValueError("Magic link already used")
        if status == "expired":
            user = store.get_user_by_email(email_for_event)
            if user is not None:
                store.log_user_activity(
                    user_id=str(user["user_id"]),
                    activity_type="auth_verify_expired",
                    endpoint="/api/auth/verify-link",
                    payload={},
                )
            raise ValueError("Magic link expired")

        email = email_for_event
        if not email:
            raise ValueError("Magic link did not resolve a valid user")

        existing_user = store.get_user_by_email(email)
        if existing_user is None:
            existing_user = store.get_or_create_user(user_id=f"usr_{secrets.token_hex(8)}", email=email)

        session_token = secrets.token_urlsafe(48)
        session_hash = self.token_hash(session_token)
        session_expires_at = self._now() + timedelta(seconds=self.config.session_ttl_seconds)
        store.create_auth_session(
            user_id=str(existing_user["user_id"]),
            token_hash=session_hash,
            expires_at=session_expires_at.isoformat(),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return existing_user, session_token

    def resolve_session(
        self,
        *,
        store: EvidenceStore,
        session_token: str,
    ) -> dict[str, str] | None:
        if not session_token:
            return None
        return store.resolve_auth_session(
            token_hash=self.token_hash(session_token),
            now_iso=self._now().isoformat(),
        )

    def resolve_session_with_rotation(
        self,
        *,
        store: EvidenceStore,
        session_token: str,
        user_agent: str,
        ip_address: str,
    ) -> tuple[dict[str, str] | None, str | None]:
        user = self.resolve_session(store=store, session_token=session_token)
        if user is None:
            return None, None
        if self.config.session_renew_window_seconds <= 0:
            return user, None

        expires_at = store.get_auth_session_expiry(token_hash=self.token_hash(session_token))
        if not expires_at:
            return user, None
        try:
            expires_dt = datetime.fromisoformat(str(expires_at))
        except ValueError:
            return user, None

        seconds_remaining = (expires_dt - self._now()).total_seconds()
        if seconds_remaining > float(self.config.session_renew_window_seconds):
            return user, None

        new_token = secrets.token_urlsafe(48)
        new_hash = self.token_hash(new_token)
        new_expires_at = self._now() + timedelta(seconds=self.config.session_ttl_seconds)
        store.create_auth_session(
            user_id=str(user["user_id"]),
            token_hash=new_hash,
            expires_at=new_expires_at.isoformat(),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        store.revoke_auth_session(token_hash=self.token_hash(session_token))
        return user, new_token

    def revoke_session(self, *, store: EvidenceStore, session_token: str) -> None:
        if not session_token:
            return
        store.revoke_auth_session(token_hash=self.token_hash(session_token))

    def send_magic_link(self, *, email: str, magic_link: str) -> dict[str, object]:
        if self.config.dev_mode:
            return {"sent": True, "mode": "dev", "magic_link": magic_link}

        msg = EmailMessage()
        msg["Subject"] = "Your MTVL AI sign-in link"
        msg["From"] = self.config.smtp_from
        msg["To"] = email
        msg.set_content(
            "Use this secure sign-in link to access MTVL AI. "
            f"This link expires in {self.config.magic_link_ttl_seconds // 60} minutes.\n\n"
            f"{magic_link}\n"
        )

        if not self.config.smtp_host:
            raise ValueError("SMTP host is not configured")

        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=10) as smtp:
            if self.config.smtp_starttls:
                smtp.starttls()
            if self.config.smtp_user and self.config.smtp_password:
                smtp.login(self.config.smtp_user, self.config.smtp_password)
            smtp.send_message(msg)

        return {"sent": True, "mode": "smtp"}


def build_auth_config() -> AuthConfig:
    return AuthConfig(
        app_base_url=os.getenv("ALS_APP_BASE_URL", "http://localhost:8000"),
        magic_link_ttl_seconds=int(os.getenv("ALS_MAGIC_LINK_TTL_SECONDS", "900")),
        session_ttl_seconds=int(os.getenv("ALS_SESSION_TTL_SECONDS", "28800")),
        session_renew_window_seconds=int(os.getenv("ALS_SESSION_RENEW_WINDOW_SECONDS", "900")),
        cookie_name=os.getenv("ALS_AUTH_COOKIE_NAME", "als_session"),
        smtp_host=os.getenv("ALS_SMTP_HOST", ""),
        smtp_port=int(os.getenv("ALS_SMTP_PORT", "587")),
        smtp_user=os.getenv("ALS_SMTP_USER", ""),
        smtp_password=os.getenv("ALS_SMTP_PASSWORD", ""),
        smtp_from=os.getenv("ALS_SMTP_FROM", "no-reply@localhost"),
        smtp_starttls=os.getenv("ALS_SMTP_STARTTLS", "1").strip() not in {"0", "false", "False"},
        dev_mode=os.getenv("ALS_MAGIC_LINK_DEV_MODE", "1").strip() in {"1", "true", "True"},
        request_rate_limit_count=int(os.getenv("ALS_MAGIC_LINK_RATE_LIMIT_COUNT", "3")),
        request_rate_limit_window_seconds=int(os.getenv("ALS_MAGIC_LINK_RATE_LIMIT_WINDOW_SECONDS", "600")),
        request_rate_limit_ip_count=int(os.getenv("ALS_MAGIC_LINK_RATE_LIMIT_IP_COUNT", "10")),
        cookie_secure=os.getenv("ALS_COOKIE_SECURE", "0").strip() in {"1", "true", "True"},
        cookie_same_site=os.getenv("ALS_COOKIE_SAMESITE", "Lax").strip() or "Lax",
        cookie_http_only=os.getenv("ALS_COOKIE_HTTPONLY", "1").strip() not in {"0", "false", "False"},
        cookie_path=os.getenv("ALS_COOKIE_PATH", "/").strip() or "/",
        cookie_domain=os.getenv("ALS_COOKIE_DOMAIN", "").strip(),
    )
