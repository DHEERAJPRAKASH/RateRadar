from django.contrib import admin
from django.urls import include, path

from common.health import health_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health_view, name="health"),
    path("rates/", include("rates.urls")),
]
