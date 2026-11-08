"""Settings shared by every server environment.

Secrets, hosts, the database and storage are defined per environment in dev.py, prod.py
and test.py. Values come from environment variables (django-environ): Docker compose
passes them with ``env_file``; the env files exist only on the server and are never
committed (TZ SEC-12). The Claude API key is NOT a Django setting: only the Celery
worker has it in its environment, and only the job pipeline reads it (jobs.pipeline).
"""

from pathlib import Path

import django_stubs_ext
import environ
from celery.schedules import crontab
from csp.constants import NONE, SELF

# Generic Django classes (ModelAdmin[Job]) at runtime, for strict typing.
django_stubs_ext.monkeypatch()

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # server/

env = environ.Env()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "axes",
    "csp",
    "accounts",
    "domains",
    "jobs",
    "scout",
    "security",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
    # django-axes: must be the last one (TZ SEC-17, login attempts are limited)
    "axes.middleware.AxesMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "yoriqnoma_server.urls"
WSGI_APPLICATION = "yoriqnoma_server.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Argon2 first (TZ SEC-15); the others only read old hashes.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "jobs:list"
LOGOUT_REDIRECT_URL = "login"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "uz"
LANGUAGES = [("uz", "O'zbekcha")]
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = env.str("DJANGO_STATIC_ROOT", default=str(BASE_DIR / "staticfiles"))
STATICFILES_DIRS = [BASE_DIR / "static"]

# Uploads (blueprint.json, bundle.zip) are checked by size before they are read.
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

X_FRAME_OPTIONS = "DENY"

# Content Security Policy (django-csp 4): only our own static files, no inline scripts.
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": [SELF],
        "script-src": [SELF],
        "style-src": [SELF],
        "img-src": [SELF, "data:"],
        "connect-src": [SELF],
        "font-src": [SELF],
        "object-src": [NONE],
        "base-uri": [SELF],
        "form-action": [SELF],
        "frame-ancestors": [NONE],
    }
}

# django-axes: 5 wrong passwords lock the username+IP pair for one hour.
AXES_FAILURE_LIMIT = env.int("YORIQNOMA_LOGIN_FAILURE_LIMIT", default=5)
AXES_COOLOFF_TIME = 1  # hours
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "registration/locked.html"
AXES_VERBOSE = False

# DRF: session authentication only (no API keys, TZ FR-SV3); default-deny.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
}

# --- logging: secrets never reach a log line (TZ SEC-12, NFR-6) -------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"secrets": {"()": "security.logfilter.SecretsFilter"}},
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["secrets"],
            "formatter": "plain",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        name: {"handlers": ["console"], "level": "INFO", "propagate": False}
        for name in ("django", "celery", "anthropic", "httpx", "jobs", "scout", "security")
    },
}

# --- Celery ---------------------------------------------------------------------------

CELERY_BROKER_URL = env.str("REDIS_URL", default="redis://127.0.0.1:6379/0")
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_HIJACK_ROOT_LOGGER = False  # Django LOGGING (with the secrets filter) stays
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "cleanup-expired": {"task": "jobs.cleanup_expired", "schedule": crontab(hour=3, minute=0)},
    "reap-stuck-jobs": {"task": "jobs.reap_stuck_jobs", "schedule": 600.0},
}

# --- the tool itself --------------------------------------------------------------------

VAR_DIR = Path(env.str("YORIQNOMA_VAR_DIR", default=str(BASE_DIR / "var")))

# Claude models by task (TZ FR-SV6) and prices, US dollars per million tokens.
YORIQNOMA_MODELS = {
    "classify": env.str("YORIQNOMA_MODEL_HAIKU", default="claude-haiku-5-5"),
    "*": env.str("YORIQNOMA_MODEL_SONNET", default="claude-sonnet-5-5"),
    "agent_step": env.str("YORIQNOMA_MODEL_SONNET", default="claude-sonnet-5-5"),
    "final_review": env.str("YORIQNOMA_MODEL_OPUS", default="claude-opus-5-5"),
}
YORIQNOMA_PRICES = env.json("YORIQNOMA_PRICES", default={})

