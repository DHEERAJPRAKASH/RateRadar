"""Authentication business logic."""

from __future__ import annotations

from dataclasses import dataclass

import pydash
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from common.logging import get_logger

log = get_logger("auth")

MIN_PASSWORD_LENGTH = 8


@dataclass(frozen=True)
class AuthResult:
    token: str
    username: str


@dataclass(frozen=True)
class AuthError:
    message: str
    status_code: int


class AuthService:
    """User signup/login — issues DRF bearer tokens."""

    @classmethod
    def signup(cls, data: dict) -> AuthResult | AuthError:
        username = pydash.get(data, "username", "").strip()
        password = pydash.get(data, "password", "")

        if not username or not password:
            return AuthError("username and password are required", 400)
        if len(password) < MIN_PASSWORD_LENGTH:
            return AuthError(
                f"password must be at least {MIN_PASSWORD_LENGTH} characters", 400
            )
        if User.objects.filter(username=username).exists():
            return AuthError("username already exists", 400)

        user = User.objects.create_user(username=username, password=password)
        token, _ = Token.objects.get_or_create(user=user)
        log.info("auth.signup", extra={"username": username})
        return AuthResult(token=token.key, username=user.username)

    @classmethod
    def login(cls, data: dict) -> AuthResult | AuthError:
        username = pydash.get(data, "username", "").strip()
        password = pydash.get(data, "password", "")

        user = authenticate(username=username, password=password)
        if user is None:
            log.info("auth.login.failed", extra={"username": username})
            return AuthError("invalid credentials", 401)

        token, _ = Token.objects.get_or_create(user=user)
        log.info("auth.login.ok", extra={"username": user.username})
        return AuthResult(token=token.key, username=user.username)

    @classmethod
    def ensure_default_user(cls, username: str, password: str) -> bool:
        """Create the default ingest user + token if missing. Returns True if created."""
        user, created = User.objects.get_or_create(username=username)
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
        Token.objects.get_or_create(user=user)
        log.info("auth.default_user", extra={"username": username, "was_created": created})
        return created
