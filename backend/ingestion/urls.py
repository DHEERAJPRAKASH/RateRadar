"""Ingestion API routes."""

from django.urls import path

from ingestion import views

urlpatterns: list[path] = [
    path("status/", views.IngestionStatusView.as_view(), name="ingestion-status"),
]
