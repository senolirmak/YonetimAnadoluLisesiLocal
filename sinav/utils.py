# -*- coding: utf-8 -*-
"""
sinav app yardımcı fonksiyonları.
"""


def onceki_ders_saati(saat: str) -> str | None:
    """
    'HH:MM' formatındaki saatten 50 dakika çıkarır.
    Sonuç negatif olursa None döner.
    """
    h, m = map(int, saat.split(":"))
    total = h * 60 + m - 50
    if total < 0:
        return None
    return f"{total // 60:02d}:{total % 60:02d}"


def saat_offset(saat: str, dakika: int) -> str:
    """'HH:MM' formatına dakika ekler/çıkarır. Sonucu 'HH:MM' döner (negatif → '00:00')."""
    h, m = map(int, saat.split(":"))
    total = max(0, h * 60 + m + dakika)
    return f"{total // 60:02d}:{total % 60:02d}"


def slot_aktif_mi(tarih, saat: str, bugun, simdi_str: str,
                  baslangic_dk: int = -30, bitis_dk: int = 120) -> bool:
    """Slot'un buton erişimine açık olup olmadığını döner."""
    if tarih != bugun:
        return False
    return saat_offset(saat, baslangic_dk) <= simdi_str <= saat_offset(saat, bitis_dk)


def salon_goster(salon_kodu: str) -> str:
    """'Salon-10_B' → 'Salon 10/B' formatına çevirir."""
    return salon_kodu.replace("-", " ", 1).replace("_", "/")


def gozetmen_bul(aktif_sinav, tarih, saat: str, sinifsube: str) -> str | None:
    """
    Verilen (tarih, saat, sinifsube) için gözetmen öğretmenini döndürür.

    Kural: saat - 50 dakikada aynı sınıfta dersi olan öğretmen gözetmendir.
    Eşleşme bulunamazsa None döner.
    """
    from datetime import time as dt_time
    from dersprogrami.models import DersProgrami

    onceki_saat = onceki_ders_saati(saat)
    if not onceki_saat:
        return None

    gun = tarih.strftime("%A")  # "Monday", "Tuesday", ...

    # sinifsube "9/A" → sinif=9, sube="A"
    try:
        sinif_str, sube = sinifsube.split("/")
        sinif = int(sinif_str)
    except (ValueError, AttributeError):
        return None

    h, m = map(int, onceki_saat.split(":"))
    giris = dt_time(h, m)

    dp = (
        DersProgrami.objects
        .filter(
            gun=gun,
            giris_saat=giris,
            sinif_sube__sinif=sinif,
            sinif_sube__sube=sube,
            uygulama_tarihi__lte=tarih,
        )
        .order_by("-uygulama_tarihi")
        .select_related("ogretmen")
        .first()
    )

    return dp.ogretmen.adi_soyadi if dp else None
