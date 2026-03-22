from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from devamsizlik.models import OgrenciDevamsizlik
from ogrenci.models import Ogrenci

from .models import OgrenciNobetGorevi

NOBETCI_ACIKLAMA = "Nöbetçi"
NOBET_DERS_SAATI = 0  # tüm gün için özel sabit


def _sinifsube_secenekleri():
    return [
        f"{s}/{sb}"
        for s, sb in Ogrenci.objects.values_list("sinif", "sube")
        .distinct()
        .order_by("sinif", "sube")
    ]


@login_required
def nobetci_form(request):
    bugun = timezone.localdate()
    tarih_str = request.GET.get("tarih") or request.POST.get("tarih", "")
    try:
        from datetime import date as dt_date

        secili_tarih = dt_date.fromisoformat(tarih_str.strip())
    except (ValueError, AttributeError):
        secili_tarih = bugun

    sinifsube = request.GET.get("sinifsube") or request.POST.get("sinifsube", "")

    ogrenciler = []
    secili_sinif = secili_sube = None
    if sinifsube:
        try:
            sinif_str, sube_str = sinifsube.split("/")
            secili_sinif = int(sinif_str.strip())
            secili_sube = sube_str.strip()
            ogrenciler = list(
                Ogrenci.objects.filter(sinif=secili_sinif, sube__iexact=secili_sube).order_by(
                    "okulno"
                )
            )
        except (ValueError, TypeError):
            pass

    # O gün + sınıf için kayıtlı nöbetçi öğrenci id'leri
    kayitli_ids = set()
    # Daha önce (başka tarihlerde) nöbet görmüş öğrenci id'leri → seçilemez
    onceki_nobet_ids = set()
    if secili_sinif and secili_sube:
        kayitli_ids = set(
            OgrenciNobetGorevi.objects.filter(
                tarih=secili_tarih,
                ogrenci__sinif=secili_sinif,
                ogrenci__sube__iexact=secili_sube,
            ).values_list("ogrenci_id", flat=True)
        )
        onceki_nobet_ids = (
            set(
                OgrenciNobetGorevi.objects.filter(
                    ogrenci__sinif=secili_sinif,
                    ogrenci__sube__iexact=secili_sube,
                )
                .exclude(tarih=secili_tarih)
                .values_list("ogrenci_id", flat=True)
            )
            - kayitli_ids
        )  # bugün zaten nöbetçiyse ayrıca engelleme

    if request.method == "POST":
        secili_ids = set(int(x) for x in request.POST.getlist("nobetci"))
        olusturan = request.user.get_full_name() or request.user.username

        with transaction.atomic():
            # Mevcut kayıtları temizle (bu tarih + sınıf/şube)
            if secili_sinif and secili_sube:
                eski_gorev_ids = OgrenciNobetGorevi.objects.filter(
                    tarih=secili_tarih,
                    ogrenci__sinif=secili_sinif,
                    ogrenci__sube__iexact=secili_sube,
                ).values_list("ogrenci_id", flat=True)

                OgrenciDevamsizlik.objects.filter(
                    ogrenci_id__in=eski_gorev_ids,
                    tarih=secili_tarih,
                    ders_saati=NOBET_DERS_SAATI,
                    aciklama=NOBETCI_ACIKLAMA,
                ).delete()

                OgrenciNobetGorevi.objects.filter(
                    tarih=secili_tarih,
                    ogrenci__sinif=secili_sinif,
                    ogrenci__sube__iexact=secili_sube,
                ).delete()

            # Yeni kayıtları oluştur
            for ogr in ogrenciler:
                if ogr.pk in secili_ids:
                    OgrenciNobetGorevi.objects.create(
                        ogrenci=ogr,
                        tarih=secili_tarih,
                        olusturan=olusturan,
                    )
                    OgrenciDevamsizlik.objects.update_or_create(
                        ogrenci=ogr,
                        tarih=secili_tarih,
                        ders_saati=NOBET_DERS_SAATI,
                        defaults={
                            "ders_adi": "Nöbet Görevi",
                            "ogretmen_adi": olusturan,
                            "aciklama": NOBETCI_ACIKLAMA,
                        },
                    )

        messages.success(request, f"{len(secili_ids)} öğrenci nöbetçi olarak kaydedildi.")
        return redirect(f"{request.path}?tarih={secili_tarih}&sinifsube={sinifsube}")

    return render(
        request,
        "ogrencinobet/nobetci_form.html",
        {
            "secili_tarih": secili_tarih,
            "bugun": bugun,
            "sinifsube_secenekleri": _sinifsube_secenekleri(),
            "secili_sinifsube": sinifsube,
            "ogrenciler": ogrenciler,
            "kayitli_ids": kayitli_ids,
            "onceki_nobet_ids": onceki_nobet_ids,
        },
    )
