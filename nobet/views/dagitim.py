from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import render
from django.utils import timezone

from dersprogrami.models import DersProgrami
from personeldevamsizlik.models import Devamsizlik
from utility.services.main_services import IstatistikService

from ..forms import NobetDagitimForm
from ..models import GunlukNobetCizelgesi, NobetGorevi, NobetOgretmen
from ..services.pdf_rapor import get_report_header_info as _get_report_header_info
from .permissions import (
    is_mudur_yardimcisi,
    is_yonetici,
    mudur_yardimcisi_required,
)

# ─────────────────────────────────────────────
# Paylaşılan yardımcı fonksiyonlar
# ─────────────────────────────────────────────

_TR_GUNLER = {
    0: "Pazartesi",
    1: "Salı",
    2: "Çarşamba",
    3: "Perşembe",
    4: "Cuma",
    5: "Cumartesi",
    6: "Pazar",
}


def _gun_adi_tr(date):
    return _TR_GUNLER[date.weekday()]



# ─────────────────────────────────────────────
# Haftalık Nöbet Dağıtımı
# ─────────────────────────────────────────────


@login_required
def nobet_dagitim(request):
    if not is_yonetici(request.user):
        raise PermissionDenied
    son_kayit = NobetGorevi.objects.order_by("-uygulama_tarihi").first()
    if son_kayit:
        ref_date = son_kayit.uygulama_tarihi
    else:
        ref_date = timezone.localdate()

    pazartesi = ref_date - timedelta(days=ref_date.weekday())

    if request.method == "POST":
        form = NobetDagitimForm(request.POST)
        if form.is_valid():
            pazartesi = form.cleaned_data["baslangic_tarihi"]

        if request.method == "POST" and any(
            k in request.POST for k in ["rotasyon_onizle", "rotasyon_kaydet", "rotasyon_iptal"]
        ):
            if not is_mudur_yardimcisi(request.user):
                raise PermissionDenied

        if "rotasyon_onizle" in request.POST:
            rotation_updates = {}
            gun_map = {
                "Monday": "Pazartesi",
                "Tuesday": "Salı",
                "Wednesday": "Çarşamba",
                "Thursday": "Perşembe",
                "Friday": "Cuma",
            }
            for gun in gun_map.keys():
                gunluk_gorevler = list(
                    NobetGorevi.objects.aktif().filter(nobet_gun=gun)
                    .select_related("nobet_yeri")
                    .order_by("nobet_yeri__ad")
                )

                if not gunluk_gorevler:
                    continue

                yerler = [g.nobet_yeri.ad if g.nobet_yeri else "" for g in gunluk_gorevler]

                if len(yerler) < 2:
                    continue

                yeni_yerler = yerler[1:] + yerler[:1]

                for gorev, yeni_yer in zip(gunluk_gorevler, yeni_yerler):
                    rotation_updates[str(gorev.pk)] = yeni_yer

            request.session["rotation_preview"] = rotation_updates
            messages.warning(
                request,
                "Rotasyon önizlemesi oluşturuldu. Tabloyu kontrol edip 'Değişiklikleri Kaydet' butonuna basınız.",
            )

        elif "rotasyon_kaydet" in request.POST:
            updates = request.session.get("rotation_preview", {})
            if updates:
                from nobet.models import NobetYerleri
                yer_map = {y.ad: y.pk for y in NobetYerleri.objects.filter(ad__in=updates.values())}
                with transaction.atomic():
                    for gorev_id, yeni_yer_ad in updates.items():
                        yer_pk = yer_map.get(yeni_yer_ad)
                        if yer_pk:
                            NobetGorevi.objects.filter(id=gorev_id).update(nobet_yeri_id=yer_pk)

                del request.session["rotation_preview"]
                messages.success(request, "Nöbet yerleri rotasyonu başarıyla kaydedildi.")
            else:
                messages.error(request, "Kaydedilecek rotasyon verisi bulunamadı.")

        elif "rotasyon_iptal" in request.POST:
            if "rotation_preview" in request.session:
                del request.session["rotation_preview"]
                messages.info(request, "Rotasyon işlemi iptal edildi.")

    else:
        form = NobetDagitimForm(initial={"baslangic_tarihi": pazartesi})

    rotation_preview = request.session.get("rotation_preview", None)

    cuma = pazartesi + timedelta(days=4)

    nobetler = NobetGorevi.objects.aktif().select_related("nobet_yeri", "ogretmen__personel")

    nobet_yerleri = sorted(list(set(nobetler.values_list("nobet_yeri__ad", flat=True))))

    gun_map = {
        "Monday": "Pazartesi",
        "Tuesday": "Salı",
        "Wednesday": "Çarşamba",
        "Thursday": "Perşembe",
        "Friday": "Cuma",
    }
    tr_gunler = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]

    veri_matrisi = {yer: {g: [] for g in tr_gunler} for yer in nobet_yerleri}

    for nobet in nobetler:
        yer = nobet.nobet_yeri.ad if nobet.nobet_yeri else ""

        if rotation_preview and str(nobet.pk) in rotation_preview:
            yer = rotation_preview[str(nobet.pk)]

        gun_tr = gun_map.get(nobet.nobet_gun, nobet.nobet_gun)

        if yer in veri_matrisi and gun_tr in veri_matrisi[yer]:
            veri_matrisi[yer][gun_tr].append(nobet.ogretmen.personel.adi_soyadi)

    tablo_satirlari = []
    for yer in nobet_yerleri:
        satir = {"yer": yer, "hucreler": []}
        for gun in tr_gunler:
            satir["hucreler"].append(veri_matrisi[yer][gun])
        tablo_satirlari.append(satir)

    context = {
        "title": "Nöbet Dağıtım Çizelgesi",
        "form": form,
        "gunler": tr_gunler,
        "tablo_satirlari": tablo_satirlari,
        "baslangic": pazartesi,
        "bitis": cuma,
        "is_preview": rotation_preview is not None,
    }

    return render(request, "nobet_dagitim.html", context)


