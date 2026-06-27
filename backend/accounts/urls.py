"""Auth API routes."""

from django.urls import path

from accounts import views

urlpatterns: list[path] = [
    path("signup/", views.SignupView.as_view(), name="auth-signup"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
]
