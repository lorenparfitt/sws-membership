"""Process configuration: Django settings, read from SWS_ environment variables.

A `.env` file beside manage.py is read first for development. Every value a
deployment must set has an SWS_ name; Django's own names are derived here so
there is one vocabulary for operators.
"""

import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(f"SWS_{name}", default)


def env_bool(name: str, default: bool) -> bool:
    value = env(name, "")
    return default if value == "" else value.lower() in ("1", "true", "yes", "on")


def _database(url: str) -> dict:
    parsed = urlparse(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
        "TEST": {"NAME": env("TEST_DATABASE_NAME", "sws_membership_test")},
    }


# --- Django -----------------------------------------------------------------

SECRET_KEY = env("SECRET_KEY", "dev-only-not-a-secret-set-SWS_SECRET_KEY-in-production")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = [h for h in env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "sws_membership.members",
    "sws_membership.accounts",
    "sws_membership.catalog",
    "sws_membership.entitlements",
    "sws_membership.waivers",
    "sws_membership.kiosk",
    "sws_membership.cards",
    "sws_membership.orders",
    # The project itself, for commands that belong to no one app.
    "sws_membership",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "sws_membership.csrf.EnsureCsrfCookie",
]

ROOT_URLCONF = "sws_membership.urls"
WSGI_APPLICATION = "sws_membership.wsgi.application"
ASGI_APPLICATION = "sws_membership.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {
    "default": _database(env("DATABASE_URL", "postgresql://sws:sws@localhost:5432/sws_membership"))
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "members.Member"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
# Session cookie: 30 days, http-only, same-site lax, secure outside development.
SESSION_COOKIE_AGE = 30 * 24 * 60 * 60
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env_bool("COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
# The browser reads the CSRF cookie to send it back as a header.
CSRF_COOKIE_HTTPONLY = False
CSRF_TRUSTED_ORIGINS = [
    o
    for o in env("CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://localhost:8000").split(",")
    if o
]

LANGUAGE_CODE = "en-ca"
TIME_ZONE = "America/Vancouver"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "var" / "static"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {
        "sws_membership": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
        "django": {"handlers": ["console"], "level": "INFO"},
    },
}

# --- The platform -----------------------------------------------------------

# Where sign-in links point; the React app in development.
SWS_FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", "http://localhost:5173")
# Where signature images and photos live in development. Production swaps in
# object storage behind the same seam.
SWS_STORAGE_DIRECTORY = env("STORAGE_DIRECTORY", str(BASE_DIR / "var" / "storage"))
# Printed on the back of every card as a QR code, as today.
SWS_SHUTTLE_URL = env("SHUTTLE_URL", "https://squamishwindsports.com/shuttle-boat-parking/")

# Which mailer sends. console logs each message; mailchimp delivers it
# through Mailchimp Transactional, the account the newsletters use.
SWS_MAIL_BACKEND = env("MAIL_BACKEND", "console")
SWS_MAILCHIMP_TRANSACTIONAL_API_KEY = env("MAILCHIMP_TRANSACTIONAL_API_KEY")
SWS_MAIL_FROM_EMAIL = env("MAIL_FROM_EMAIL", "membership@squamishwindsports.com")
SWS_MAIL_FROM_NAME = env("MAIL_FROM_NAME", "Squamish Windsports Society")

# Which processor charges cards. The fake one needs no network and is
# approved by posting to the notification endpoint; production is nuvei.
SWS_PAYMENT_PROCESSOR = env("PAYMENT_PROCESSOR", "fake")
SWS_NUVEI_MERCHANT_ID = env("NUVEI_MERCHANT_ID")
SWS_NUVEI_MERCHANT_SITE_ID = env("NUVEI_MERCHANT_SITE_ID")
SWS_NUVEI_SECRET_KEY = env("NUVEI_SECRET_KEY")
SWS_NUVEI_ENVIRONMENT = env("NUVEI_ENVIRONMENT", "int")
# Public URL Nuvei posts notifications to; must reach this API.
SWS_NUVEI_NOTIFICATION_URL = env(
    "NUVEI_NOTIFICATION_URL", "http://localhost:8000/api/payments/notification"
)

for _name, _allowed in (
    ("SWS_MAIL_BACKEND", ("console", "mailchimp")),
    ("SWS_PAYMENT_PROCESSOR", ("fake", "nuvei")),
    ("SWS_NUVEI_ENVIRONMENT", ("int", "prod")),
):
    if globals()[_name] not in _allowed:
        raise ValueError(f"{_name} must be one of {', '.join(_allowed)}")
