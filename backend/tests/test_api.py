"""API tests for the rates endpoints."""

import datetime as _dt
from decimal import Decimal

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from rates.models import Provider, Rate


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
    assert (
        len(data) == 2
    )  # Two providers (if we had more), but here 1 provider with 2 types
    # Actually, with one provider, we get 2 rows (one per type).
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
    response1 = client.get("/api/rates/latest/")
    assert response1.status_code == 200

    # Second call should hit cache
    response2 = client.get("/api/rates/latest/")
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
        content_type="application/json",
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
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer test-token",
    )
    assert response.status_code == 201
    data = response.json()
    assert "quarantined" in data
    assert "null rate_value" in str(data["quarantined"])
