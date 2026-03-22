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


def gozetmen_bul(aktif_sinav, tarih, saat: str, sinifsube: str) -> str | None:
    """
    Verilen (tarih, saat, sinifsube) için gözetmen öğretmenini döndürür.

    Kural: saat - 50 dakikada aynı sınıfta dersi olan öğretmen gözetmendir.
    Eşleşme bulunamazsa None döner.
    """
    from .models import DersProgram

    onceki_saat = onceki_ders_saati(saat)
    if not onceki_saat:
        return None

    gun = tarih.strftime("%A")  # "Monday", "Tuesday", ...

    dp = DersProgram.objects.filter(
        sinav=aktif_sinav,
        gun=gun,
        giris_saat=onceki_saat,
        sinif_sube__sinifsube=sinifsube,
    ).values_list("ders_ogretmeni", flat=True).first()

    return dp  # str veya None
