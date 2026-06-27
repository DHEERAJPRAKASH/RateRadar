"""Celery application bootstrap.

The worker and beat scheduler both import this module. Task modules are
auto-discovered from installed apps (e.g. ``ingestion.services.tasks``).
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("rateradar")
app.config_from_object("django.conf:settings", namespace="CELERY")
# Tasks live in ``<app>.services.tasks``. A dotted ``related_name`` makes
# Celery's autodiscover crash on apps without a ``services`` package
# (e.g. django.contrib.admin), so scope discovery to the package that has tasks.
app.autodiscover_tasks(["ingestion.services"])


@app.task(bind=True, ignore_result=True)
def debug_task(self):  # pragma: no cover - sanity check only
    print(f"Request: {self.request!r}")
