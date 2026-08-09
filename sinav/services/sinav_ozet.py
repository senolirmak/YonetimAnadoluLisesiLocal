from django.db.models import Max, Min

from dersprogrami.models import DersProgrami
from ogrenci.models import Ogrenci as OgrenciModel
from sinav.models import OturmaPlani, SinavBilgisi, SubeDers, Takvim, TakvimUretim


def db_ozeti() -> dict:
    aktif = SinavBilgisi.objects.filter(aktif=True).first()
    return {
        "ogrenci":      OgrenciModel.objects.count(),
        "ders_program": DersProgrami.objects.aktif().count(),
        "sube_ders":    SubeDers.objects.count(),
        "takvim":       Takvim.objects.filter(sinav=aktif).count(),
        "oturma_plani": OturmaPlani.objects.filter(sinav=aktif).count(),
    }


def sinav_takvim_araliklari(sinavlar) -> dict:
    """
    Her sınav için aktif TakvimUretim'in kapsadığı gerçek (üretilmiş) takvimin
    ilk ve son gününü döner: { sinav_id: (baslangic_tarihi, bitis_tarihi) }.

    sinav_baslangic_tarihi alanı elle girilir ve GA'ya başlangıç noktası olarak
    verilir; üretilen takvim tatil/çakışma yüzünden daha ileri bir tarihte
    başlayabilir veya beklenenden uzun sürebilir. Bu yüzden gerçek aralık,
    manuel alanla karıştırılmadan, üretilen Takvim kayıtlarından hesaplanır.
    """
    uretimler = {
        u.sinav_id: u
        for u in TakvimUretim.objects.filter(sinav__in=sinavlar, aktif=True)
    }
    if not uretimler:
        return {}

    araliklar = (
        Takvim.objects
        .filter(uretim__in=uretimler.values())
        .values("uretim")
        .annotate(baslangic=Min("tarih"), bitis=Max("tarih"))
    )
    aralik_by_uretim = {a["uretim"]: (a["baslangic"], a["bitis"]) for a in araliklar}

    return {
        sinav_id: aralik_by_uretim[u.pk]
        for sinav_id, u in uretimler.items()
        if u.pk in aralik_by_uretim
    }


def gozetmen_ozeti_hesapla(aktif_uretim) -> tuple[list[dict], dict]:
    """Aktif TakvimUretim'deki tüm gözetmenler + Sınıf Listesi PDF öğretmenlerini
    listeler. `aktif_uretim=None` ise boş sonuç döner."""
    from okul.models import Personel
    from sinav.services.ders_sinav_eslestir import tum_siniflistesi_eslestir

    if aktif_uretim is None:
        return [], {}

    # Gözetmen listesi + slot sayıları (FK üzerinden, ID bazlı)
    personel_rows = (
        OturmaPlani.objects
        .filter(uretim=aktif_uretim, gozetmen_fk__isnull=False)
        .values("gozetmen_fk_id")
        .distinct()
    )
    gozetmen_slot_sayisi = {}  # pk → slot_sayisi
    for row in personel_rows:
        pk = row["gozetmen_fk_id"]
        gozetmen_slot_sayisi[pk] = (
            OturmaPlani.objects
            .filter(uretim=aktif_uretim, gozetmen_fk_id=pk)
            .values("tarih", "saat", "oturum")
            .distinct()
            .count()
        )

    # Sınıf Listesi PDF: sınav öncesi son dersin öğretmeni (bitis bazlı eşleşme, ID bazlı)
    siniflistesi_map = tum_siniflistesi_eslestir(aktif_uretim)

    # Tüm personel ID'lerini birleştir (gozetmen_fk + siniflistesi sahibi) ve
    # isimleri tek sorguda çek (isim yalnızca gösterim için, eşleştirme ID ile yapılır)
    tum_pkler = set(gozetmen_slot_sayisi) | set(siniflistesi_map)
    ad_map = dict(
        Personel.objects.filter(pk__in=tum_pkler).values_list("pk", "adi_soyadi")
    )
    gozetmenler = [
        {
            "ad":               ad_map.get(pk, "—"),
            "pk":               pk,
            "slot_sayisi":      gozetmen_slot_sayisi.get(pk, 0),
            "siniflistesi_adet": len(siniflistesi_map.get(pk, [])),
        }
        for pk in tum_pkler
    ]
    gozetmenler.sort(key=lambda g: g["ad"])

    return gozetmenler, siniflistesi_map