# Spending limits (TZ FR-SV6): one Claude key pays for every job, sign-up is open.
YORIQNOMA_DEFAULT_JOB_BUDGET_USD = env.float("YORIQNOMA_DEFAULT_JOB_BUDGET_USD", default=3.0)
YORIQNOMA_MAX_JOB_BUDGET_USD = env.float("YORIQNOMA_MAX_JOB_BUDGET_USD", default=20.0)
YORIQNOMA_USER_DAILY_BUDGET_USD = env.float("YORIQNOMA_USER_DAILY_BUDGET_USD", default=10.0)
YORIQNOMA_USER_MONTHLY_BUDGET_USD = env.float("YORIQNOMA_USER_MONTHLY_BUDGET_USD", default=50.0)
YORIQNOMA_MONTHLY_BUDGET_USD = env.float("YORIQNOMA_MONTHLY_BUDGET_USD", default=500.0)

YORIQNOMA_MAX_CONCURRENT_JOBS = env.int("YORIQNOMA_MAX_CONCURRENT_JOBS", default=2)
YORIQNOMA_RETENTION_DAYS = env.int("YORIQNOMA_RETENTION_DAYS", default=30)
YORIQNOMA_JOB_TIME_LIMIT_S = env.int("YORIQNOMA_JOB_TIME_LIMIT_S", default=3 * 3600)
YORIQNOMA_INPUT_TIMEOUT_S = env.int("YORIQNOMA_INPUT_TIMEOUT_S", default=600)
YORIQNOMA_BUNDLE_MAX_BYTES = env.int("YORIQNOMA_BUNDLE_MAX_BYTES", default=500 * 1024 * 1024)
YORIQNOMA_BLUEPRINT_MAX_BYTES = env.int("YORIQNOMA_BLUEPRINT_MAX_BYTES", default=5 * 1024 * 1024)

# Test mail: *@inbox.<server domain> lands in Mailpit (MX record points to the server).
YORIQNOMA_MAIL_DOMAIN = env.str("YORIQNOMA_MAIL_DOMAIN", default="inbox.yoriqnoma.test")
YORIQNOMA_MAILPIT_URL = env.str("YORIQNOMA_MAILPIT_URL", default="http://mailpit:8025")
YORIQNOMA_PUBLIC_URL = env.str("YORIQNOMA_PUBLIC_URL", default="http://127.0.0.1:8000")

# Etiquette (TZ SEC-14).
YORIQNOMA_VERSION = "0.1.0"
YORIQNOMA_USER_AGENT = (
    f"AI-user-yoriqnoma/{YORIQNOMA_VERSION} (+{YORIQNOMA_PUBLIC_URL.rstrip('/')}/about/)"
)
YORIQNOMA_REQUESTS_PER_SECOND = env.float("YORIQNOMA_REQUESTS_PER_SECOND", default=2.0)

# Mode B scouting limits (ARCHITECTURE §7.6).
YORIQNOMA_SCOUT_MAX_PAGES = env.int("YORIQNOMA_SCOUT_MAX_PAGES", default=60)
YORIQNOMA_SCOUT_AGENT_STEPS = env.int("YORIQNOMA_SCOUT_AGENT_STEPS", default=40)
YORIQNOMA_SCOUT_AGENT_SHARE = env.float("YORIQNOMA_SCOUT_AGENT_SHARE", default=0.4)

# Host names that may resolve to private addresses. ONLY for the e2e test profile (the
# demo_shop container) and slow tests; prod.py forces an empty list (TZ SEC-10).
YORIQNOMA_PRIVATE_ALLOWLIST: list[str] = []

# Redis for the per-domain rate limiter; empty means an in-process limiter (dev, tests).
YORIQNOMA_RATELIMIT_REDIS_URL = env.str("YORIQNOMA_RATELIMIT_REDIS_URL", default="")
