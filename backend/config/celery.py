"""Celery application bootstrap.

The worker and beat scheduler both import this module. Task modules are
auto-discovered from installed apps (e.g. ``ingestion.tasks``).
"""
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("rateradar")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):  # pragma: no cover - sanity check only
    print(f"Request: {self.request!r}")
