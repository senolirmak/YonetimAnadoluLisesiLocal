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
    """Import servisleri başarılı yüklemeden sonra bu fonksiyonu çağırır.

    Yalnızca yeni tarih, o veri türü için hâlihazırda aktif olan tarihten DAHA GÜNCEL ya da
    hiç aktif tarih tanımlı değilse günceller. Geçmişe dönük (backfill) bir dosya
    yüklenmesi — örn. eksik bir ay için sonradan bulunan bir ders programı — sistemin
    "aktif" (en güncel/geçerli) kabul ettiği versiyonu geri almamalı (yaşandı: bkz. commit
    geçmişi). Bilinçli olarak eski bir tarihi aktif yapmak gerekiyorsa admin panelinden
    AktifVeriKonfigurasyonu kaydı elle güncellenmelidir.
    """
    from okul.models import AktifVeriKonfigurasyonu

    mevcut = AktifVeriKonfigurasyonu.objects.filter(veri_turu=veri_turu).first()
    if mevcut and mevcut.uygulama_tarihi and mevcut.uygulama_tarihi > uygulama_tarihi:
        return

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


def get_aktif_egitim_yili():
    """OkulBilgi singleton'dan aktif eğitim-öğretim yılını (EgitimOgretimYili) döner."""
    from okul.models import OkulBilgi

    okul = OkulBilgi.objects.select_related("okul_egtyil").first()
    return okul.okul_egtyil if okul else None


def get_aktif_donem():
    """OkulBilgi singleton'dan aktif dönemi (OkulDonem) döner."""
    from okul.models import OkulBilgi

    okul = OkulBilgi.objects.select_related("okul_donem").first()
    return okul.okul_donem if okul else None


def donem_tarihe_gore(tarih):
    """`tarih`i (baslangic..bitis aralığında) kapsayan OkulDonem kaydını döner — bulunamazsa
    None. `egitim_yili` bu kayıttan `.egitim_yili` ile erişilir.

    Bir içe aktarma kaydının hangi eğitim-öğretim yılına/dönemine ait olduğunu, sistemin
    O ANKİ aktif yılından (`get_aktif_egitim_yili`/`get_aktif_donem` — geçmişe dönük bir
    dosya yüklenirken yanlış sonuç verir, bkz. commit geçmişi) değil, dosyanın kendi
    uygulama_tarihi'nden belirlemek için kullanılır.
    """
    from okul.models import OkulDonem

    if not tarih:
        return None
    return (
        OkulDonem.objects.select_related("egitim_yili")
        .filter(baslangic__lte=tarih, bitis__gte=tarih)
        .first()
    )


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
