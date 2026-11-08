"""Yıl kurulumu: bütün kurulların aktif eğitim yılı için iskelet olarak açılması ve otomatik üyeler."""

from django.db import transaction

from kurul.models import Kurul, KurulTuru
from kurul.services.uyelik import otomatik_uyeleri_uygula
from okul.models import Brans, Personel, SinifSube


def _kapsamlar(tur, egitim_yili):
    if tur.kapsam == KurulTuru.KAPSAM_SUBE:
        return [
            {"sinif_sube": ss}
            for ss in SinifSube.objects.order_by("sinif", "sube")
            if ss.acik_mi(egitim_yili)
        ]
    if tur.kapsam == KurulTuru.KAPSAM_BRANS:
        brans_idler = (
            Personel.objects.gorevde().filter(brans__isnull=False)
            .exclude(gorev_tipi__in=Personel.YONETICI_GOREVLERI)
            .values_list("brans_id", flat=True)
        )
        return [{"brans": b} for b in Brans.objects.filter(pk__in=brans_idler).order_by("ad")]
    return [{}]


@transaction.atomic
def yil_kurulumu(egitim_yili) -> dict:
    """Aktif bütün türler için yılın kurullarını yapılarıyla (iskelet) açar — var olanlara
    dokunmaz — ve eksik otomatik üyeleri ekler. Diğer kurulların üyeleri yapı formundan
    seçilir. Zümre başkanları kurulu en sona bırakılır, çünkü üyeleri zümrelerde seçilen
    başkanlardır. Açılan kurul ve eklenen üye sayılarını döner."""
    sonuc = {"acilan": 0, "otomatik_uye": 0}
    acilanlar = []
    for tur in KurulTuru.objects.filter(aktif=True):
        for kapsam in _kapsamlar(tur, egitim_yili):
            kurul, olustu = Kurul.objects.get_or_create(tur=tur, egitim_yili=egitim_yili, **kapsam)
            sonuc["acilan"] += olustu
            acilanlar.append(kurul)
    acilanlar.sort(key=lambda k: k.tur.otomatik_uyelik == KurulTuru.OTOMATIK_ZUMRE_BASKANLARI)
    for kurul in acilanlar:
        sonuc["otomatik_uye"] += otomatik_uyeleri_uygula(kurul)
    return sonuc


def acilmamis_turler(egitim_yili):
    """Bu yıl için hiç kurulu açılmamış aktif türler."""
    acik = Kurul.objects.filter(egitim_yili=egitim_yili).values_list("tur_id", flat=True)
    return KurulTuru.objects.filter(aktif=True).exclude(pk__in=acik)
