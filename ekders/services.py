from datetime import timedelta
from math import floor

from ekders.models import GOREV_TIPI_ESLEME, GorevTipi, OgretmenEkDers, Tatil

GUN_ALANLARI = {
    "Monday":    "pazartesi",
    "Tuesday":   "sali",
    "Wednesday": "carsamba",
    "Thursday":  "persembe",
    "Friday":    "cuma",
    "Saturday":  "cumartesi",
    "Sunday":    "pazar",
}

REHBERLIK_DERS_ADI = "REHBERLİK VE YÖNLENDİRME"


def _donem_pazartesiler(donem):
    """
    Dönem içindeki, en az bir çalışma günü olan haftaların Pazartesi tarihlerini döndürür.
    Tatil tablosundaki kayıtlar göz önüne alınır.
    """
    haftalar = []
    bas = donem.baslangic_tarihi

    # Dönemin ilk Pazartesi'sini bul
    gunler_fark = (7 - bas.weekday()) % 7
    pazartesi = bas if bas.weekday() == 0 else bas + timedelta(days=gunler_fark)

    while pazartesi <= donem.bitis_tarihi:
        # Bu haftada en az bir çalışma günü var mı?
        calisma_var = False
        for i in range(5):  # Pazartesi – Cuma
            gun = pazartesi + timedelta(days=i)
            if gun > donem.bitis_tarihi:
                break
            tatil_mi = Tatil.objects.filter(baslangic__lte=gun, bitis__gte=gun).exists()
            if not tatil_mi:
                calisma_var = True
                break
        if calisma_var:
            haftalar.append(pazartesi)
        pazartesi += timedelta(days=7)

    return haftalar


def _son_uygulama_tarihi(personel, baslangic):
    """DersProgrami'nde, verilen tarihten önceki en güncel uygulama_tarihi'ni döndürür."""
    from dersprogrami.models import DersProgrami
    return (
        DersProgrami.objects
        .filter(ogretmen=personel, uygulama_tarihi__lte=baslangic)
        .order_by("-uygulama_tarihi")
        .values_list("uygulama_tarihi", flat=True)
        .first()
    )


def _gunluk_ders(personel, uygulama_tarihi):
    """
    Her gün için ders saatini döndürür (REHBERLİK VE YÖNLENDİRME hariç).
    {field_name: saat} sözlüğü.
    """
    from dersprogrami.models import DersProgrami
    sonuc = {}
    for gun_tr, field in GUN_ALANLARI.items():
        sonuc[field] = (
            DersProgrami.objects
            .filter(ogretmen=personel, uygulama_tarihi=uygulama_tarihi, gun=gun_tr)
            .exclude(ders__ders_adi__iexact=REHBERLIK_DERS_ADI)
            .count()
        )
    return sonuc


def donem_hesapla(donem):
    """
    Dönem için tüm ders okuyan personelin haftalık kayıtlarını oluşturur/günceller.
    Var olan kayıtları günceller (idempotent), fazladan kayıt eklemez.
    Oluşturulan/güncellenen kayıt sayısını döndürür.
    """
    from nobet.models import NobetGorevi
    from okul.models import Personel

    gorev_tipi_cache = {gt.kod: gt for gt in GorevTipi.objects.all()}
    haftalar = _donem_pazartesiler(donem)

    personeller = (
        Personel.objects
        .filter(dersprogrami__isnull=False)
        .distinct()
    )

    islem_sayisi = 0
    for pazartesi in haftalar:
        pazar = pazartesi + timedelta(days=6)

        for personel in personeller:
            uygulama = _son_uygulama_tarihi(personel, pazartesi)
            if uygulama is None:
                continue

            gt_kod = GOREV_TIPI_ESLEME.get(personel.gorev_tipi or "", "brans_ogretmeni")
            gorev_tipi = gorev_tipi_cache.get(gt_kod)
            if not gorev_tipi:
                continue

            gunluk = _gunluk_ders(personel, uygulama)

            # Hiç ders saati yoksa kayıt oluşturma
            if sum(gunluk.values()) == 0:
                continue

            son_nobet_ut = (
                NobetGorevi.objects
                .filter(ogretmen__personel=personel, uygulama_tarihi__lte=pazartesi)
                .order_by("-uygulama_tarihi")
                .values_list("uygulama_tarihi", flat=True)
                .first()
            )
            nobet = (
                NobetGorevi.objects
                .filter(ogretmen__personel=personel, uygulama_tarihi=son_nobet_ut)
                .count()
                if son_nobet_ut else 0
            )

            OgretmenEkDers.objects.update_or_create(
                donem=donem,
                personel=personel,
                hafta_baslangic=pazartesi,
                defaults={"gorev_tipi": gorev_tipi, "nobet_sayisi": nobet, **gunluk},
            )
            islem_sayisi += 1

    return islem_sayisi


def donem_ozet_listesi(donem):
    """
    Dönem için tüm personelin aylık ek ders özetini hesaplar.
    Her personel için bir dict içeren liste döndürür.
    """
    from okul.models import Personel

    personel_ids = (
        OgretmenEkDers.objects
        .filter(donem=donem)
        .values_list("personel_id", flat=True)
        .distinct()
    )
    personeller = Personel.objects.filter(pk__in=personel_ids).order_by("adi_soyadi")

    return [personel_ozet(donem, p) for p in personeller]


def personel_ozet(donem, personel):
    """Bir dönem için tek personelin aylık ek ders hesabını döndürür."""
    kayitlar = list(
        OgretmenEkDers.objects
        .filter(donem=donem, personel=personel)
        .select_related("gorev_tipi")
        .order_by("hafta_baslangic")
    )
    if not kayitlar:
        return None

    gorev_tipi = kayitlar[0].gorev_tipi
    hafta_sayisi = len(kayitlar)
    toplam_ders = sum(k.haftalik_ders_saati for k in kayitlar)
    toplam_nobet_saat = sum(k.nobet_saati for k in kayitlar)
    toplam_diger = sum(k.diger_zorunlu_saat for k in kayitlar)

    maas_karsiligi = gorev_tipi.maas_karsiligi_haftalik * hafta_sayisi
    hazirlik = floor(float(toplam_ders) * float(gorev_tipi.hazirlik_katsayi))
    ucretli = max(0, toplam_ders - maas_karsiligi) + hazirlik + toplam_nobet_saat + toplam_diger

    return {
        "personel": personel,
        "gorev_tipi": gorev_tipi,
        "hafta_sayisi": hafta_sayisi,
        "toplam_ders": toplam_ders,
        "maas_karsiligi": maas_karsiligi,
        "hazirlik": hazirlik,
        "toplam_nobet_saat": toplam_nobet_saat,
        "toplam_diger": toplam_diger,
        "ucretli_ekders": ucretli,
        "haftalik_kayitlar": kayitlar,
    }
