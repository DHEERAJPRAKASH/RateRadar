"""Provision the default ingest user (idempotent).

Run on boot before seeding so the dashboard can auto-login and obtain a bearer
token for the ingest endpoint. Credentials come from
``DEFAULT_INGEST_USERNAME`` / ``DEFAULT_INGEST_PASSWORD`` (settings/env).
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

from common.logging import get_logger

log = get_logger("auth")


class Command(BaseCommand):
    help = "Create the default ingest user and token if they do not exist."

    def handle(self, *args, **options) -> None:
        username = settings.DEFAULT_INGEST_USERNAME
        password = settings.DEFAULT_INGEST_PASSWORD

        user, created = User.objects.get_or_create(username=username)
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
        token, _ = Token.objects.get_or_create(user=user)

        log.info(
            "auth.default_user",
            extra={"username": username, "was_created": created},
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Default user '{username}' {'created' if created else 'present'}."
            )
        )
