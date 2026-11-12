"""
Baymax — Django settings.

EVERY environment-specific value comes from environment variables: loaded
from app/.env locally, from the Vercel dashboard in production. There are no
fallback defaults in this file. If a variable is missing, Django refuses to
start and lists every missing variable at once, so nothing silently falls
back to a value you did not choose.
"""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # = app/

# Load app/.env if it exists. On Vercel there is no .env file; the real
# environment variables are used instead, and this call does nothing.
load_dotenv(BASE_DIR / '.env')


# ── Strict environment readers ────────────────────────────────────────────────
_missing = []   # names of required variables that are not set
_invalid = []   # (name, reason) for variables with an unusable value


def _get(name: str, allow_empty: bool = False) -> str:
    """Return a required variable. Record it as missing if absent (or empty)."""
    value = os.environ.get(name)
    if value is None or (not allow_empty and value.strip() == ''):
        _missing.append(name)
        return ''
    return value.strip()


def _get_bool(name: str) -> bool:
    value = _get(name)
    if value == '':
        return False
    if value.lower() in {'1', 'true', 'yes', 'on'}:
        return True
    if value.lower() in {'0', 'false', 'no', 'off'}:
        return False
    _invalid.append((name, 'must be True or False'))
    return False


def _get_int(name: str) -> int:
    value = _get(name)
    if value == '':
        return 0
    try:
        return int(value)
    except ValueError:
        _invalid.append((name, 'must be a whole number'))
        return 0


def _get_list(name: str, allow_empty: bool = False) -> list:
    """Comma-separated variable -> list of non-empty, stripped items."""
    return [item.strip() for item in _get(name, allow_empty).split(',') if item.strip()]


def _get_path(name: str) -> str:
    """Path variable. A relative path is resolved against app/ (BASE_DIR)."""
    value = _get(name)
    if value == '':
        return ''
    path = Path(value)
    return str(path if path.is_absolute() else (BASE_DIR / path).resolve())


# ── Core ──────────────────────────────────────────────────────────────────────
DEBUG = _get_bool('DEBUG')
SECRET_KEY = _get('SECRET_KEY')
ALLOWED_HOSTS = _get_list('ALLOWED_HOSTS')
CSRF_TRUSTED_ORIGINS = _get_list('CSRF_TRUSTED_ORIGINS', allow_empty=True)

# ── Applications ──────────────────────────────────────────────────────────────
# django.contrib.admin is deliberately NOT installed: /admin/ belongs to the
# Admin IT portal of Baymax, not to Django's built-in admin site.
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # must be second
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ── Database ──────────────────────────────────────────────────────────────────
_database_url = os.environ.get('DATABASE_URL', '').strip()
if _database_url:
    DATABASES = {'default': dj_database_url.parse(_database_url, conn_max_age=0)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': _get('DB_NAME'),
            'USER': _get('DB_USER'),
            'PASSWORD': _get('DB_PASSWORD', allow_empty=True),
            'HOST': _get('DB_HOST'),
            'PORT': _get('DB_PORT'),
        }
    }

# ── Sessions & cache ──────────────────────────────────────────────────────────
# Serverless instances do not share memory, so both live in the database.
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'baymax_cache',
    }
}

# ── Authentication ────────────────────────────────────────────────────────────
# Baymax uses its own session-based role login. allauth is used only for the
# Google OAuth handshake.
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
SITE_ID = 1
LOGIN_URL = '/login/'

ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': _get('GOOGLE_CLIENT_ID'),
            'secret': _get('GOOGLE_CLIENT_SECRET'),
            'key': '',
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = _get('LANGUAGE_CODE')
TIME_ZONE = _get('TIME_ZONE')
USE_I18N = True
USE_TZ = False  # schema.sql uses plain TIMESTAMP columns (no time zone)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Static files (WhiteNoise) ─────────────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

# ── Production security ───────────────────────────────────────────────────────
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # SECURE_SSL_REDIRECT must stay False — Vercel terminates SSL at the edge.
    SECURE_SSL_REDIRECT = False

# ── LLM (Groq, via its OpenAI-compatible endpoint) ────────────────────────────
GROQ_API_KEY = _get('GROQ_API_KEY')
GROQ_MODEL = _get('GROQ_MODEL')
GROQ_TIMEOUT = _get_int('GROQ_TIMEOUT')

# ── Email (Gmail SMTP) ────────────────────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = _get('EMAIL_HOST')
EMAIL_PORT = _get_int('EMAIL_PORT')
EMAIL_USE_TLS = _get_bool('EMAIL_USE_TLS')
EMAIL_HOST_USER = _get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = _get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = _get('DEFAULT_FROM_EMAIL')

# ── Machine-learning artifacts ────────────────────────────────────────────────
SVM_PATH = _get_path('SVM_PATH')
SCALER_PATH = _get_path('SCALER_PATH')

# ── Fail fast, with one clear message ─────────────────────────────────────────
if _missing or _invalid:
    _lines = []
    if _missing:
        _lines.append('Missing from your environment (.env): ' + ', '.join(sorted(set(_missing))))
    for _name, _reason in _invalid:
        _lines.append(f'{_name} {_reason}')
    raise ImproperlyConfigured(
        'Baymax cannot start.\n  ' + '\n  '.join(_lines) +
        '\nCheck app/.env and fill in every value.'
    )