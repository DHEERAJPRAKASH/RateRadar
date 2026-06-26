"""Rate API routes. Endpoints are added in Phase 2."""

from django.urls import path

from rates import views

urlpatterns: list[path] = [
    path("latest/", views.latest_rates, name="latest-rates"),
    path("history/", views.rate_history, name="rate-history"),
    path("ingest/", views.ingest, name="ingest"),
]
