"""Tahtaların akal-eta-yonetim güncellemelerini çektiği yerel APT deposu.

"Düz" (flat) bir Debian deposudur; tahtadaki kaynak satırı:

    deb [signed-by=/usr/share/keyrings/akal-eta-yonetim.gpg] <sunucu>/tahtalar/apt/ ./

Güncel sürüm (`akal_eta_yonetim.py` içindeki `SURUM`) her istekte koddan
üretilir; aynı sürüm ve aynı anahtar her zaman aynı baytları verir (zamanlar
`depo_anahtari.SABIT_ZAMAN`'a sabitlenir, Ed25519 imzası da belirlenimcidir).
Böylece `deploy.sh`'ye bir adım eklemeden, sürüm artırılıp main'e alındığında
depo kendiliğinden güncellenir.

Sunulan her sürüm `ARSIV_KLASORU`'na bir kez kaydedilir (repoya girmez); depo
listesinde son `LISTEDEKI_SURUM_SAYISI` sürüm bulunur. Yeni sürüm tahtada
çalışmazsa tahta eski sürümü buradan geri kurar (bkz. akal_eta_yonetim.py,
kendini güncelleme).
"""

import email.utils
import hashlib
import logging
import os
import re
from pathlib import Path

from django.conf import settings

from tahtalar.services import depo_anahtari, kurulum_paketi

log = logging.getLogger(__name__)

DOSYALAR = ("InRelease", "Release", "Release.gpg", "Packages")
ARSIV_KLASORU = Path(settings.BASE_DIR) / "tahta-paketleri"
LISTEDEKI_SURUM_SAYISI = 5
_ARSIV_KALIBI = re.compile(rf"^{re.escape(kurulum_paketi.PAKET_ADI)}_(\d+)\.(\d+)\.(\d+)_all\.deb$")


def _ozetler(veri):
    return {
        "MD5Sum": hashlib.md5(veri, usedforsecurity=False).hexdigest(),
        "SHA256": hashlib.sha256(veri).hexdigest(),
    }


# ── Sürüm arşivi ────────────────────────────────────────────────────────


def arsivle(ad, paket):
    """Paketi arşive yazar (yoksa ya da farklıysa). Yazılamazsa depo yine
    çalışır, yalnızca geri dönüş noktası eksik kalır."""
    yol = ARSIV_KLASORU / ad
    try:
        if yol.is_file() and yol.read_bytes() == paket:
            return
        ARSIV_KLASORU.mkdir(mode=0o755, exist_ok=True)
        gecici = yol.with_name(f".{ad}.{os.getpid()}.tmp")
        gecici.write_bytes(paket)
        os.replace(gecici, yol)
    except OSError as hata:
        log.warning("Tahta paketi arşive yazılamadı (%s): %s", yol, hata)


def guncel_surumu_arsivle():
    """Güncel sürüm arşivde yoksa üretip yazar (her tahta bağlantısında çağrılır;
    arşivde varsa paket üretilmez)."""
    if (ARSIV_KLASORU / kurulum_paketi.paket_dosya_adi()).is_file():
        return
    try:
        arsivle(kurulum_paketi.paket_dosya_adi(), kurulum_paketi.depo_paketi_olustur())
    except (kurulum_paketi.PaketHatasi, depo_anahtari.AnahtarHatasi):
        pass


def depodaki_paketler():
    """{dosya adı: paket bytes}, eskiden yeniye. Güncel sürüm koddan üretilir ve
    arşivlenir; eski sürümler arşivden gelir."""
    guncel_ad = kurulum_paketi.paket_dosya_adi()
    guncel = kurulum_paketi.depo_paketi_olustur()
    arsivle(guncel_ad, guncel)
    surumler = {}
    try:
        for yol in ARSIV_KLASORU.iterdir():
            eslesme = _ARSIV_KALIBI.match(yol.name)
            if eslesme and yol.name != guncel_ad:
                surumler[tuple(int(p) for p in eslesme.groups())] = yol
    except OSError:
        pass
    eskiler = sorted(surumler.items())[-(LISTEDEKI_SURUM_SAYISI - 1) :]
    paketler = {}
    for _, yol in eskiler:
        try:
            paketler[yol.name] = yol.read_bytes()
        except OSError:
            continue
    paketler[guncel_ad] = guncel
    return paketler


# ── Depo dosyaları ──────────────────────────────────────────────────────


def packages_girdisi(ad, paket):
    """Packages dosyasındaki bir paket: control alanları + Filename/Size/özetler."""
    control = kurulum_paketi.control_alanlari(paket).rstrip("\n")
    bas, aciklama = control.split("\nDescription:", 1)
    ozet = _ozetler(paket)
    return (
        f"{bas}\n"
        f"Filename: {ad}\n"
        f"Size: {len(paket)}\n"
        f"MD5sum: {ozet['MD5Sum']}\n"
        f"SHA256: {ozet['SHA256']}\n"
        f"Description:{aciklama}\n"
    )


def packages(paketler):
    return "\n".join(packages_girdisi(ad, paket) for ad, paket in paketler.items()).encode("utf-8")


def release(packages_icerik):
    ozet = _ozetler(packages_icerik)
    tarih = email.utils.formatdate(depo_anahtari.SABIT_ZAMAN, usegmt=True)
    satirlar = [
        "Origin: akalyonetim",
        f"Label: {kurulum_paketi.PAKET_ADI}",
        f"Date: {tarih}",
        "Description: akal-eta-yonetim (okul sunucusu)",
    ]
    for alan in ("MD5Sum", "SHA256"):
        satirlar += [f"{alan}:", f" {ozet[alan]} {len(packages_icerik)} Packages"]
    return "\n".join(satirlar) + "\n"


def depo_dosyasi(ad):
    """Depodaki bir dosyanın içeriği; depo kapalıysa ya da ad bilinmiyorsa None."""
    anahtar = depo_anahtari.imza_anahtari()
    if anahtar is None:
        return None
    paketler = depodaki_paketler()
    if ad in paketler:
        return paketler[ad]
    if ad not in DOSYALAR:
        return None
    pk = packages(paketler)
    if ad == "Packages":
        return pk
    metin = release(pk)
    if ad == "Release":
        return metin.encode("utf-8")
    if ad == "Release.gpg":
        return anahtar.ayrik_imza(metin.encode("utf-8"), depo_anahtari.SABIT_ZAMAN)
    return anahtar.acik_metin_imza(metin, depo_anahtari.SABIT_ZAMAN)
