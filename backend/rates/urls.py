"""Rate API routes."""

from django.urls import path

from rates.views import (
    BrowseRatesView,
    IngestView,
    LatestRatesView,
    QuarantinedRowsView,
    RateHistoryView,
    RateMetaView,
)

urlpatterns: list[path] = [
    path("latest/", LatestRatesView.as_view(), name="latest-rates"),
    path("history/", RateHistoryView.as_view(), name="rate-history"),
    path("browse/", BrowseRatesView.as_view(), name="browse-rates"),
    path("quarantined/", QuarantinedRowsView.as_view(), name="quarantined-rows"),
    path("meta/", RateMetaView.as_view(), name="rate-meta"),
    path("ingest/", IngestView.as_view(), name="ingest"),
]
