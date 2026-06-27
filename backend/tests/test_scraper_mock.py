"""Mocked-HTTP tests for the scraper/ingestion worker.

Required by the brief: mock the HTTP call and assert the parsed output
matches a known fixture, and prove failures are captured (not silent crashes).
No real network is touched — ``responses`` intercepts the requests layer.
"""

import datetime as _dt

import pytest
import requests
import responses

from ingestion.fetchers import (
    FetchHTTPError,
    FetchTimeout,
    HttpRateFetcher,
    PartialResponseError,
)
from ingestion.parsers import ParseError, parse_rate_payload

_SOURCE_URL = "https://example.com/rates/savings"

# Known fixture: the exact JSON body a source would return.
_FIXTURE_BODY = """
[
  {
    "provider": "HSBC",
    "rate_type": "savings_1yr_fixed",
    "rate_value": 4.5,
    "effective_date": "2026-06-27",
    "ingestion_ts": "2026-06-27T08:00:00",
    "currency": "USD",
    "source_url": "https://example.com/rates/savings",
    "raw_response_id": "abc-123"
  },
  {
    "provider": "Chase",
    "rate_type": "mortgage_30yr_fixed",
    "rate_value": 6.8,
    "effective_date": "2026-06-27",
    "ingestion_ts": "2026-06-27T08:00:00",
    "currency": "USD",
    "source_url": "https://example.com/rates/savings",
    "raw_response_id": "abc-124"
  }
]
"""

# The parsed output we expect for the fixture above.
_EXPECTED_PARSED = [
    {
        "provider": "HSBC",
        "rate_type": "savings_1yr_fixed",
        "rate_value": 4.5,
        "effective_date": "2026-06-27",
        "ingestion_ts": "2026-06-27T08:00:00",
        "currency": "USD",
        "source_url": "https://example.com/rates/savings",
        "raw_response_id": "abc-123",
    },
    {
        "provider": "Chase",
        "rate_type": "mortgage_30yr_fixed",
        "rate_value": 6.8,
        "effective_date": "2026-06-27",
        "ingestion_ts": "2026-06-27T08:00:00",
        "currency": "USD",
        "source_url": "https://example.com/rates/savings",
        "raw_response_id": "abc-124",
    },
]


@responses.activate
def test_fetch_and_parse_matches_fixture():
    """Mocked HTTP body -> fetch -> parse equals the known fixture."""
    responses.add(
        responses.GET,
        _SOURCE_URL,
        body=_FIXTURE_BODY,
        status=200,
        content_type="application/json",
    )

    result = HttpRateFetcher().fetch(_SOURCE_URL)
    parsed = parse_rate_payload(result["body"])

    assert parsed == _EXPECTED_PARSED


@responses.activate
def test_fetch_timeout_raises_fetch_timeout():
    """A request timeout surfaces as a typed FetchTimeout, not a raw crash."""
    responses.add(
        responses.GET,
        _SOURCE_URL,
        body=requests.exceptions.Timeout("connection timed out"),
    )

    with pytest.raises(FetchTimeout):
        HttpRateFetcher().fetch(_SOURCE_URL)


@responses.activate
def test_fetch_http_error_raises_fetch_http_error():
    """A 4xx response surfaces as FetchHTTPError carrying the status code."""
    responses.add(responses.GET, _SOURCE_URL, status=404)

    with pytest.raises(FetchHTTPError) as exc_info:
        HttpRateFetcher().fetch(_SOURCE_URL)

    assert exc_info.value.status_code == 404


@responses.activate
def test_fetch_empty_body_raises_partial_response():
    """An empty body is treated as a partial/truncated response."""
    responses.add(responses.GET, _SOURCE_URL, body="", status=200)

    with pytest.raises(PartialResponseError):
        HttpRateFetcher().fetch(_SOURCE_URL)


def test_parse_invalid_json_raises_parse_error():
    """Non-JSON payloads raise ParseError so the row can be quarantined/replayed."""
    with pytest.raises(ParseError):
        parse_rate_payload("not-json-at-all")


def test_parse_missing_keys_raises_parse_error():
    """A row missing required keys is rejected by the strict parser."""
    body = '[{"provider": "HSBC"}]'
    with pytest.raises(ParseError):
        parse_rate_payload(body)


@pytest.mark.django_db
def test_scrape_rates_quarantines_parse_failure_without_crashing(mocker):
    """When a source returns unparseable data, scrape_rates records a FAILED
    RawResponse and does not raise (worker never crashes silently)."""
    from ingestion import tasks
    from rates.models import RawResponse

    class _StubFetcher:
        def fetch(self, url):
            return {"url": url, "status_code": 200, "body": "garbage-not-json"}

    mocker.patch.object(tasks, "HttpRateFetcher", return_value=_StubFetcher())

    tasks.scrape_rates()

    failed = RawResponse.objects.filter(status=RawResponse.Status.FAILED)
    assert failed.count() == len(tasks._SCRAPING_SOURCES)
    assert failed.first().parse_error


@pytest.mark.django_db
def test_scrape_rates_ingests_clean_rows_from_mocked_source(mocker):
    """A well-formed mocked source body flows fetch -> parse -> clean -> upsert."""
    from ingestion import tasks
    from rates.models import Rate

    class _StubFetcher:
        def fetch(self, url):
            return {"url": url, "status_code": 200, "body": _FIXTURE_BODY}

    mocker.patch.object(tasks, "HttpRateFetcher", return_value=_StubFetcher())

    tasks.scrape_rates()

    assert Rate.objects.filter(rate_type="savings_1yr_fixed").exists()
    assert Rate.objects.filter(rate_type="mortgage_30yr_fixed").exists()
