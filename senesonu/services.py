"""Sene sonu öğrenci sınıf/şube atlatma iş mantığı.

`gecis_olustur` bir taslak (SeneSonuGecisi + satırları) oluşturur, henüz `ogrenci.Ogrenci`
kayıtlarına dokunmaz. `gecis_uygula` taslağı kalıcı hale getirir.
"""

from django.db import transaction
from django.utils import timezone

from .models import SeneSonuGecisi, SeneSonuOgrenciGecisi


def _yeni_subeler_belirle(sinif_no, adet):
    """`sinif_no` seviyesi için `adet` kadar şube harfi belirler.

    Önce o sınıf seviyesindeki KAPALI şubeler (varsa, harf sırasına göre) yeniden
    kullanılır; kalan ihtiyaç için henüz hiç kullanılmayan (ne açık ne kapalı bir
    kaydı olan) sıradaki yeni harfler üretilir. Şubelerin fiilen açılması/oluşturulması
    `gecis_uygula` içinde yapılır — bu fonksiyon yalnızca hangi harflerin kullanılacağını
    belirler.
    """
    from okul.models import SinifSube
    from secmelidersler.services.ders_dagilimi import HARFLER

    kapali_harfler = list(
        SinifSube.objects.filter(sinif=sinif_no, acik=False)
        .order_by("sube")
        .values_list("sube", flat=True)
    )
    kullanimda = set(SinifSube.objects.filter(sinif=sinif_no).values_list("sube", flat=True))

    secilen = kapali_harfler[:adet]
    for harf in HARFLER:
        if len(secilen) >= adet:
            break
        if harf not in kullanimda and harf not in secilen:
            secilen.append(harf)
    return secilen


def gecis_olustur(eski_yil, yeni_yil, kullanici=None):
    from ogrenci.models import Ogrenci
    from secmelidersler.models import OgrenciSinifTekrari
    from secmelidersler.services.ders_dagilimi import plan_sinif_dagilimi

    with transaction.atomic():
        gecis = SeneSonuGecisi.objects.create(
            eski_egitim_yili=eski_yil,
            yeni_egitim_yili=yeni_yil,
            olusturan=kullanici,
        )

        satirlar = []

        def _sinif_tekrari_ids(sinif_no):
            return set(
                OgrenciSinifTekrari.objects.filter(
                    ogrenci__aktif=True,
                    ogrenci__sinif=sinif_no,
                ).values_list("ogrenci_id", flat=True)
            )

        # 9 → 10 ve 11 → 12: şube aynı kalır.
        for eski_sinif, yeni_sinif in ((9, 10), (11, 12)):
            tekrar_ids = _sinif_tekrari_ids(eski_sinif)
            for ogr in Ogrenci.objects.filter(aktif=True, sinif=eski_sinif).order_by("okulno"):
                if ogr.pk in tekrar_ids:
                    satirlar.append(SeneSonuOgrenciGecisi(
                        gecis=gecis, ogrenci=ogr,
                        eski_sinif=eski_sinif, eski_sube=ogr.sube,
                        yeni_sinif=eski_sinif, yeni_sube=ogr.sube,
                        durum="sinif_tekrari",
                    ))
                else:
                    satirlar.append(SeneSonuOgrenciGecisi(
                        gecis=gecis, ogrenci=ogr,
                        eski_sinif=eski_sinif, eski_sube=ogr.sube,
                        yeni_sinif=yeni_sinif, yeni_sube=ogr.sube,
                        durum="normal",
                    ))

        # 10 → 11: alan bazlı hesaplanan şube. `_sube_dagit` harfleri sadece sıra/ordinal
        # olarak üretir (kapalı/açık şubelerden habersiz) — burada gerçek harflere eşlenir:
        # önce kapalı şubeler yeniden kullanılır, sonra sıradaki yeni harf(ler) üretilir.
        plan = plan_sinif_dagilimi(10, 11, eski_yil)
        toplam_sube_ihtiyaci = sum(len(g["subeler"]) for g in plan["alan_gruplari"])
        gercek_harfler = iter(_yeni_subeler_belirle(11, toplam_sube_ihtiyaci))
        for grup in plan["alan_gruplari"]:
            for sube in grup["subeler"]:
                gercek_harf = next(gercek_harfler)
                for ogr in sube["ogrenciler"]:
                    satirlar.append(SeneSonuOgrenciGecisi(
                        gecis=gecis, ogrenci=ogr,
                        eski_sinif=10, eski_sube=ogr.sube,
                        yeni_sinif=11, yeni_sube=gercek_harf,
                        durum="normal",
                    ))
        for ogr in plan["alan_yok"]:
            satirlar.append(SeneSonuOgrenciGecisi(
                gecis=gecis, ogrenci=ogr,
                eski_sinif=10, eski_sube=ogr.sube,
                yeni_sinif=11, yeni_sube="",
                durum="inceleme_gerekli",
            ))
        for ogr in plan["sinif_tekrari"]:
            satirlar.append(SeneSonuOgrenciGecisi(
                gecis=gecis, ogrenci=ogr,
                eski_sinif=10, eski_sube=ogr.sube,
                yeni_sinif=10, yeni_sube=ogr.sube,
                durum="sinif_tekrari",
            ))

        # 12. sınıf: mezun.
        tekrar_ids_12 = _sinif_tekrari_ids(12)
        for ogr in Ogrenci.objects.filter(aktif=True, sinif=12).order_by("okulno"):
            if ogr.pk in tekrar_ids_12:
                satirlar.append(SeneSonuOgrenciGecisi(
                    gecis=gecis, ogrenci=ogr,
                    eski_sinif=12, eski_sube=ogr.sube,
                    yeni_sinif=12, yeni_sube=ogr.sube,
                    durum="sinif_tekrari",
                ))
            else:
                satirlar.append(SeneSonuOgrenciGecisi(
                    gecis=gecis, ogrenci=ogr,
                    eski_sinif=12, eski_sube=ogr.sube,
                    yeni_sinif=None, yeni_sube="",
                    durum="mezun",
                ))

        SeneSonuOgrenciGecisi.objects.bulk_create(satirlar)

    return gecis


