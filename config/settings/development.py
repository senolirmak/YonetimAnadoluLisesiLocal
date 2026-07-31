import os

from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = os.getenv(
    "ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0"
).split(",")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Yerel geliştirici araçları (bkz. devtools/README.md).
# Bu klasör .gitignore'dadır ve GitHub'a hiç gitmez; sadece fiziksel olarak
# diskte bulunduğunda etkinleşir, böylece development.py başka bir makinede
# (devtools klasörü olmadan) sorunsuz çalışmaya devam eder.
if (BASE_DIR / "devtools").is_dir():
    INSTALLED_APPS += ["devtools"]
