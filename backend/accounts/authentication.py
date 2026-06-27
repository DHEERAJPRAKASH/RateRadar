"""DRF authentication classes."""

from __future__ import annotations

from rest_framework.authentication import TokenAuthentication


class BearerTokenAuthentication(TokenAuthentication):
    """Token auth that expects ``Authorization: Bearer <token>``."""

    keyword = "Bearer"