# DevamsizlikListView, CreateView, UpdateView, DeleteView → personeldevamsizlik app'e taşındı.


# ─────────────────────────────────────────────
# Manuel Dağıtım
# ─────────────────────────────────────────────


@mudur_yardimcisi_required
def manuel_dagitim(request):
    from datetime import datetime, time

    target_date = timezone.localdate()
    view_datetime = None

    if request.GET.get("tarih"):
        tarih_str = request.GET.get("tarih")
        try:
            dt_obj = datetime.strptime(tarih_str, "%Y-%m-%d %H:%M:%S")
            target_date = dt_obj.date()
            view_datetime = dt_obj
        except ValueError:
            try:
                target_date = datetime.strptime(tarih_str, "%Y-%m-%d").date()
            except ValueError:
                pass

    if request.method == "GET":
        if view_datetime:
            check_start = timezone.make_aware(view_datetime.replace(microsecond=0))
            check_end = timezone.make_aware(view_datetime.replace(microsecond=999999))
        else:
            check_start = timezone.make_aware(datetime.combine(target_date, time.min))
            check_end = timezone.make_aware(datetime.combine(target_date, time.max))

        from ..models import NobetAtanamayan, NobetGecmisi

        has_assignments = NobetGecmisi.objects.filter(
            tarih__range=[check_start, check_end]
        ).exists()
        has_unassigned = NobetAtanamayan.objects.filter(
            tarih__range=[check_start, check_end]
        ).exists()

        if not (has_assignments or has_unassigned):
            messages.warning(
                request,
                f"{target_date.strftime('%d.%m.%Y')} tarihi için kayıtlı dağıtım bulunamadı. Lütfen önce Otomatik Dağıtım sayfasından dağıtım yapıp kaydediniz.",
            )
            from django.shortcuts import redirect

            return redirect(f"/ders-doldurma/?tarih={target_date.strftime('%Y-%m-%d')}")

    if request.method == "POST" and "kaydet" in request.POST:
        from django.shortcuts import redirect

        from ..models import NobetAtanamayan, NobetGecmisi

        try:
            date_str = request.POST.get("target_date_hidden")
            save_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_dt = timezone.make_aware(datetime.combine(save_date, time.min))
            end_dt = timezone.make_aware(datetime.combine(save_date, time.max))

            days_map = {
                0: "Monday",
                1: "Tuesday",
                2: "Wednesday",
                3: "Thursday",
                4: "Friday",
                5: "Saturday",
                6: "Sunday",
            }
            day_name_en = days_map[save_date.weekday()]

            devamsizlar_q = Devamsizlik.objects.filter(
                baslangic_tarihi__lte=save_date, bitis_tarihi__gte=save_date
            ).select_related("ogretmen__personel")
            program_date_q = (
                DersProgrami.objects.filter(uygulama_tarihi__lte=save_date)
                .order_by("-uygulama_tarihi")
                .values_list("uygulama_tarihi", flat=True)
                .first()
            )

            all_empty_lessons = []
            if program_date_q:
                for devamsiz in devamsizlar_q:
                    p_id = devamsiz.ogretmen.personel.pk
                    allowed_hours = (
                        [int(h) for h in devamsiz.ders_saatleri.split(",") if h.strip().isdigit()]
                        if devamsiz.ders_saatleri
                        else list(range(1, 9))
                    )
                    dersler = DersProgrami.objects.filter(
                        ogretmen_id=p_id,
                        gun=day_name_en,
                        uygulama_tarihi=program_date_q,
                        ders_saati__derssaati_no__in=allowed_hours,
                    ).select_related("sinif_sube", "ders_saati")
                    for ders in dersler:
                        ds_no = ders.ders_saati.derssaati_no if ders.ders_saati else None
                        if ds_no and 1 <= ds_no <= 8 and ders.sinif_sube:
                            sinif_label = str(ders.sinif_sube)
                            all_empty_lessons.append(
                                {
                                    "saat": ds_no,
                                    "sinif": sinif_label,
                                    "devamsiz_id": p_id,
                                    "unique_key": f"{ds_no}_{p_id}|{sinif_label}",
                                }
                            )

            NobetGecmisi.objects.filter(tarih__range=[start_dt, end_dt]).delete()
            NobetAtanamayan.objects.filter(tarih__range=[start_dt, end_dt]).delete()

            kayit_zamani = timezone.localtime().replace(
                year=save_date.year, month=save_date.month, day=save_date.day
            )
            assigned_lesson_keys = set()

            for key, value in request.POST.items():
                if key.startswith("cell_") and value:
                    parts = key.split("_")
                    nobetci_id = int(parts[1])
                    saat = int(parts[2])

                    val_parts = value.split("|")
                    devamsiz_id = int(val_parts[0])
                    sinif_adi = val_parts[1]

                    ogretmen = (
                        NobetOgretmen.objects.filter(
                            personel_id=nobetci_id, uygulama_tarihi__lte=save_date
                        )
                        .order_by("-uygulama_tarihi")
                        .first()
                    )

                    if ogretmen:
                        NobetGecmisi.objects.create(
                            saat=saat,
                            sinif=sinif_adi,
                            devamsiz=devamsiz_id,
                            tarih=kayit_zamani,
                            atandi=1,
                            ogretmen=ogretmen,
                        )
                        assigned_lesson_keys.add(f"{saat}_{value}")

            for lesson in all_empty_lessons:
                if lesson["unique_key"] not in assigned_lesson_keys:
                    abs_teacher = (
                        NobetOgretmen.objects.filter(
                            personel_id=lesson["devamsiz_id"], uygulama_tarihi__lte=save_date
                        )
                        .order_by("-uygulama_tarihi")
                        .first()
                    )
                    if abs_teacher:
                        NobetAtanamayan.objects.create(
                            saat=lesson["saat"],
                            sinif=lesson["sinif"],
                            tarih=kayit_zamani,
                            atandi=0,
                            ogretmen=abs_teacher,
                        )

            try:
                istatistik_service = IstatistikService()
                istatistik_service.hesapla_ve_kaydet()
            except Exception as e:
                print(f"İstatistik güncelleme hatası: {e}")

            messages.success(
                request, f"{save_date.strftime('%d.%m.%Y')} tarihi için manuel dağıtım güncellendi."
            )
            return redirect(f"{request.path}?tarih={save_date.strftime('%Y-%m-%d')}")

        except Exception as e:
            messages.error(request, f"Hata oluştu: {e}")

    from datetime import datetime, time

    days_map = {
        0: "Monday",
        1: "Tuesday",
        2: "Wednesday",
        3: "Thursday",
        4: "Friday",
        5: "Saturday",
        6: "Sunday",
    }
    day_name_en = days_map[target_date.weekday()]

    gorev_date = (
        NobetGorevi.objects.filter(uygulama_tarihi__lte=target_date)
        .order_by("-uygulama_tarihi")
        .values_list("uygulama_tarihi", flat=True)
        .first()
    )

    nobetciler = []

    gunluk_degisiklikler = dict(
        GunlukNobetCizelgesi.objects.filter(tarih=target_date).values_list(
            "ogretmen_id", "nobet_yeri"
        )
    )

    if gorev_date:
        nobet_gorevleri = (
            NobetGorevi.objects.filter(uygulama_tarihi=gorev_date, nobet_gun=day_name_en)
            .select_related("ogretmen__personel", "nobet_yeri")
            .order_by("nobet_yeri__ad")
        )
        for gorev in nobet_gorevleri:
            yer = gunluk_degisiklikler.get(
                gorev.ogretmen.pk, gorev.nobet_yeri.ad if gorev.nobet_yeri else ""
            )
            nobetciler.append(
                {
                    "id": gorev.ogretmen.personel.pk,
                    "ad": gorev.ogretmen.personel.adi_soyadi,
                    "yer": yer,
                }
            )

    start_day = timezone.make_aware(datetime.combine(target_date, time.min))
    end_day = timezone.make_aware(datetime.combine(target_date, time.max))

    devamsizlar = Devamsizlik.objects.filter(
        baslangic_tarihi__lte=target_date, bitis_tarihi__gte=target_date
    ).select_related("ogretmen__personel")

    bos_dersler_havuzu = {i: [] for i in range(1, 9)}

    program_date = (
        DersProgrami.objects.filter(uygulama_tarihi__lte=target_date)
        .order_by("-uygulama_tarihi")
        .values_list("uygulama_tarihi", flat=True)
        .first()
    )

    if program_date:
        for devamsiz in devamsizlar:
            p_id = devamsiz.ogretmen.personel.pk
            p_ad = devamsiz.ogretmen.personel.adi_soyadi

            allowed_hours = (
                [int(h) for h in devamsiz.ders_saatleri.split(",") if h.strip().isdigit()]
                if devamsiz.ders_saatleri
                else list(range(1, 9))
            )

            dersler = DersProgrami.objects.filter(
                ogretmen_id=p_id,
                gun=day_name_en,
                uygulama_tarihi=program_date,
                ders_saati__derssaati_no__in=allowed_hours,
            ).select_related("sinif_sube", "ders_saati")

            for ders in dersler:
                ds_no = ders.ders_saati.derssaati_no if ders.ders_saati else None
                if ds_no and 1 <= ds_no <= 8 and ders.sinif_sube:
                    sinif_label = str(ders.sinif_sube)
                    bos_dersler_havuzu[ds_no].append(
                        {
                            "val": f"{p_id}|{sinif_label}",
                            "label": f"{sinif_label} ({p_ad})",
                            "sort_key": p_ad,
                        }
                    )

        for i in range(1, 9):
            bos_dersler_havuzu[i].sort(key=lambda x: x["sort_key"])

    tablo_satirlari = []

    if view_datetime:
        atama_start = timezone.make_aware(view_datetime.replace(microsecond=0))
        atama_end = timezone.make_aware(view_datetime.replace(microsecond=999999))
    else:
        from ..models import NobetGecmisi

        latest = (
            NobetGecmisi.objects.filter(tarih__range=[start_day, end_day])
            .order_by("-tarih")
            .first()
        )
        if latest:
            atama_start = latest.tarih.replace(microsecond=0)
            atama_end = latest.tarih.replace(microsecond=999999)
        else:
            atama_start = start_day
            atama_end = end_day

    from ..models import NobetGecmisi

    mevcut_atamalar = NobetGecmisi.objects.filter(
        tarih__range=[atama_start, atama_end]
    ).select_related("ogretmen__personel")
    atama_map = {
        (k.ogretmen.personel.pk, k.saat): f"{k.devamsiz}|{k.sinif}" for k in mevcut_atamalar
    }

    for n in nobetciler:
        satir = {"nobetci": n, "hucreler": []}
        kendi_dersleri = DersProgrami.objects.filter(
            ogretmen_id=n["id"], gun=day_name_en, uygulama_tarihi=program_date
        ).values_list("ders_saati__derssaati_no", flat=True)

        for saat in range(1, 9):
            durum = {}
            if saat in kendi_dersleri:
                durum["tip"] = "dolu"
            else:
                durum["tip"] = "musait"
                durum["secenekler"] = bos_dersler_havuzu[saat]
                durum["secili"] = atama_map.get((n["id"], saat), "")

            satir["hucreler"].append(durum)
        tablo_satirlari.append(satir)

    context = {
        "title": "Manuel Nöbet Dağıtım Matrisi",
        "target_date": target_date,
        "tablo_satirlari": tablo_satirlari,
        "saatler": range(1, 9),
    }
    return render(request, "manuel_dagitim.html", context)
