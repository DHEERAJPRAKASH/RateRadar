"""Class-based API views for the ingestion app."""

from __future__ import annotations

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.services.loader import get_ingestion_status


class IngestionStatusView(APIView):
    """GET /ingestion/status — live seed progress."""

    permission_classes = [AllowAny]

    def get(self, request) -> Response:
        return Response(get_ingestion_status())
