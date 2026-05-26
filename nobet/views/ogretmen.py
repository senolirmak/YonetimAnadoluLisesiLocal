from datetime import date as dt_date
from datetime import datetime, timedelta
from datetime import time as dt_time

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from nobet.models import (
    GunlukNobetCizelgesi,
    NobetAtanamayan,
    NobetGecmisi,
    NobetGorevi,
    NobetIstatistik,
    NobetPersonel,
)
from personeldevamsizlik.models import Devamsizlik
from main.utils import _ogretmen_menu_gorumu, _DAYS_MAP, _GUN_TR, _TR_GUNLER


# ─────────────────────────────────────────────
# Öğretmen — Haftalık Nöbet Listesi (salt okunur)
# ─────────────────────────────────────────────

@login_required
def ogretmen_haftalik_nobet(request):
    if not (request.user.is_superuser or request.user.groups.filter(name="mudur_yardimcisi").exists() or _ogretmen_menu_gorumu(request.user)):
        raise PermissionDenied

    # Distinct uygulama tarihleri (tebliğ tarihleri), sıralı
    uyg_tarihler = list(
        NobetGorevi.objects.values_list("uygulama_tarihi", flat=True)
        .distinct()
        .order_by("uygulama_tarihi")
    )

    if not uyg_tarihler:
        return render(
            request,
            "nobet/ogretmen_haftalik_nobet.html",
            {
                "title": "Haftalık Nöbet Listesi",
                "gunler": _TR_GUNLER,
                "tablo_satirlari": [],
                "baslangic": None,
                "bitis": None,
                "onceki": None,
                "sonraki": None,
                "uygulama_tarihi": None,
            },
        )

    # Seçili uygulama tarihi: GET'ten geliyorsa kullan, yoksa en son
    tarih_str = request.GET.get("tarih", "").strip()
    try:
        secili = dt_date.fromisoformat(tarih_str)
        if secili not in uyg_tarihler:
            # En yakın olanı bul
            secili = min(uyg_tarihler, key=lambda t: abs((t - secili).days))
    except (ValueError, TypeError):
        secili = uyg_tarihler[-1]

    idx = uyg_tarihler.index(secili)
    onceki = uyg_tarihler[idx - 1] if idx > 0 else None
    sonraki = uyg_tarihler[idx + 1] if idx < len(uyg_tarihler) - 1 else None

    # Hafta aralığı: bugünün bulunduğu haftanın Pazartesi–Cuma
    bugun = timezone.localdate()
    pazartesi = bugun - timedelta(days=bugun.weekday())
    cuma = pazartesi + timedelta(days=4)

    # Sadece seçili uygulama tarihine ait kayıtlar
    nobetler = NobetGorevi.objects.filter(uygulama_tarihi=secili).select_related(
        "ogretmen__personel"
    )

    # Öğretmen → {gün: yer} haritası
    ogretmen_nobet_map = {}
    for n in nobetler:
        isim = n.ogretmen.personel.adi_soyadi
        gun_tr = _GUN_TR.get(n.nobet_gun, n.nobet_gun)
        ogretmen_nobet_map.setdefault(isim, {})[gun_tr] = n.nobet_yeri

    # Tablo satırları: her öğretmen için 5 günlük satır
    tablo_satirlari = []
    for isim, gun_yer in sorted(ogretmen_nobet_map.items()):
        satir = {"ogretmen": isim}
        for gun in _TR_GUNLER:
            satir[gun] = gun_yer.get(gun, "")
        tablo_satirlari.append(satir)

    return render(
        request,
        "nobet/ogretmen_haftalik_nobet.html",
        {
            "title": "Haftalık Nöbet Listesi",
            "gunler": _TR_GUNLER,
            "tablo_satirlari": tablo_satirlari,
            "baslangic": pazartesi,
            "bitis": cuma,
            "onceki": onceki,
            "sonraki": sonraki,
            "uygulama_tarihi": secili,
        },
    )


# ─────────────────────────────────────────────
# Öğretmen — Günün Nöbetçileri (salt okunur)
# ─────────────────────────────────────────────

