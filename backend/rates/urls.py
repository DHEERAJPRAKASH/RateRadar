"""Rate API routes. Endpoints are added in Phase 2."""

from django.urls import path

from rates import views

urlpatterns: list[path] = [
    path("latest/", views.latest_rates, name="latest-rates"),
    path("history/", views.rate_history, name="rate-history"),
    path("browse/", views.browse_rates, name="browse-rates"),
    path("quarantined/", views.quarantined_rows, name="quarantined-rows"),
    path("meta/", views.rate_meta, name="rate-meta"),
    path("ingest/", views.ingest, name="ingest"),
]
