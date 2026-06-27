"""Class-based API views for the rates app."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import BearerTokenAuthentication
from rates.pagination import DefaultPagination
from rates.serializers import IngestSerializer, QuarantineSerializer, RateSerializer
from rates.services import IngestService, RateQueryService


class LatestRatesView(APIView):
    """GET /rates/latest — latest rate per provider."""

    permission_classes = [AllowAny]

    def get(self, request) -> Response:
        rate_type = request.query_params.get("rate_type")
        data, _ = RateQueryService.get_latest_rates(rate_type)
        return Response(data)


class RateHistoryView(APIView):
    """GET /rates/history — historical rates for a provider/type."""

    permission_classes = [AllowAny]

    def get(self, request) -> Response:
        provider_slug = request.query_params.get("provider")
        rate_type = request.query_params.get("rate_type")
        if not provider_slug or not rate_type:
            return Response(
                {"error": "provider and rate_type query params are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        date_from, date_to = RateQueryService.history_date_window(
            request.query_params.get("from"),
            request.query_params.get("to"),
        )
        data, _ = RateQueryService.get_history(
            provider_slug, rate_type, date_from, date_to
        )
        return Response(data)


class BrowseRatesView(APIView):
    """GET /rates/browse — paginated browse with optional filters."""

    permission_classes = [AllowAny]

    def get(self, request) -> Response:
        qs = RateQueryService.browse_queryset(request.query_params)
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = RateSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class QuarantinedRowsView(APIView):
    """GET /rates/quarantined — failed raw responses."""

    permission_classes = [AllowAny]

    def get(self, request) -> Response:
        qs = RateQueryService.quarantined_queryset()
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = QuarantineSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class RateMetaView(APIView):
    """GET /rates/meta — distinct rate types and providers."""

    permission_classes = [AllowAny]

    def get(self, request) -> Response:
        return Response(RateQueryService.get_meta())


class IngestView(APIView):
    """POST /rates/ingest — ingest rate data (bearer token required)."""

    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        serializer = IngestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        result = IngestService.ingest_payload(serializer.validated_data["data"])
        return Response(result, status=status.HTTP_201_CREATED)
