"""Authentication for the ingest endpoint.

Implements requirement 2B: the ingest endpoint requires a *bearer* token,
enforced through DRF's authentication classes (no external auth service). GET
endpoints stay public.

- ``BearerTokenAuthentication`` is DRF's ``TokenAuthentication`` with the
  ``Bearer`` keyword (the default keyword is ``Token``).
- ``signup`` / ``login`` issue and return a token tied to a Django user, so the
  dashboard can obtain a bearer token at runtime instead of shipping a static
  secret in the browser bundle.
"""

from __future__ import annotations

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from common.logging import get_logger

log = get_logger("auth")

MIN_PASSWORD_LENGTH = 8


class BearerTokenAuthentication(TokenAuthentication):
    """DRF token auth that expects ``Authorization: Bearer <token>``."""

    keyword = "Bearer"


@api_view(["POST"])
@permission_classes([AllowAny])
def signup(request) -> Response:
    """Create a user and return a bearer token.

    Body: ``{"username": str, "password": str}``. Idempotent-ish: a duplicate
    username is rejected with 400 rather than overwriting an existing account.
    """
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""

    if not username or not password:
        return Response(
            {"error": "username and password are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(password) < MIN_PASSWORD_LENGTH:
        return Response(
            {"error": f"password must be at least {MIN_PASSWORD_LENGTH} characters"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if User.objects.filter(username=username).exists():
        return Response(
            {"error": "username already exists"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = User.objects.create_user(username=username, password=password)
    token, _ = Token.objects.get_or_create(user=user)
    log.info("auth.signup", extra={"username": username})
    return Response(
        {"token": token.key, "username": user.username},
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request) -> Response:
    """Validate credentials and return the user's bearer token."""
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""

    user = authenticate(username=username, password=password)
    if user is None:
        log.info("auth.login.failed", extra={"username": username})
        return Response(
            {"error": "invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    token, _ = Token.objects.get_or_create(user=user)
    log.info("auth.login.ok", extra={"username": user.username})
    return Response({"token": token.key, "username": user.username})
