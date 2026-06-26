"""Shared pytest configuration."""
import os
import sys

# Add the backend directory to the path so imports work.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()
