from django.contrib import admin
from django.urls import include, path

from common.health import health_view
from rates import auth as auth_views
from rates import views as rate_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health_view, name="health"),
    path("auth/signup/", auth_views.signup, name="auth-signup"),
    path("auth/login/", auth_views.login, name="auth-login"),
    path("ingestion/status/", rate_views.ingestion_status, name="ingestion-status"),
    path("rates/", include("rates.urls")),
]
