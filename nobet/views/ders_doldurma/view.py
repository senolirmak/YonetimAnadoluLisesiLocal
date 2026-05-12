"""
nobet_ders_doldurma — ana view (lean orchestrator).

POST aksiyonları küçük handler fonksiyonlarına devredilir;
DB sorguları _queries modülünden gelir; mazeret ve PDF ayrı modüllerde.
"""
from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone

from personeldevamsizlik.models import Devamsizlik
from utility.services.main_services import IstatistikService
from utility.services.nobet_dagitimi_service import AdvancedNobetDagitim

from ...forms import NobetDersDoldurmaForm
from ...models import (
    MAZERET_DERSLER,
    MazeretSalonGorevi,
    NobetAtanamayan,
    NobetGecmisi,
    NobetGorevi,
    NobetOgretmen,
    NobetPersonel,
)
from ..permissions import is_mudur_yardimcisi, is_yonetici
from ._mazeret import mazeret_ctx
from ._queries import (
    DAYS_MAP,
    aktif_devamsizliklar,
    aktif_gorev_tarihi,
    aktif_program_tarihi,
    ders_programi_by_ogretmenler,
    en_son_kayit_dt,
    gecmis_tarihler,
    kayitli_atamalar_ve_atamayanlar,
)

SESS_ASSIGN   = "nobet_assignments"
SESS_UNASSIGN = "nobet_unassigned"
SESS_DATE     = "nobet_target_date"


# ── Yardımcılar ───────────────────────────────────────────────────────────────


def _istatistik_guncelle():
    try:
        IstatistikService().hesapla_ve_kaydet()
    except Exception as e:
        print(f"İstatistik güncelleme hatası: {e}")


