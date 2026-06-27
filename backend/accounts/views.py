"""Class-based auth API views."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.services import AuthError, AuthService


class SignupView(APIView):
    """POST /auth/signup — create user and return bearer token."""

    permission_classes = [AllowAny]

    def post(self, request) -> Response:
        result = AuthService.signup(request.data)
        if isinstance(result, AuthError):
            return Response({"error": result.message}, status=result.status_code)
        return Response(
            {"token": result.token, "username": result.username},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """POST /auth/login — validate credentials and return bearer token."""

    permission_classes = [AllowAny]

    def post(self, request) -> Response:
        result = AuthService.login(request.data)
        if isinstance(result, AuthError):
            return Response({"error": result.message}, status=result.status_code)
        return Response({"token": result.token, "username": result.username})