@login_required
def ogretmen_gunun_nobetcileri(request):
    if not (request.user.is_superuser or request.user.groups.filter(name="mudur_yardimcisi").exists() or _ogretmen_menu_gorumu(request.user)):
        raise PermissionDenied

    target_date = timezone.localdate()
    tarih_str = request.GET.get("tarih", "").strip()
    try:
        target_date = dt_date.fromisoformat(tarih_str)
    except (ValueError, TypeError):
        pass

    day_name_en = _DAYS_MAP[target_date.weekday()]

    gorev_date = (
        NobetGorevi.objects.filter(uygulama_tarihi__lte=target_date)
        .order_by("-uygulama_tarihi")
        .values_list("uygulama_tarihi", flat=True)
        .first()
    )

    gorevler = []
    if gorev_date:
        tum_gorevler = (
            NobetGorevi.objects.filter(
                uygulama_tarihi=gorev_date,
                nobet_gun=day_name_en,
            )
            .select_related("ogretmen__personel")
            .order_by("nobet_yeri")
        )

        gunluk_degisiklikler = {
            k.ogretmen_id: k.nobet_yeri
            for k in GunlukNobetCizelgesi.objects.filter(tarih=target_date)
        }
        full_day_hours = set(range(1, 9))

        for gorev in tum_gorevler:
            if gorev.ogretmen.pk in gunluk_degisiklikler:
                gorev.nobet_yeri = gunluk_degisiklikler[gorev.ogretmen.pk]

            is_full_absent = False
            for absence in Devamsizlik.objects.filter(
                ogretmen=gorev.ogretmen,
                baslangic_tarihi__lte=target_date,
                bitis_tarihi__gte=target_date,
            ):
                abs_start = absence.baslangic_tarihi
                if isinstance(abs_start, datetime):
                    abs_start = abs_start.date()
                abs_end = absence.bitis_tarihi or abs_start
                if isinstance(abs_end, datetime):
                    abs_end = abs_end.date()

                if abs_start < target_date < abs_end:
                    is_full_absent = True
                elif hasattr(absence, "ders_saatleri") and absence.ders_saatleri:
                    try:
                        hours = [
                            int(h) for h in absence.ders_saatleri.split(",") if h.strip().isdigit()
                        ]
                        if set(hours).issuperset(full_day_hours):
                            is_full_absent = True
                    except ValueError:
                        pass
                if is_full_absent:
                    break

            if not is_full_absent:
                gorevler.append(gorev)

    return render(
        request,
        "nobet/ogretmen_gunun_nobetcileri.html",
        {
            "title": "Günün Nöbetçileri",
            "gorevler": gorevler,
            "target_date": target_date,
            "onceki": (target_date - timedelta(days=1)).isoformat(),
            "sonraki": (target_date + timedelta(days=1)).isoformat(),
        },
    )


# ─────────────────────────────────────────────
# Öğretmen — Atanan / Atanamayan Dersler (salt okunur)
# ─────────────────────────────────────────────

@login_required
def ogretmen_ders_doldurma(request):
    if not (request.user.is_superuser or request.user.groups.filter(name="mudur_yardimcisi").exists() or _ogretmen_menu_gorumu(request.user)):
        raise PermissionDenied

    target_date = timezone.localdate()
    tarih_str = request.GET.get("tarih", "").strip()
    try:
        target_date = dt_date.fromisoformat(tarih_str)
    except (ValueError, TypeError):
        pass

    start_day = timezone.make_aware(datetime.combine(target_date, dt_time.min))
    end_day = timezone.make_aware(datetime.combine(target_date, dt_time.max))

    saved_assigns = (
        NobetGecmisi.objects.filter(tarih__range=[start_day, end_day])
        .select_related("ogretmen__personel")
        .order_by("saat")
    )
    saved_unassigns = (
        NobetAtanamayan.objects.filter(tarih__range=[start_day, end_day])
        .select_related("ogretmen__personel")
        .order_by("saat")
    )

    # devamsiz alanı personel pk (integer) saklar — isim için tek sorguda çek
    devamsiz_ids = set(
        list(saved_assigns.values_list("devamsiz", flat=True))
        + list(saved_unassigns.values_list("ogretmen__personel__pk", flat=True))
    )
    personel_map = dict(
        NobetPersonel.objects.filter(pk__in=devamsiz_ids).values_list("pk", "adi_soyadi")
    )

    assignments = [
        {
            "hour": a.saat,
            "sinif": a.sinif,
            "devamsiz": personel_map.get(a.devamsiz, "-"),
            "atanan": a.ogretmen.personel.adi_soyadi,
        }
        for a in saved_assigns
    ]
    unassigned = [
        {
            "hour": u.saat,
            "sinif": u.sinif,
            "devamsiz": u.ogretmen.personel.adi_soyadi,
        }
        for u in saved_unassigns
    ]

    return render(
        request,
        "nobet/ogretmen_ders_doldurma.html",
        {
            "title": "Atanan Dersler ve Atanamayan Dersler",
            "assignments": assignments,
            "unassigned": unassigned,
            "target_date": target_date,
            "onceki": (target_date - timedelta(days=1)).isoformat(),
            "sonraki": (target_date + timedelta(days=1)).isoformat(),
        },
    )


# ─────────────────────────────────────────────
# Nöbetçi Öğretmen — Ders Doldurma İstatistikleri
# ─────────────────────────────────────────────

