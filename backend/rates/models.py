"""Persistence model for interest-rate data.

Three tables:
- ``Provider``  — the small dimension of rate publishers (banks). The ``slug`` is
  the canonicalization/dedup key (e.g. ``hsbc``/``Hsbc``/``HSBC`` → ``hsbc``).
- ``RawResponse`` — the raw payload captured at ingestion time for auditing and
  replay. Failed parses are stored with ``status=FAILED`` and can be re-processed.
- ``Rate``      — the cleaned fact table the API serves.

See ``schema.md`` for the index/query rationale and the natural-key choice.
"""

from __future__ import annotations

from django.db import models


class Provider(models.Model):
    """A rate publisher (e.g. a bank). Low cardinality dimension table.

    The ``slug`` is the canonicalization key used during ingestion to collapse
    dirty variants (e.g. ``hsbc``/``Hsbc``/``HSBC`` → ``hsbc``). The ``name``
    holds the curated display name.
    """

    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class RawResponse(models.Model):
    """Raw payload captured at ingestion time for auditing and replay.

    A failed parse is stored with ``status=FAILED`` and the error text so it can
    be re-processed later via ``manage.py replay_failed`` without re-fetching.
    """

    class Status(models.TextChoices):
        PARSED = "parsed", "Parsed"
        FAILED = "failed", "Failed"

    external_id = models.CharField(
        max_length=128,
        unique=True,
        null=True,
        blank=True,
        help_text="Source-provided id (parquet raw_response_id), if any.",
    )
    source_url = models.URLField(max_length=512, blank=True, default="")
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PARSED
    )
    parse_error = models.TextField(null=True, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"], name="ix_raw_status"),
            models.Index(fields=["created_at"], name="ix_raw_created_at"),
        ]

    def __str__(self) -> str:
        return f"RawResponse<{self.external_id or self.pk} {self.status}>"


class Rate(models.Model):
    """A cleaned, queryable rate observation."""

    provider = models.ForeignKey(
        Provider, on_delete=models.PROTECT, related_name="rates"
    )
    rate_type = models.CharField(max_length=64)
    rate_value = models.DecimalField(max_digits=7, decimal_places=4)
    currency = models.CharField(max_length=8, default="USD")
    effective_date = models.DateField()
    # Source-claimed ingestion timestamp (from the parquet/webhook payload).
    ingestion_ts = models.DateTimeField()
    source_url = models.URLField(max_length=512, blank=True, default="")
    raw_response = models.ForeignKey(
        RawResponse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rates",
    )
    # Our own DB write time — distinct from the source ``ingestion_ts``.
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Natural key: at most one observation per provider/type/effective day.
            # Re-ingests update the value (correction / latest-wins).
            models.UniqueConstraint(
                fields=["provider", "rate_type", "effective_date"],
                name="uq_rate_natural_key",
            )
        ]
        indexes = [
            # Latest per provider with optional type filter, plus provider+type history.
            models.Index(
                fields=["provider", "rate_type", "-effective_date", "-ingestion_ts"],
                name="ix_rate_provider_type_eff",
            ),
            # Latest per provider without type filter (DISTINCT ON).
            models.Index(
                fields=["provider", "-effective_date", "-ingestion_ts"],
                name="ix_rate_provider_eff",
            ),
            # Rate change over last 30 days for a given type.
            models.Index(
                fields=["rate_type", "effective_date"], name="ix_rate_type_eff"
            ),
            # Records ingested in a 24-hour window.
            models.Index(fields=["ingestion_ts"], name="ix_rate_ingestion_ts"),
        ]
        ordering = ["-effective_date", "-ingestion_ts"]

    def __str__(self) -> str:
        return f"{self.provider.slug} {self.rate_type} {self.rate_value}% {self.effective_date}"
