"""Bir eğitim-öğretim yılının seçmeli ders tanımlarını (sınıf toplam saat, zorunlu
dersler, seçmeli ders grupları, alan tanımları) bir sonraki yıla kopyalar.

Her fonksiyon "Önceki Dönemden Getir" butonlarının servis katmanıdır — var olanı
bozmadan eksikleri ekler (SinifSeviyeToplamSaat hariç, o her zaman tek satır/seviye
olduğu için önceki yılın değeriyle güncellenir).
"""

from django.db import transaction


def onceki_egitim_yili(hedef_yil):
    """`hedef_yil`den kronolojik olarak bir önceki EgitimOgretimYili'ni döner (yoksa None)."""
    from okul.models import EgitimOgretimYili

    if not hedef_yil:
        return None
    return (
        EgitimOgretimYili.objects.filter(egitim_baslangic__lt=hedef_yil.egitim_baslangic)
        .order_by("-egitim_baslangic")
        .first()
    )


def sinif_toplam_saat_kopyala(onceki_yil, hedef_yil):
    from ..models import SinifSeviyeToplamSaat

    guncellenen = 0
    with transaction.atomic():
        for kayit in SinifSeviyeToplamSaat.objects.filter(egitim_yili=onceki_yil):
            SinifSeviyeToplamSaat.objects.update_or_create(
                egitim_yili=hedef_yil,
                sinif_seviyesi=kayit.sinif_seviyesi,
                defaults={"haftalik_toplam_saat": kayit.haftalik_toplam_saat},
            )
            guncellenen += 1
    return guncellenen


def ortak_ders_kopyala(onceki_yil, hedef_yil):
    from ..models import OrtakDers

    mevcut_adlar = set(
        OrtakDers.objects.filter(egitim_yili=hedef_yil).values_list("sinif_seviyesi", "ders_adi")
    )
    eklenen = atlanan = 0
    with transaction.atomic():
        for kayit in OrtakDers.objects.filter(egitim_yili=onceki_yil).prefetch_related("branslar"):
            if (kayit.sinif_seviyesi, kayit.ders_adi) in mevcut_adlar:
                atlanan += 1
                continue
            yeni = OrtakDers.objects.create(
                egitim_yili=hedef_yil,
                sinif_seviyesi=kayit.sinif_seviyesi,
                ders_adi=kayit.ders_adi,
                haftalik_saat=kayit.haftalik_saat,
                sira=kayit.sira,
            )
            yeni.branslar.set(kayit.branslar.all())
            eklenen += 1
    return eklenen, atlanan


def secmeli_grup_kopyala(onceki_yil, hedef_yil):
    from ..models import SecmeliDers, SecmeliDersGrubu

    mevcut_gruplar = set(
        SecmeliDersGrubu.objects.filter(egitim_yili=hedef_yil).values_list("sinif_seviyesi", "adi")
    )
    eklenen_grup = eklenen_ders = atlanan_grup = 0
    with transaction.atomic():
        for grup in SecmeliDersGrubu.objects.filter(egitim_yili=onceki_yil):
            if (grup.sinif_seviyesi, grup.adi) in mevcut_gruplar:
                atlanan_grup += 1
                continue
            yeni_grup = SecmeliDersGrubu.objects.create(
                egitim_yili=hedef_yil,
                sinif_seviyesi=grup.sinif_seviyesi,
                adi=grup.adi,
                zorunlu_grup=grup.zorunlu_grup,
                sira=grup.sira,
            )
            eklenen_grup += 1
            for ders in grup.dersler.prefetch_related("branslar"):
                yeni_ders = SecmeliDers.objects.create(
                    grup=yeni_grup,
                    ders_adi=ders.ders_adi,
                    saat_secenekleri=ders.saat_secenekleri,
                    sira=ders.sira,
                    aktif=ders.aktif,
                )
                yeni_ders.branslar.set(ders.branslar.all())
                eklenen_ders += 1
    return eklenen_grup, eklenen_ders, atlanan_grup


def alan_kopyala(onceki_yil, hedef_yil):
    from ..models import Alan, AlanDers, SecmeliDers

    mevcut_alanlar = set(
        Alan.objects.filter(egitim_yili=hedef_yil).values_list("sinif_seviyesi", "adi")
    )
    eklenen_alan = eklenen_ders = atlanan_alan = eslesmeyen_ders = 0
    with transaction.atomic():
        for alan in Alan.objects.filter(egitim_yili=onceki_yil):
            if (alan.sinif_seviyesi, alan.adi) in mevcut_alanlar:
                atlanan_alan += 1
                continue
            yeni_alan = Alan.objects.create(
                egitim_yili=hedef_yil,
                sinif_seviyesi=alan.sinif_seviyesi,
                adi=alan.adi,
                sira=alan.sira,
            )
            eklenen_alan += 1
            for alan_ders in AlanDers.objects.filter(alan=alan).select_related("ders", "ders__grup"):
                eski_ders = alan_ders.ders
                yeni_ders = SecmeliDers.objects.filter(
                    grup__egitim_yili=hedef_yil,
                    grup__sinif_seviyesi=eski_ders.grup.sinif_seviyesi,
                    grup__adi=eski_ders.grup.adi,
                    ders_adi=eski_ders.ders_adi,
                ).first()
                if not yeni_ders:
                    eslesmeyen_ders += 1
                    continue
                AlanDers.objects.create(
                    alan=yeni_alan, ders=yeni_ders, secilen_saat=alan_ders.secilen_saat
                )
                eklenen_ders += 1
    return eklenen_alan, eklenen_ders, atlanan_alan, eslesmeyen_ders
