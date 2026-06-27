"""Django settings for the Rate-Tracker project.

All configuration is environment-driven and fails fast (see ``common.env``).
There are no secrets baked into this file.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from common.env import get_csv_env, get_env, get_required_env

# Load .env for local development (Docker uses env_file: .env).
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core security / debug -------------------------------------------------
SECRET_KEY = get_required_env("DJANGO_SECRET_KEY")
DEBUG = get_env("DJANGO_DEBUG", False, cast=bool)
ALLOWED_HOSTS = get_csv_env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,web")

# --- Applications ----------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "django_celery_beat",
    # Local
    "common",
    "accounts",
    "rates",
    "ingestion",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Observability: log requests + warn on slow DB queries (>200ms).
    "common.middleware.RequestTimingMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database --------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": get_required_env("POSTGRES_DB"),
        "USER": get_required_env("POSTGRES_USER"),
        "PASSWORD": get_required_env("POSTGRES_PASSWORD"),
        "HOST": get_env("POSTGRES_HOST", "db"),
        "PORT": get_env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": get_env("DB_CONN_MAX_AGE", 60, cast=int),
    }
}

# --- Cache (Redis via django-redis) ---------------------------------------
REDIS_URL = get_env("REDIS_URL", "redis://redis:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": "rateradar",
    }
}

# --- Celery ----------------------------------------------------------------
CELERY_BROKER_URL = get_env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = get_env("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = "UTC"

# How often the scheduled scrape runs (seconds). Wired into beat on startup.
SCRAPE_INTERVAL_SECONDS = get_env("SCRAPE_INTERVAL_SECONDS", 300, cast=int)

# Celery Beat schedule (periodic tasks).
CELERY_BEAT_SCHEDULE = {
    "scrape-rates": {
        "task": "ingestion.services.tasks.scrape_rates",
        "schedule": SCRAPE_INTERVAL_SECONDS,
    },
}

# --- Auth / passwords ------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Static bearer token guarding POST /rates/ingest (no external auth service).
# Retained for backwards compatibility; the ingest endpoint now authenticates via
# DRF token auth (see accounts.authentication.BearerTokenAuthentication).
INGEST_API_TOKEN = get_env("INGEST_API_TOKEN", "")

# Default user provisioned before seeding so the dashboard can auto-login and
# obtain a bearer token for the ingest endpoint (demo convenience, no external
# auth service). Override in production.
DEFAULT_INGEST_USERNAME = get_env("DEFAULT_INGEST_USERNAME", "ingestor")
DEFAULT_INGEST_PASSWORD = get_env("DEFAULT_INGEST_PASSWORD", "ingest-dev-password")

# --- DRF -------------------------------------------------------------------
REST_FRAMEWORK = {
    # GET endpoints are public; the ingest view opts into auth explicitly.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "rates.pagination.DefaultPagination",
    "PAGE_SIZE": get_env("API_DEFAULT_PAGE_SIZE", 50, cast=int),
    "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
}

# --- CORS ------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = get_csv_env(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
)

# --- I18N / static ---------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Observability ---------------------------------------------------------
# Any single DB query slower than this (ms) is logged at WARNING.
SLOW_QUERY_MS = get_env("SLOW_QUERY_MS", 200, cast=int)
LOG_LEVEL = get_env("LOG_LEVEL", "INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "common.logging.JsonFormatter",
            "format": "%(timestamp)s %(level)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "rateradar": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
