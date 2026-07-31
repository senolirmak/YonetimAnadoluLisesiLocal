from sinav.models import OturmaPlani


def en_yakin_sinav_sonucu(aktif_uretim, okulno: str, bugun) -> tuple:
    """Bir öğrencinin (okulno) aktif üretimdeki oturma planı kayıtlarından
    bugünküleri, yoksa en yakın gelecek tarihtekileri döner.

    Returns: (sonuclar, gosterim_tarihi, hata)
    """
    tum_sonuclar = list(
        OturmaPlani.objects
        .filter(uretim=aktif_uretim, okulno=okulno)
        .order_by("tarih", "saat", "oturum")
        .values("tarih", "saat", "salon", "sira_no", "ders_adi", "sinifsube", "adi_soyadi")
    )
    if not tum_sonuclar:
        return [], None, f"'{okulno}' okul numarasına ait kayıt bulunamadı."

    bugun_sonuclar = [s for s in tum_sonuclar if s["tarih"] == bugun]
    if bugun_sonuclar:
        return bugun_sonuclar, bugun, None

    yakin_tarih = next((s["tarih"] for s in tum_sonuclar if s["tarih"] > bugun), None)
    if yakin_tarih:
        sonuclar = [s for s in tum_sonuclar if s["tarih"] == yakin_tarih]
        return sonuclar, yakin_tarih, None

    return [], None, "Yaklaşan sınav oturumu bulunmuyor (tüm oturumlar geçmiş)."
