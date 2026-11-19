"""Tahtaların APT deposunun imza anahtarı.

Anahtar sunucuda bir kez üretilir (`python manage.py tahta_apt_anahtari_olustur`)
ve BASE_DIR altındaki dosyada durur (repoya girmez, `.gitignore`). Açık
anahtar akal-eta-yonetim paketine gömülür; tahtalardaki APT depo imzasını
onunla doğrular. Anahtar değişirse eski anahtarı taşıyan tahtalar depodan
güncelleme alamaz: paketin bir kez elle yeniden kurulması gerekir.
"""

import json
import os
from pathlib import Path

from django.conf import settings

from tahtalar.services.openpgp import Anahtar

ANAHTAR_DOSYASI = Path(settings.BASE_DIR) / "tahta-apt-imza-anahtari.json"
KULLANICI_KIMLIGI = "akal-eta-yonetim APT deposu (okul sunucusu)"

# Anahtarın, depo dosyalarının ve depo paketinin zamanı. Sabit tutulur: aynı
# sürüm her istekte aynı baytlarla üretilir (gunicorn işçileri arasında da),
# saati geri kalmış tahtalar da imzayı "gelecekten" saymaz.
SABIT_ZAMAN = 1767225600  # 2026-01-01 00:00:00 UTC


class AnahtarHatasi(Exception):
    pass


def imza_anahtari():
    """Sunucudaki imza anahtarı; dosya yoksa None (depo kapalı)."""
    try:
        veri = json.loads(ANAHTAR_DOSYASI.read_text(encoding="utf-8"))
        return Anahtar(bytes.fromhex(veri["tohum"]), veri["olusturma"])
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as hata:
        raise AnahtarHatasi(f"{ANAHTAR_DOSYASI.name} okunamadı: {hata}") from None


def depo_hazir_mi():
    try:
        return imza_anahtari() is not None
    except AnahtarHatasi:
        return False


def imza_anahtari_olustur(zorla=False):
    """Yeni anahtar üretip dosyaya (yalnızca sahibi okur) yazar → Anahtar."""
    if ANAHTAR_DOSYASI.exists() and not zorla:
        raise AnahtarHatasi(
            f"{ANAHTAR_DOSYASI} zaten var. Değiştirmek, depoyu tanıyan tahtaların "
            "güncelleme almasını keser; gerçekten isteniyorsa --zorla kullanın."
        )
    anahtar = Anahtar.uret(SABIT_ZAMAN)
    icerik = json.dumps({"tohum": anahtar.tohum().hex(), "olusturma": anahtar.olusturma})
    gecici = ANAHTAR_DOSYASI.with_suffix(".tmp")
    fd = os.open(gecici, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(icerik + "\n")
    os.replace(gecici, ANAHTAR_DOSYASI)
    return anahtar


def acik_anahtarlik():
    """Pakete gömülecek ikili anahtarlık; anahtar yoksa None."""
    anahtar = imza_anahtari()
    return anahtar.acik_anahtarlik(KULLANICI_KIMLIGI) if anahtar else None
