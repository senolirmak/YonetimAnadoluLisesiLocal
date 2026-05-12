"""
DB sorgu yardımcıları — HTTP katmanından bağımsız saf fonksiyonlar.

Performans notları:
  - ders_programi_by_ogretmenler: N ayrı sorgu yerine tek IN sorgusu (N+1 → 1)
  - kayitli_atamalar_ve_atamayanlar: list() ile önbellekle, exists()+iter çifti yok
  - en_son_kayit_dt: iki tabloyu 2 sorguda çözer, tekrar sorgu açmaz
"""
from datetime import datetime, time

from django.db.models import Q
from django.utils import timezone

from dersprogrami.models import DersProgrami
from personeldevamsizlik.models import Devamsizlik
from ...models import NobetAtanamayan, NobetGecmisi, NobetGorevi


DAYS_MAP = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


def aktif_program_tarihi(target_date):
    t = (
        DersProgrami.objects.filter(uygulama_tarihi__lte=target_date)
        .order_by("-uygulama_tarihi")
        .values_list("uygulama_tarihi", flat=True)
        .first()
    )
    if not t:
        t = (
            DersProgrami.objects.order_by("-uygulama_tarihi")
            .values_list("uygulama_tarihi", flat=True)
            .first()
        )
    return t


def aktif_gorev_tarihi(target_date):
    return (
        NobetGorevi.objects.filter(uygulama_tarihi__lte=target_date)
        .order_by("-uygulama_tarihi")
        .values_list("uygulama_tarihi", flat=True)
        .first()
    )


def ders_programi_by_ogretmenler(ogretmen_ids, day_name_en, program_date):
    """
    Tüm öğretmenlerin ders programını TEK sorguda çeker.
    Döndürür: {ogretmen_id: {ders_saati_no: sinif_sube_str}}
    """
    qs = DersProgrami.objects.filter(
        ogretmen__id__in=ogretmen_ids,
        gun=day_name_en,
        uygulama_tarihi=program_date,
    ).select_related("sinif_sube", "ders_saati", "ogretmen")

    result = {}
    for ders in qs:
        if not (ders.sinif_sube and ders.ders_saati):
            continue
        result.setdefault(ders.ogretmen.id, {})[ders.ders_saati.derssaati_no] = str(ders.sinif_sube)
    return result


def aktif_devamsizliklar(target_date, sadece_gorevlendirilebilir=False):
    """Verilen tarihe ait aktif devamsızlık kayıtlarını liste olarak döner."""
    qs = (
        Devamsizlik.objects.filter(baslangic_tarihi__lte=target_date)
        .filter(Q(bitis_tarihi__gte=target_date) | Q(bitis_tarihi__isnull=True))
        .select_related("ogretmen__personel")
    )
    if sadece_gorevlendirilebilir:
        qs = qs.filter(gorevlendirme_yapilsin=True)
    return list(qs)


def en_son_kayit_dt(target_date):
    """
    target_date için en son kaydedilen atama datetime'ını döner, yoksa None.
    İki tabloyu 2 sorguda kontrol eder; exists()+iter pattern'ını önler.
    """
    start = timezone.make_aware(datetime.combine(target_date, time.min))
    end   = timezone.make_aware(datetime.combine(target_date, time.max))
    rec = NobetGecmisi.objects.filter(tarih__range=[start, end]).order_by("-tarih").first()
    un  = NobetAtanamayan.objects.filter(tarih__range=[start, end]).order_by("-tarih").first()
    candidates = [x.tarih for x in (rec, un) if x]
    return max(candidates) if candidates else None


def kayitli_atamalar_ve_atamayanlar(start_dt, end_dt):
    """
    Her iki tabloyu list() ile önbelleğe alarak döner.
    exists() + iterasyon çifti yerine tek değerlendirme.
    """
    assigns = list(
        NobetGecmisi.objects.filter(tarih__range=[start_dt, end_dt])
        .select_related("ogretmen__personel")
    )
    unassigns = list(
        NobetAtanamayan.objects.filter(tarih__range=[start_dt, end_dt])
        .select_related("ogretmen__personel")
    )
    return assigns, unassigns


def gecmis_tarihler(target_date):
    """Aynı haftanın günündeki önceki 5 kayıt tarihini döner."""
    wd_map = {0: 2, 1: 3, 2: 4, 3: 5, 4: 6, 5: 7, 6: 1}
    d_wd = wd_map.get(target_date.weekday(), 2)
    d1 = set(NobetGecmisi.objects.filter(tarih__week_day=d_wd).values_list("tarih", flat=True))
    d2 = set(NobetAtanamayan.objects.filter(tarih__week_day=d_wd).values_list("tarih", flat=True))
    return sorted(d1 | d2, reverse=True)[:5]
