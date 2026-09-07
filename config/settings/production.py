import os

from .base import *  # noqa: F401, F403

DEBUG = False

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST"),
        "PORT": os.getenv("DB_PORT"),
    }
}

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

# kurulumcu, nginx'i HTTPS (yerel CA ile — bkz. kurulumcu/sertifika.py modül
# docstring'i, sunucu okul ağı içinde/dışarıya kapalı olduğundan Let's
# Encrypt kullanılamıyor) ile yapılandırdığında .env'e HTTPS_ETKIN=True yazar.
# Bu bayrak olmadan (mevcut/eski HTTP-only kurulumlarda) aşağıdaki ayarlar
# devre DIŞI kalır — aksi hâlde SESSION/CSRF çerezleri "Secure" işaretlenir
# ve düz HTTP üzerinde tarayıcı tarafından hiç gönderilmez, bu da nginx henüz
# güncellenmemiş bir sunucuda oturum açmayı tamamen kırar.
HTTPS_ETKIN = os.getenv("HTTPS_ETKIN", "False") == "True"
if HTTPS_ETKIN:
    # nginx TLS'i sonlandırıp gunicorn'a düz bir unix soketi üzerinden
    # ilettiğinden, bu başlık olmadan request.is_secure() her zaman False
    # döner (bkz. kurulumcu/sunucu.py: nginx_https_yapilandir docstring'i).
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
