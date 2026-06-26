"""HTTP fetcher with timeout, retry, and typed exceptions.

Source-agnostic: fetches a URL and returns the raw response body. Failures
are captured as typed exceptions, never silent crashes.
"""
from __future__ import annotations

from typing import TypedDict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class FetchError(Exception):
    """Base class for fetch errors."""


class FetchTimeout(FetchError):
    """Request timed out."""


class FetchHTTPError(FetchError):
    """HTTP error (4xx/5xx)."""

    def __init__(self, status_code: int, url: str) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(f"HTTP {status_code} from {url}")


class PartialResponseError(FetchError):
    """Response was incomplete or truncated."""


class FetchResult(TypedDict):
    url: str
    status_code: int
    body: str


class HttpRateFetcher:
    """Fetch rate data from HTTP sources with timeout and retry."""

    def __init__(
        self,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def fetch(self, url: str) -> FetchResult:
        """Fetch a URL and return the response body.

        Raises:
            FetchTimeout: if the request times out.
            FetchHTTPError: if the response status is 4xx/5xx.
            PartialResponseError: if the response is incomplete.
            FetchError: for other network errors.
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            body = response.text
            if not body:
                raise PartialResponseError(f"Empty response from {url}")
            return FetchResult(url=url, status_code=response.status_code, body=body)
        except requests.Timeout as exc:
            raise FetchTimeout(f"Timeout after {self.timeout}s from {url}") from exc
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else 0
            raise FetchHTTPError(status_code, url) from exc
        except requests.RequestException as exc:
            raise FetchError(f"Request failed for {url}: {exc}") from exc