@login_required
def nobetci_ders_doldurma_istatistik(request):
    if not (
        request.user.is_superuser
        or request.user.groups.filter(name="mudur_yardimcisi").exists()
        or _ogretmen_menu_gorumu(request.user)
    ):
        raise PermissionDenied

    # ── Aktif nöbet tarifesi ──────────────────────────────────────
    aktif_gorev_tarihi = (
        NobetGorevi.objects.order_by("-uygulama_tarihi")
        .values_list("uygulama_tarihi", flat=True)
        .first()
    )

    GUN_TR = {
        "Monday": "Pazartesi", "Tuesday": "Salı", "Wednesday": "Çarşamba",
        "Thursday": "Perşembe", "Friday": "Cuma",
        "Saturday": "Cumartesi", "Sunday": "Pazar",
    }

    # ── Tarih aralığı filtresi (GET: donem = 30 | 90 | tum) ───────
    donem = request.GET.get("donem", "30")
    today = timezone.localdate()
    if donem == "tum":
        tarih_siniri = None
    elif donem == "90":
        tarih_siniri = today - timedelta(days=90)
    else:
        donem = "30"
        tarih_siniri = today - timedelta(days=30)

    gecmis_qs = NobetGecmisi.objects.all()
    atanamayan_qs = NobetAtanamayan.objects.all()
    if tarih_siniri:
        gecmis_qs = gecmis_qs.filter(tarih__date__gte=tarih_siniri)
        atanamayan_qs = atanamayan_qs.filter(tarih__date__gte=tarih_siniri)

    # ── Özet sayılar ─────────────────────────────────────────────
    toplam_doldurma = gecmis_qs.count()
    toplam_atanamayan = atanamayan_qs.count()

    # ── Aktif nöbet programındaki öğretmenleri grupla ─────────────
    gorevler = (
        NobetGorevi.objects.filter(uygulama_tarihi=aktif_gorev_tarihi)
        .select_related("ogretmen__personel")
        .order_by("ogretmen__personel__adi_soyadi", "nobet_gun")
    )

    # {NobetOgretmen.pk: [gun_tr, ...]}
    ogretmen_gunler = {}
    ogretmen_obj = {}
    for g in gorevler:
        pk = g.ogretmen_id
        ogretmen_gunler.setdefault(pk, []).append(GUN_TR.get(g.nobet_gun, g.nobet_gun))
        ogretmen_obj[pk] = g.ogretmen

    if not ogretmen_gunler:
        return render(request, "nobet/nobetci_ders_doldurma_istatistik.html", {
            "title": "Ders Doldurma İstatistikleri",
            "satirlar": [],
            "toplam_doldurma": 0,
            "toplam_atanamayan": 0,
            "aktif_gorev_tarihi": None,
            "donem": donem,
        })

    # ── Dönem içi doldurma sayıları (tek sorgu) ───────────────────
    doldurma_counts = dict(
        gecmis_qs.filter(ogretmen_id__in=ogretmen_gunler)
        .values("ogretmen_id")
        .annotate(sayi=Count("id"))
        .values_list("ogretmen_id", "sayi")
    )

    # ── Önceden hesaplanmış istatistikler ─────────────────────────
    istatistikler = {
        ist.ogretmen_id: ist
        for ist in NobetIstatistik.objects.filter(ogretmen_id__in=ogretmen_gunler)
    }

    # ── Satır listesi (ağırlıklı puana göre azalan) ───────────────
    satirlar = []
    for pk, gunler in ogretmen_gunler.items():
        ogr = ogretmen_obj[pk]
        ist = istatistikler.get(pk)
        donem_count = doldurma_counts.get(pk, 0)
        satirlar.append({
            "adi_soyadi":       ogr.personel.adi_soyadi,
            "gunler":           gunler,
            "donem_doldurma":   donem_count,
            "toplam_nobet":     ist.toplam_nobet      if ist else 0,
            "haftalik_ort":     round(ist.haftalik_ortalama, 2) if ist else 0,
            "agirlikli_puan":   round(ist.agirlikli_puan, 1)    if ist else 0,
            "son_nobet":        ist.son_nobet_tarihi  if ist else None,
            "son_nobet_yeri":   ist.son_nobet_yeri    if ist else "-",
        })

    satirlar.sort(key=lambda r: r["agirlikli_puan"], reverse=True)

    # ── Son 20 ders doldurma kaydı ────────────────────────────────
    son_kayitlar_qs = (
        NobetGecmisi.objects
        .filter(ogretmen_id__in=ogretmen_gunler)
        .select_related("ogretmen__personel")
        .order_by("-tarih")[:20]
    )
    devamsiz_ids = [k.devamsiz for k in son_kayitlar_qs if k.devamsiz]
    devamsiz_map = dict(
        NobetPersonel.objects.filter(pk__in=devamsiz_ids).values_list("pk", "adi_soyadi")
    )
    son_kayitlar = [
        {
            "tarih":    k.tarih,
            "saat":     k.saat,
            "sinif":    k.sinif,
            "nobetci":  k.ogretmen.personel.adi_soyadi,
            "devamsiz": devamsiz_map.get(k.devamsiz, "-"),
        }
        for k in son_kayitlar_qs
    ]

    return render(request, "nobet/nobetci_ders_doldurma_istatistik.html", {
        "title":               "Ders Doldurma İstatistikleri",
        "satirlar":            satirlar,
        "son_kayitlar":        son_kayitlar,
        "toplam_doldurma":     toplam_doldurma,
        "toplam_atanamayan":   toplam_atanamayan,
        "aktif_gorev_tarihi":  aktif_gorev_tarihi,
        "donem":               donem,
    })
