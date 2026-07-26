"""Nöbet Listesi — aktif (varsayılan) ya da geçmiş bir eğitim-öğretim yılı/dönem için
haftalık nöbet görevlerinin salt-okunur listesi."""

from django.shortcuts import render

from ..models import NobetGorevi
from .permissions import ust_yonetici_required


@ust_yonetici_required
def nobet_gorevi_listesi(request):
    from okul.models import EgitimOgretimYili, OkulDonem

    yil_id = request.GET.get("yil", "").strip()
    donem_id = request.GET.get("donem", "").strip()
    secili_yil = EgitimOgretimYili.objects.filter(pk=yil_id).first() if yil_id else None
    secili_donem = OkulDonem.objects.filter(pk=donem_id).first() if donem_id else None

    if secili_yil and secili_donem:
        kayitlar = NobetGorevi.objects.filter(egitim_yili=secili_yil, donem=secili_donem)
        gecmis_donem_secili = True
    else:
        kayitlar = NobetGorevi.objects.aktif()
        gecmis_donem_secili = False

    kayitlar = kayitlar.select_related("ogretmen__personel", "nobet_yeri").order_by(
        "ogretmen__personel__adi_soyadi", "nobet_gun"
    )

    donemler = (
        NobetGorevi.objects.exclude(egitim_yili__isnull=True)
        .values("egitim_yili_id", "egitim_yili__egitim_yili", "donem_id", "donem__donem")
        .distinct()
        .order_by("-egitim_yili__egitim_yili", "donem__donem")
    )

    context = {
        "title": "Nöbet Listesi",
        "kayitlar": kayitlar,
        "donemler": donemler,
        "secili_yil_id": yil_id,
        "secili_donem_id": donem_id,
        "gecmis_donem_secili": gecmis_donem_secili,
    }
    return render(request, "nobet/nobet_gorevi_listesi.html", context)