def gecis_uygula(gecis):
    from ogrenci.models import Ogrenci
    from okul.models import OkulBilgi, SinifSube

    if gecis.uygulandi:
        raise ValueError("Bu geçiş zaten uygulanmış.")

    satirlar = list(gecis.ogrenci_gecisleri.select_related("ogrenci"))
    cozulmemis = [s for s in satirlar if s.durum == "inceleme_gerekli" and not s.yeni_sube]
    if cozulmemis:
        raise ValueError(
            f"{len(cozulmemis)} öğrencinin şubesi henüz belirlenmedi — uygulamadan önce "
            "'İnceleme Gerekli' satırları düzenleyin."
        )

    gerekli_sinif_sube = {
        (s.yeni_sinif, s.yeni_sube) for s in satirlar if s.durum != "mezun" and s.yeni_sube
    }

    with transaction.atomic():
        # Hedef şube yoksa oluşturulur; kapalıysa sene sonu geçişi kapsamında yeniden açılır.
        for sinif_no, sube in gerekli_sinif_sube:
            kayit, olusturuldu = SinifSube.objects.get_or_create(
                sinif=sinif_no, sube=sube, defaults={"acik": True}
            )
            if not olusturuldu and not kayit.acik:
                kayit.acik = True
                kayit.save(update_fields=["acik"])

        mezun_ids = [s.ogrenci_id for s in satirlar if s.durum == "mezun"]
        if mezun_ids:
            Ogrenci.objects.filter(pk__in=mezun_ids).update(aktif=False)

        guncellenecek = [s for s in satirlar if s.durum != "mezun"]
        ogrenciler = []
        for satir in guncellenecek:
            ogr = satir.ogrenci
            ogr.sinif = satir.yeni_sinif
            ogr.sube = satir.yeni_sube
            ogrenciler.append(ogr)
        if ogrenciler:
            Ogrenci.objects.bulk_update(ogrenciler, ["sinif", "sube"])

        okul = OkulBilgi.get()
        okul.okul_egtyil = gecis.yeni_egitim_yili
        okul.okul_donem = gecis.yeni_egitim_yili.donemleri.filter(donem=1).first()
        okul.save(update_fields=["okul_egtyil", "okul_donem"])

        gecis.uygulandi = True
        gecis.uygulama_zamani = timezone.now()
        gecis.save(update_fields=["uygulandi", "uygulama_zamani"])

    return gecis
