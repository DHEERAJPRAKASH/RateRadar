from django.contrib import admin
from django.urls import include, path

from common.health import HealthView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", HealthView.as_view(), name="health"),
    path("auth/", include("accounts.urls")),
    path("ingestion/", include("ingestion.urls")),
    path("rates/", include("rates.urls")),
]
