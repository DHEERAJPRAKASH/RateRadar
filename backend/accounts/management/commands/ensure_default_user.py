"""Provision the default ingest user (idempotent).

Run on boot before seeding so the dashboard can auto-login and obtain a bearer
token for the ingest endpoint. Credentials come from
``DEFAULT_INGEST_USERNAME`` / ``DEFAULT_INGEST_PASSWORD`` (settings/env).
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from accounts.services import AuthService


class Command(BaseCommand):
    help = "Create the default ingest user and token if they do not exist."

    def handle(self, *args, **options) -> None:
        username = settings.DEFAULT_INGEST_USERNAME
        password = settings.DEFAULT_INGEST_PASSWORD

        created = AuthService.ensure_default_user(username, password)
        self.stdout.write(
            self.style.SUCCESS(
                f"Default user '{username}' {'created' if created else 'present'}."
            )
        )
