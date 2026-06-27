from django.contrib import admin
from django.urls import include, path

from common.health import health_view
from rates import views as rate_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health_view, name="health"),
    path("ingestion/status/", rate_views.ingestion_status, name="ingestion-status"),
    path("rates/", include("rates.urls")),
]
