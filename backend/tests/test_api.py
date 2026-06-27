"""API tests for the rates endpoints."""

import datetime as _dt
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from rates.models import Provider, Rate, RawResponse


@pytest.fixture(autouse=True)
def _clear_cache():
    """Tests share Redis with the running app; clear it so cached real
    responses do not leak into assertions."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def sample_provider():
    return Provider.objects.create(name="Test Bank", slug="test-bank")


@pytest.fixture
def sample_rates(sample_provider):
    """Create sample rates for testing."""
    today = _dt.date.today()
    yesterday = today - _dt.timedelta(days=1)
    two_days_ago = today - _dt.timedelta(days=2)

    rates = [
        Rate.objects.create(
            provider=sample_provider,
            rate_type="savings_1yr_fixed",
            rate_value=Decimal("4.5"),
            currency="USD",
            effective_date=today,
            ingestion_ts=_dt.datetime.now(),
        ),
        Rate.objects.create(
            provider=sample_provider,
            rate_type="savings_1yr_fixed",
            rate_value=Decimal("4.3"),
            currency="USD",
            effective_date=yesterday,
            ingestion_ts=_dt.datetime.now(),
        ),
        Rate.objects.create(
            provider=sample_provider,
            rate_type="mortgage_30yr_fixed",
            rate_value=Decimal("6.8"),
            currency="USD",
            effective_date=today,
            ingestion_ts=_dt.datetime.now(),
        ),
    ]
    return rates


@pytest.mark.django_db
def test_latest_rates_no_filter(client, sample_rates):
    """GET /rates/latest returns latest rate per provider."""
    response = client.get("/rates/latest/")
    assert response.status_code == 200
    data = response.json()
    # DISTINCT ON (provider) returns one row per provider regardless of type.
    assert len(data) == 1
    assert data[0]["provider_slug"] == "test-bank"


@pytest.mark.django_db
def test_latest_rates_with_type_filter(client, sample_rates):
    """GET /rates/latest?rate_type=savings_1yr_fixed filters by type."""
    response = client.get("/rates/latest/?rate_type=savings_1yr_fixed")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["rate_type"] == "savings_1yr_fixed"
    assert data[0]["rate_value"] == "4.5000"


@pytest.mark.django_db
def test_latest_rates_caching(client, sample_rates):
    """GET /rates/latest caches the response for 60s."""
    # First call
    response1 = client.get("/rates/latest/")
    assert response1.status_code == 200

    # Second call should hit cache
    response2 = client.get("/rates/latest/")
    assert response2.status_code == 200
    assert response1.json() == response2.json()


def test_rate_history_missing_params(client):
    """GET /rates/history requires provider and rate_type."""
    response = client.get("/rates/history/")
    assert response.status_code == 400
    assert "error" in response.json()


@pytest.mark.django_db
def test_rate_history_success(client, sample_provider, sample_rates):
    """GET /rates/history returns historical rates for provider/type."""
    response = client.get(
        f"/rates/history/?provider=test-bank&rate_type=savings_1yr_fixed"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # Two rates for this provider/type
    assert data[0]["rate_type"] == "savings_1yr_fixed"
    assert data[0]["provider_slug"] == "test-bank"


@pytest.mark.django_db
def test_rate_history_caching(client, sample_provider, sample_rates):
    """GET /rates/history caches the response for 60s."""
    response1 = client.get(
        f"/rates/history/?provider=test-bank&rate_type=savings_1yr_fixed"
    )
    assert response1.status_code == 200

    response2 = client.get(
        f"/rates/history/?provider=test-bank&rate_type=savings_1yr_fixed"
    )
    assert response2.status_code == 200
    assert response1.json() == response2.json()


def test_ingest_missing_auth(client):
    """POST /rates/ingest requires bearer token."""
    response = client.post(
        "/rates/ingest/",
        {"data": []},
        content_type="application/json",
    )
    assert response.status_code == 401


def test_ingest_invalid_token(client):
    """POST /rates/ingest rejects invalid bearer token."""
    response = client.post(
        "/rates/ingest/",
        {"data": []},
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer invalid-token",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_ingest_success(client, sample_provider, settings):
    """POST /rates/ingest ingests valid data and returns counts."""
    settings.INGEST_API_TOKEN = "test-token"
    payload = {
        "data": [
            {
                "provider": "test-bank",
                "rate_type": "savings_1yr_fixed",
                "rate_value": 4.7,
                "currency": "USD",
                "effective_date": _dt.date.today().isoformat(),
                "ingestion_ts": _dt.datetime.now().isoformat(),
            }
        ]
    }
    response = client.post(
        "/rates/ingest/",
        payload,
        format="json",
        HTTP_AUTHORIZATION="Bearer test-token",
    )
    assert response.status_code == 201
    data = response.json()
    assert "inserted" in data
    assert data["inserted"] >= 1


@pytest.mark.django_db
def test_ingest_invalid_data_quarantined(client, settings):
    """POST /rates/ingest quarantines invalid rows."""
    settings.INGEST_API_TOKEN = "test-token"
    payload = {
        "data": [
            {
                "provider": "test-bank",
                "rate_type": "savings_1yr_fixed",
                "rate_value": None,  # Invalid
                "currency": "USD",
                "effective_date": _dt.date.today().isoformat(),
                "ingestion_ts": _dt.datetime.now().isoformat(),
            }
        ]
    }
    response = client.post(
        "/rates/ingest/",
        payload,
        format="json",
        HTTP_AUTHORIZATION="Bearer test-token",
    )
    assert response.status_code == 201
    data = response.json()
    assert "quarantined" in data
    assert "null rate_value" in str(data["quarantined"])


# --- browse / history window / quarantine / meta / status -------------------


def _make_rate(provider, rate_type, value, eff_date):
    return Rate.objects.create(
        provider=provider,
        rate_type=rate_type,
        rate_value=Decimal(str(value)),
        currency="USD",
        effective_date=eff_date,
        ingestion_ts=timezone.now(),
    )


@pytest.mark.django_db
def test_browse_rates_filters_by_type_and_is_paginated(client, sample_provider):
    today = _dt.date.today()
    _make_rate(sample_provider, "savings_1yr_fixed", 4.5, today)
    _make_rate(sample_provider, "mortgage_30yr_fixed", 6.8, today)

    response = client.get("/rates/browse/?rate_type=savings_1yr_fixed")

    assert response.status_code == 200
    body = response.json()
    assert "results" in body and "count" in body
    assert all(r["rate_type"] == "savings_1yr_fixed" for r in body["results"])
    assert body["count"] == 1


@pytest.mark.django_db
def test_browse_rates_filters_by_date_window(client, sample_provider):
    today = _dt.date.today()
    old = today - _dt.timedelta(days=90)
    _make_rate(sample_provider, "savings_1yr_fixed", 4.5, today)
    _make_rate(sample_provider, "savings_1yr_fixed", 4.0, old)

    response = client.get(
        f"/rates/browse/?from={(today - _dt.timedelta(days=7)).isoformat()}"
    )

    assert response.status_code == 200
    dates = [r["effective_date"] for r in response.json()["results"]]
    assert today.isoformat() in dates
    assert old.isoformat() not in dates


@pytest.mark.django_db
def test_history_respects_from_to_window(client, sample_provider):
    today = _dt.date.today()
    inside = today - _dt.timedelta(days=10)
    outside = today - _dt.timedelta(days=200)
    _make_rate(sample_provider, "savings_1yr_fixed", 4.5, inside)
    _make_rate(sample_provider, "savings_1yr_fixed", 3.9, outside)

    response = client.get(
        "/rates/history/?provider=test-bank&rate_type=savings_1yr_fixed"
        f"&from={(today - _dt.timedelta(days=30)).isoformat()}&to={today.isoformat()}"
    )

    assert response.status_code == 200
    dates = [r["effective_date"] for r in response.json()]
    assert inside.isoformat() in dates
    assert outside.isoformat() not in dates


@pytest.mark.django_db
def test_quarantined_rows_returns_reason(client):
    RawResponse.objects.create(
        external_id="bad-1",
        source_url="https://example.com/x",
        payload={"provider": "HSBC", "rate_value": None},
        status=RawResponse.Status.FAILED,
        parse_error="null rate_value",
    )

    response = client.get("/rates/quarantined/")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    row = body["results"][0]
    assert row["reason"] == "null rate_value"
    assert row["payload"]["provider"] == "HSBC"


@pytest.mark.django_db
def test_rate_meta_lists_types_and_providers(client, sample_provider):
    _make_rate(sample_provider, "savings_1yr_fixed", 4.5, _dt.date.today())

    response = client.get("/rates/meta/")

    assert response.status_code == 200
    body = response.json()
    assert "savings_1yr_fixed" in body["rate_types"]
    assert any(p["slug"] == "test-bank" for p in body["providers"])


def test_ingestion_status_defaults_to_idle(client):
    response = client.get("/ingestion/status/")
    assert response.status_code == 200
    assert response.json()["state"] == "idle"


@pytest.mark.django_db
def test_quarantined_payload_with_date_is_json_safe():
    """A quarantined parquet row carrying date/datetime objects must persist
    (JSONField cannot serialize raw date objects)."""
    from ingestion.cleaning import Quarantine
    from ingestion.loader import ingest_records

    raw = {
        "provider": "HSBC",
        "rate_value": None,
        "effective_date": _dt.date.today(),
        "ingestion_ts": _dt.datetime.now(),
    }
    result = ingest_records([], [(Quarantine("null rate_value"), raw)])

    assert sum(result.quarantined.values()) == 1
    stored = RawResponse.objects.get(status=RawResponse.Status.FAILED)
    assert stored.payload["effective_date"] == _dt.date.today().isoformat()


@pytest.mark.django_db
def test_seed_full_data_skips_when_rates_exist(sample_provider):
    """The boot seed task is a no-op (marks complete) if data already exists."""
    from ingestion.loader import get_ingestion_status
    from ingestion.tasks import seed_full_data

    _make_rate(sample_provider, "savings_1yr_fixed", 4.5, _dt.date.today())

    seed_full_data()

    assert get_ingestion_status()["state"] == "complete"
