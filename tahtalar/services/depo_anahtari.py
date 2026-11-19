"""Tahtaların APT deposunun imza anahtarı.

Anahtar sunucuda bir kez üretilir (kurulumcu üretir; elle:
`python manage.py tahta_apt_anahtari_olustur`) ve `DEPO_KLASORU` altında durur
(repoya girmez, `.gitignore`). Açık anahtar akal-eta-yonetim paketine gömülür;
tahtalardaki APT depo imzasını onunla doğrular. Anahtar değişirse eski anahtarı
taşıyan tahtalar depodan güncelleme alamaz: paketin bir kez elle yeniden
kurulması gerekir.

`DEPO_KLASORU` (anahtar + sunulmuş paketlerin arşivi) uygulamayı çalıştıran
servis kullanıcısına (akalsite) aittir: proje kökü ona yazılabilir değildir
(bkz. kurulumcu/servis_kullanicisi.py: tahta_deposunu_hazirla). İlk sürümde
anahtar proje kökünde (`ESKI_ANAHTAR_DOSYASI`) duruyordu; orada bulunursa
okunur ve klasör yazılabilirse yeni yerine kopyalanır.
"""

import json
import os
from pathlib import Path

from django.conf import settings

from tahtalar.services.openpgp import Anahtar

DEPO_KLASORU = Path(settings.BASE_DIR) / "tahta-deposu"
ANAHTAR_DOSYASI = DEPO_KLASORU / "imza-anahtari.json"
ESKI_ANAHTAR_DOSYASI = Path(settings.BASE_DIR) / "tahta-apt-imza-anahtari.json"
KULLANICI_KIMLIGI = "akal-eta-yonetim APT deposu (okul sunucusu)"
SERVIS_KOMUTU = (
    "sudo -u akalsite env -C <PROJE_DIZINI> venv/bin/python manage.py "
    "tahta_apt_anahtari_olustur --settings=config.settings.production"
)

# Anahtarın, depo dosyalarının ve depo paketinin zamanı. Sabit tutulur: aynı
# sürüm her istekte aynı baytlarla üretilir (gunicorn işçileri arasında da),
# saati geri kalmış tahtalar da imzayı "gelecekten" saymaz.
SABIT_ZAMAN = 1767225600  # 2026-01-01 00:00:00 UTC


class AnahtarHatasi(Exception):
    pass


def _coz(metin, ad):
    try:
        veri = json.loads(metin)
        return Anahtar(bytes.fromhex(veri["tohum"]), veri["olusturma"])
    except (ValueError, KeyError, TypeError) as hata:
        raise AnahtarHatasi(f"{ad} okunamadı: {hata}") from None


def _oku(yol):
    try:
        return yol.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as hata:
        raise AnahtarHatasi(
            f"{yol} okunamadı: {hata}. Dosya uygulamayı çalıştıran kullanıcıya ait olmalı "
            "(kurulumcuyu yeniden çalıştırmak düzeltir)."
        ) from None


def _yaz(yol, veri):
    """Yalnızca sahibinin okuyacağı şekilde, atomik yazar."""
    yol.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    gecici = yol.with_name(f".{yol.name}.{os.getpid()}.tmp")
    fd = os.open(gecici, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(veri)
    os.replace(gecici, yol)


def _eskiyi_tasi():
    """Eski konumdaki anahtar → bayt (yoksa None). Yeni yere yazılabiliyorsa kopyalar."""
    veri = _oku(ESKI_ANAHTAR_DOSYASI)
    if veri is not None:
        _coz(veri, ESKI_ANAHTAR_DOSYASI.name)
        try:
            _yaz(ANAHTAR_DOSYASI, veri)
        except OSError:
            pass  # eski yerden okunmaya devam edilir; kurulumcu taşır
    return veri


def imza_anahtari():
    """Sunucudaki imza anahtarı; dosya yoksa None (depo kapalı)."""
    veri = _oku(ANAHTAR_DOSYASI)
    if veri is None:
        veri = _eskiyi_tasi()
    return None if veri is None else _coz(veri, ANAHTAR_DOSYASI.name)


def anahtar_dosyasi():
    """Anahtarın şu an okunduğu dosya (yedekleme için); yoksa None."""
    for yol in (ANAHTAR_DOSYASI, ESKI_ANAHTAR_DOSYASI):
        if yol.is_file():
            return yol
    return None


def depo_hazir_mi():
    try:
        return imza_anahtari() is not None
    except AnahtarHatasi:
        return False


def imza_anahtari_olustur(zorla=False):
    """Anahtar yoksa üretip `ANAHTAR_DOSYASI`'na (yalnızca sahibi okur) yazar →
    (Anahtar, üretildi mi). Eski konumda varsa yeni yere taşınır, üretilmez."""
    if not zorla:
        if ANAHTAR_DOSYASI.exists():
            raise AnahtarHatasi(
                f"{ANAHTAR_DOSYASI} zaten var. Değiştirmek, depoyu tanıyan tahtaların "
                "güncelleme almasını keser; gerçekten isteniyorsa --zorla kullanın."
            )
        veri = _oku(ESKI_ANAHTAR_DOSYASI)
        if veri is not None:
            anahtar = _coz(veri, ESKI_ANAHTAR_DOSYASI.name)
            _yeni_yere_yaz(veri)
            return anahtar, False
    anahtar = Anahtar.uret(SABIT_ZAMAN)
    icerik = json.dumps({"tohum": anahtar.tohum().hex(), "olusturma": anahtar.olusturma})
    _yeni_yere_yaz((icerik + "\n").encode("utf-8"))
    return anahtar, True


def _yeni_yere_yaz(veri):
    try:
        _yaz(ANAHTAR_DOSYASI, veri)
    except OSError as hata:
        raise AnahtarHatasi(
            f"{ANAHTAR_DOSYASI} yazılamadı: {hata}. Komutu uygulamayı çalıştıran "
            f"kullanıcıyla çalıştırın: {SERVIS_KOMUTU}"
        ) from None


def acik_anahtarlik():
    """Pakete gömülecek ikili anahtarlık; anahtar yoksa None."""
    anahtar = imza_anahtari()
    return anahtar.acik_anahtarlik(KULLANICI_KIMLIGI) if anahtar else None
