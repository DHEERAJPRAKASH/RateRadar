"""DRF serializers for the rates API."""
from __future__ import annotations

from rest_framework import serializers

from rates.models import Rate


class RateSerializer(serializers.ModelSerializer):
    """Read-only serializer for Rate records."""

    provider_slug = serializers.CharField(source="provider.slug", read_only=True)
    provider_name = serializers.CharField(source="provider.name", read_only=True)

    class Meta:
        model = Rate
        fields = [
            "id",
            "provider_slug",
            "provider_name",
            "rate_type",
            "rate_value",
            "currency",
            "effective_date",
            "ingestion_ts",
            "source_url",
        ]
        read_only_fields = fields


class IngestSerializer(serializers.Serializer):
    """Serializer for POST /rates/ingest payload."""

    data = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
        help_text="Array of raw rate dicts (same schema as parquet).",
    )
