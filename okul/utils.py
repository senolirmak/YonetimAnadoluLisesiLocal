from __future__ import annotations

import datetime


def get_aktif_tarih(veri_turu: str) -> datetime.date | None:
    """
    Verilen veri_turu için AktifVeriKonfigurasyonu tablosundaki aktif uygulama_tarihi'ni döner.
    Kayıt yoksa None döner — çağıran taraf fallback'i yönetir.

    veri_turu değerleri: "ders_programi", "personel_listesi", "nobet_listesi"
    """
    from okul.models import AktifVeriKonfigurasyonu

    try:
        return AktifVeriKonfigurasyonu.objects.get(veri_turu=veri_turu).uygulama_tarihi
    except AktifVeriKonfigurasyonu.DoesNotExist:
        return None


def set_aktif_tarih(veri_turu: str, uygulama_tarihi: datetime.date) -> None:
    """Import servisleri başarılı yüklemeden sonra bu fonksiyonu çağırır."""
    from okul.models import AktifVeriKonfigurasyonu

    AktifVeriKonfigurasyonu.objects.update_or_create(
        veri_turu=veri_turu,
        defaults={"uygulama_tarihi": uygulama_tarihi},
    )


def get_aktif_nobet_tarihi() -> datetime.date | None:
    """
    Aktif nöbet listesi uygulama_tarihi'ni döner.
    Konfigürasyon yoksa DB'deki en son NobetOgretmen tarihine fall-back yapar.
    """
    tarih = get_aktif_tarih("nobet_listesi")
    if tarih is None:
        from nobet.models import NobetGorevi
        tarih = (
            NobetGorevi.objects
            .order_by("-uygulama_tarihi")
            .values_list("uygulama_tarihi", flat=True)
            .first()
        )
    return tarih


def get_aktif_dp_tarihi() -> datetime.date | None:
    """
    Aktif ders programı uygulama_tarihi'ni döner.
    Konfigürasyon yoksa DB'deki en son tarihe fall-back yapar.
    Her iki durumda da None dönebilir (hiç kayıt yoksa).
    """
    tarih = get_aktif_tarih("ders_programi")
    if tarih is None:
        from dersprogrami.models import DersProgrami
        tarih = (
            DersProgrami.objects
            .order_by("-uygulama_tarihi")
            .values_list("uygulama_tarihi", flat=True)
            .first()
        )
    return tarih