def _parse_target_date(raw):
    """'YYYY-MM-DD HH:MM:SS' veya 'YYYY-MM-DD' → date; geçersizse None."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except (ValueError, TypeError):
            pass
    return None


# ── POST handler'ları ─────────────────────────────────────────────────────────


def _handle_kaydet(request):
    """
    Oturumdaki hesaplama sonuçlarını DB'ye kaydeder.
    Döndürür: (target_date, assignments, unassigned)
    """
    assignments = request.session.get(SESS_ASSIGN, [])
    unassigned  = request.session.get(SESS_UNASSIGN, [])
    date_str    = request.session.get(SESS_DATE)
    target_date = timezone.localdate()

    if not date_str:
        return target_date, assignments, unassigned

    target_date  = datetime.strptime(date_str, "%Y-%m-%d").date()
    kayit_zamani = timezone.localtime().replace(
        year=target_date.year, month=target_date.month, day=target_date.day
    )

    for item in assignments:
        ogretmen = NobetOgretmen.objects.filter(personel_id=item["teacher_id"]).first()
        if ogretmen:
            try:
                NobetGecmisi.objects.create(
                    saat=item["hour"], sinif=item["class"],
                    devamsiz=item["absent_teacher_id"],
                    tarih=kayit_zamani, atandi=1, ogretmen=ogretmen,
                )
            except Exception as e:
                print(f"Hata (Atama Kaydı): {e}")

    for item in unassigned:
        ogretmen = NobetOgretmen.objects.filter(personel_id=item["absent_teacher_id"]).first()
        if ogretmen:
            try:
                NobetAtanamayan.objects.create(
                    saat=item["hour"], sinif=item["class"],
                    tarih=kayit_zamani, atandi=0, ogretmen=ogretmen,
                )
            except Exception as e:
                print(f"Hata (Atanamayan Kaydı): {e}")

    _istatistik_guncelle()
    messages.success(
        request,
        f"{target_date.strftime('%d.%m.%Y')} tarihi için atamalar başarıyla kaydedildi.",
    )
    return target_date, assignments, unassigned


def _handle_sil(request):
    """
    Kaydı siler. Başarılıysa redirect döner; başarısızsa None.
    """
    delete_dt_str = request.POST.get("delete_datetime")

    if delete_dt_str:
        try:
            del_dt   = datetime.strptime(delete_dt_str, "%Y-%m-%d %H:%M:%S")
            start_dt = timezone.make_aware(del_dt.replace(microsecond=0))
            end_dt   = timezone.make_aware(del_dt.replace(microsecond=999999))
            NobetGecmisi.objects.filter(tarih__range=[start_dt, end_dt]).delete()
            NobetAtanamayan.objects.filter(tarih__range=[start_dt, end_dt]).delete()
            _istatistik_guncelle()
            messages.success(request, f"{del_dt.strftime('%d.%m.%Y %H:%M:%S')} tarihli kayıtlar silindi.")
            return redirect(f"{request.path}?tarih={del_dt.date().strftime('%Y-%m-%d')}")
        except ValueError:
            messages.error(request, "Silme işlemi için tarih formatı geçersiz.")
            return None

    form = NobetDersDoldurmaForm(request.POST)
    if form.is_valid():
        target_date = form.cleaned_data["tarih"]
        start_dt = timezone.make_aware(datetime.combine(target_date, time.min))
        end_dt   = timezone.make_aware(datetime.combine(target_date, time.max))
        NobetGecmisi.objects.filter(tarih__range=[start_dt, end_dt]).delete()
        NobetAtanamayan.objects.filter(tarih__range=[start_dt, end_dt]).delete()
        _istatistik_guncelle()
        messages.success(request, f"{target_date.strftime('%d.%m.%Y')} tarihli kayıtlar silindi.")
        return redirect(f"{request.path}?tarih={target_date.strftime('%Y-%m-%d')}")
    return None


def _handle_mazeret_kaydet(request):
    """Mazeret salon atamalarını kaydeder ve redirect döner."""
    date_str = request.POST.get("mazeret_tarih", "")
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        target_date = timezone.localdate()

    for salon_ad in ("Mazeret1", "Mazeret2"):
        if request.POST.get(f"mazeret_acik_{salon_ad}") != "1":
            MazeretSalonGorevi.objects.filter(tarih=target_date, salon=salon_ad).delete()
            continue
        for saat in MAZERET_DERSLER:
            ogr_pk = request.POST.get(f"mazeret_{salon_ad}_{saat}", "").strip()
            if ogr_pk:
                try:
                    ogretmen = NobetOgretmen.objects.get(pk=int(ogr_pk))
                    MazeretSalonGorevi.objects.update_or_create(
                        tarih=target_date, salon=salon_ad, saat=saat,
                        defaults={"ogretmen": ogretmen},
                    )
                except (NobetOgretmen.DoesNotExist, ValueError):
                    pass
            else:
                MazeretSalonGorevi.objects.filter(
                    tarih=target_date, salon=salon_ad, saat=saat
                ).delete()

    messages.success(
        request,
        f"{target_date.strftime('%d.%m.%Y')} tarihi için mazeret salon atamaları kaydedildi.",
    )
    return redirect(f"{request.path}?tarih={target_date.strftime('%Y-%m-%d')}")


def _handle_hesapla(request, form):
    """
    Devamsız + nöbetçi verilerini tek DersProgrami sorgusunda çeker (N+1 → 1),
    AdvancedNobetDagitim çalıştırır.

    Döndürür: (assignments, unassigned, personel_map, gorev_date, absent_ids)
    """
    target_date  = form.cleaned_data["tarih"]
    max_shifts   = form.cleaned_data.get("max_shifts", 2)
    day_name_en  = DAYS_MAP[target_date.weekday()]
    program_date = aktif_program_tarihi(target_date)
    gorev_date   = aktif_gorev_tarihi(target_date)

    absent_records     = aktif_devamsizliklar(target_date, sadece_gorevlendirilebilir=True)
    absent_teacher_ids = [r.ogretmen.personel.pk for r in absent_records]

    duty_records = (
        list(
            NobetGorevi.objects.filter(uygulama_tarihi=gorev_date, nobet_gun=day_name_en)
            .select_related("ogretmen__personel")
        )
        if gorev_date else []
    )
    duty_teacher_ids = [r.ogretmen.personel.pk for r in duty_records]

    # ── Tek sorguda tüm ders programları (N+1 → 1) ────────────────
    all_ids = list(set(absent_teacher_ids + duty_teacher_ids))
    dp_map  = ders_programi_by_ogretmenler(all_ids, day_name_en, program_date) if program_date else {}

    absent_teachers_data = []
    for r in absent_records:
        p_id = r.ogretmen.personel.pk
        allowed = (
            [int(h) for h in r.ders_saatleri.split(",") if h.strip().isdigit()]
            if getattr(r, "ders_saatleri", None)
            else list(range(1, 9))
        )
        dersleri = {no: kls for no, kls in dp_map.get(p_id, {}).items() if no in allowed}
        if dersleri:
            absent_teachers_data.append({
                "ogretmen_id": p_id,
                "adi_soyadi":  r.ogretmen.personel.adi_soyadi,
                "devamsiz_tur": r.get_devamsiz_tur_display(),
                "dersleri":    dersleri,
            })

    available_teachers_data = []
    stats_dict = {}
    absent_set = set(absent_teacher_ids)
    for r in duty_records:
        p_id = r.ogretmen.personel.pk
        if p_id in absent_set:
            continue
        available_teachers_data.append({
            "ogretmen_id": p_id,
            "adi_soyadi":  r.ogretmen.personel.adi_soyadi,
            "dersleri":    dp_map.get(p_id, {}),
        })
        try:
            s = r.ogretmen.istatistikler
            stats_dict[p_id] = {
                "haftalik_ortalama": s.haftalik_ortalama,
                "agirlikli_puan":    s.agirlikli_puan,
                "toplam_nobet":      s.toplam_nobet,
                "hafta_sayisi":      s.hafta_sayisi,
                "son_nobet_tarihi":  s.son_nobet_tarihi,
                "son_nobet_yeri":    s.son_nobet_yeri,
            }
        except Exception:
            pass

    solver = AdvancedNobetDagitim(max_shifts=max_shifts)
    solver.set_teacher_statistics(stats_dict)
    result = solver.optimize(available_teachers_data, absent_teachers_data)

    assignments = result.get("assignments", [])
    unassigned  = result.get("unassigned", [])
    absent_info = {t["ogretmen_id"]: t["devamsiz_tur"] for t in absent_teachers_data}
    for a in assignments:
        a["devamsiz_tur"] = absent_info.get(a["absent_teacher_id"], "")
    for u in unassigned:
        u["devamsiz_tur"] = absent_info.get(u["absent_teacher_id"], "")

    personel_map = {
        p.id: p.adi_soyadi
        for p in NobetPersonel.objects.filter(id__in=all_ids)
    }
    return assignments, unassigned, personel_map, gorev_date, absent_teacher_ids


# ── Ana view ──────────────────────────────────────────────────────────────────


@login_required
def nobet_ders_doldurma(request):
    if not is_yonetici(request.user):
        raise PermissionDenied

    target_date           = timezone.localdate()
    assignments           = []
    unassigned            = []
    personel_map          = {}
    loaded_from_db        = False
    current_view_datetime = None
    gorev_date            = None
    absent_ids            = []

    # ── POST ──────────────────────────────────────────────────────
    if request.method == "POST":
        action = next(
            (k for k in ("kaydet", "sil", "mazeret_kaydet", "hesapla") if k in request.POST),
            None,
        )
        if action in ("kaydet", "sil", "mazeret_kaydet") and not is_mudur_yardimcisi(request.user):
            raise PermissionDenied

        if action == "kaydet":
            target_date, assignments, unassigned = _handle_kaydet(request)
            loaded_from_db = True

        elif action == "sil":
            resp = _handle_sil(request)
            if resp:
                return resp

        elif action == "mazeret_kaydet":
            return _handle_mazeret_kaydet(request)

        elif action == "hesapla":
            form = NobetDersDoldurmaForm(request.POST)
            if form.is_valid():
                target_date = form.cleaned_data["tarih"]
                assignments, unassigned, personel_map, gorev_date, absent_ids = _handle_hesapla(
                    request, form
                )
                request.session[SESS_ASSIGN]   = assignments
                request.session[SESS_UNASSIGN] = unassigned
                request.session[SESS_DATE]     = target_date.strftime("%Y-%m-%d")

    # ── GET: target_date parse ────────────────────────────────────
    elif request.GET.get("tarih"):
        parsed = _parse_target_date(request.GET["tarih"])
        if parsed:
            target_date = parsed

    # ── GET: kayıtlı veri otomatik yükleme ───────────────────────
    if request.method == "GET":
        found_dt = en_son_kayit_dt(target_date)
        if found_dt:
            start_dt = found_dt.replace(microsecond=0)
            end_dt   = found_dt.replace(microsecond=999999)
            saved, saved_un = kayitli_atamalar_ve_atamayanlar(start_dt, end_dt)
            if saved or saved_un:
                current_view_datetime = found_dt
                loaded_from_db = True
                query_date    = found_dt.date()
                devamsiz_list = aktif_devamsizliklar(query_date)
                absent_map    = {r.ogretmen.personel.pk: r.get_devamsiz_tur_display() for r in devamsiz_list}
                absent_ids    = [r.ogretmen.personel.pk for r in devamsiz_list]

                for s in saved:
                    assignments.append({
                        "hour": s.saat, "class": s.sinif,
                        "teacher_id": s.ogretmen.personel.pk,
                        "absent_teacher_id": s.devamsiz,
                        "devamsiz_tur": absent_map.get(s.devamsiz, "-"),
                    })
                for u in saved_un:
                    abs_id = u.ogretmen.personel.pk
                    unassigned.append({
                        "hour": u.saat, "class": u.sinif,
                        "absent_teacher_id": abs_id,
                        "devamsiz_tur": absent_map.get(abs_id, "-"),
                    })
                request.session[SESS_ASSIGN]   = assignments
                request.session[SESS_UNASSIGN] = unassigned
                request.session[SESS_DATE]     = target_date.strftime("%Y-%m-%d")
                messages.info(
                    request,
                    f"{found_dt.strftime('%d.%m.%Y %H:%M:%S')} tarihli kayıtlı dağılım gösteriliyor.",
                )

    # ── personel_map (kaydet POST veya DB yüklemesi sonrası) ──────
    if loaded_from_db and not personel_map:
        all_ids = set()
        for a in assignments:
            all_ids.update([a.get("teacher_id"), a.get("absent_teacher_id")])
        for u in unassigned:
            all_ids.add(u.get("absent_teacher_id"))
        personel_map = {p.id: p.adi_soyadi for p in NobetPersonel.objects.filter(id__in=all_ids)}

    # ── Mazeret context (mümkünse önceden hesaplanan değerleri kullanır) ──
    if gorev_date is None:
        gorev_date = aktif_gorev_tarihi(target_date)
    if not absent_ids:
        absent_ids = list(
            Devamsizlik.objects.filter(baslangic_tarihi__lte=target_date)
            .filter(Q(bitis_tarihi__gte=target_date) | Q(bitis_tarihi__isnull=True))
            .values_list("ogretmen__personel__pk", flat=True)
        )

    day_name_en = DAYS_MAP[target_date.weekday()]

    context = {
        "title":                 "Nöbetçi Öğretmen Ders Doldurma",
        "form":                  NobetDersDoldurmaForm(initial={"tarih": target_date, "max_shifts": 2}),
        "assignments":           assignments,
        "unassigned":            unassigned,
        "personel_map":          personel_map,
        "target_date":           target_date,
        "history_records":       gecmis_tarihler(target_date),
        "loaded_from_db":        loaded_from_db,
        "current_view_datetime": current_view_datetime,
        **mazeret_ctx(target_date, gorev_date, day_name_en, absent_ids),
    }
    return render(request, "nobet_ders_doldurma.html", context)
