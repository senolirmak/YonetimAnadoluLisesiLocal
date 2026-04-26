from datetime import datetime, time
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone

from nobet.models import NobetAtanamayan, NobetGecmisi, NobetOgretmen, NobetPersonel
from okul.utils import get_aktif_dp_tarihi
from personeldevamsizlik.models import Devamsizlik
from utility.constants import WEEKDAY_TO_DB as _WEEKDAY_TO_DB
from veriaktar.forms import DersProgramiImportForm

from .forms import SinifSubeSecimForm
from .models import DersProgrami

# ─────────────────────────────────────────────
# Yetki yardımcıları
# ─────────────────────────────────────────────

from okul.auth import is_mudur_yardimcisi, mudur_yardimcisi_required  # noqa: E402

YONETICI_GRUPLAR = {"mudur_yardimcisi", "okul_muduru", "rehber_ogretmen", "disiplin_kurulu"}
TARIH_DEGISTIREBILIR_GRUPLAR = {"mudur_yardimcisi", "okul_muduru"}


def _is_yonetici(user):
    return user.is_superuser or user.groups.filter(name__in=YONETICI_GRUPLAR).exists()


def _is_tarih_degistirebilir(user):
    return user.is_superuser or user.groups.filter(name__in=TARIH_DEGISTIREBILIR_GRUPLAR).exists()


def yonetici_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not _is_yonetici(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


def mudur_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not _is_tarih_degistirebilir(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


# ─────────────────────────────────────────────
# MultipleTeacherDersProxy — şablon yardımcısı
# ─────────────────────────────────────────────


class MultipleTeacherDersProxy:
    """
    Aynı ders saatinde birden fazla öğretmenin atanmış olması durumunda,
    şablona tek bir ders nesnesi gibi davranıp öğretmen (ve varsa ders)
    isimlerini virgülle birleştirerek sunan yardımcı sınıf.
    """

    def __init__(
        self, matches, nobetci_ogretmen=None, atanamayan=False, devamsiz_map=None, ders_saati=None
    ):
        self.matches = matches
        self.first = matches[0]
        self.nobetci_ogretmen = nobetci_ogretmen
        self.atanamayan = atanamayan
        self.devamsiz_map = devamsiz_map or {}
        self.ders_saati = ders_saati

    @property
    def ders_adi(self):
        dersler = []
        for m in self.matches:
            if m.ders_adi and m.ders_adi not in dersler:
                dersler.append(m.ders_adi)
        return " / ".join(dersler) if dersler else self.first.ders_adi

    @property
    def ogretmen_detay(self):
        liste = []
        eklenen = set()
        for m in self.matches:
            if m.ogretmen and m.ogretmen.pk not in eklenen:
                eklenen.add(m.ogretmen.pk)
                neden = self.devamsiz_map.get((m.ogretmen.pk, self.ders_saati))
                liste.append({"adi_soyadi": m.ogretmen.adi_soyadi, "devamsiz_nedeni": neden})
        return liste

    @property
    def has_devamsiz(self):
        for ogr in self.ogretmen_detay:
            if ogr.get("devamsiz_nedeni"):
                return True
        return False

    @property
    def ogretmen(self):
        class FakeOgretmen:
            def __init__(self, parent):
                self.parent = parent

            @property
            def adi_soyadi(self):
                isimler = []
                for m in self.parent.matches:
                    if m.ogretmen and m.ogretmen.adi_soyadi not in isimler:
                        isimler.append(m.ogretmen.adi_soyadi)
                return ", ".join(isimler)

            def __str__(self):
                return self.adi_soyadi

        return FakeOgretmen(self)

    def __getattr__(self, name):
        return getattr(self.first, name)


# ─────────────────────────────────────────────
# Öğretmen Haftalık Programı (Durum)
# ─────────────────────────────────────────────


@yonetici_required
def ogretmen_program(request):
    from django.db.models import Q

    now = timezone.localtime()
    current_clock = now.time()
    tarih_degistirebilir = _is_tarih_degistirebilir(request.user)

    secilen_tarih = None
    secilen_ders_saati = None
    if tarih_degistirebilir:
        tarih_str = request.GET.get("tarih", "").strip()
        ds_str = request.GET.get("ders_saati", "").strip()
        if tarih_str:
            try:
                secilen_tarih = datetime.strptime(tarih_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        if ds_str:
            try:
                val = int(ds_str)
                if 1 <= val <= 8:
                    secilen_ders_saati = val
            except (ValueError, TypeError):
                pass

    today = secilen_tarih if secilen_tarih else now.date()
    current_day_db = _WEEKDAY_TO_DB.get(today.weekday(), "Monday")

    aktif_tarih = get_aktif_dp_tarihi()
    dp_tarih_filter = {"uygulama_tarihi": aktif_tarih} if aktif_tarih else {}
    gun_saatleri_qs = (
        DersProgrami.objects.filter(gun=current_day_db, **dp_tarih_filter)
        .select_related("ders_saati")
        .order_by("ders_saati__derssaati_no")
    )
    seen_ds = set()
    gun_saatleri = []
    for dp in gun_saatleri_qs:
        if dp.ders_saati and dp.ders_saati_id not in seen_ds:
            seen_ds.add(dp.ders_saati_id)
            gun_saatleri.append({
                "ders_saati": dp.ders_saati.derssaati_no,
                "ders_saati_adi": dp.ders_saati.ders_adi,
                "giris_saat": dp.ders_saati.derssaati_baslangic,
                "cikis_saat": dp.ders_saati.derssaati_bitis,
            })

    auto_ders_saati = None
    _auto_giris = None
    _auto_cikis = None
    for row in gun_saatleri:
        if row["giris_saat"] <= current_clock < row["cikis_saat"]:
            auto_ders_saati = row["ders_saati"]
            _auto_giris = row["giris_saat"]
            _auto_cikis = row["cikis_saat"]
            break

    current_ders_saati = secilen_ders_saati if secilen_ders_saati else auto_ders_saati

    ders_saati_giris = None
    ders_saati_cikis = None
    if current_ders_saati:
        for row in gun_saatleri:
            if row["ders_saati"] == current_ders_saati:
                ders_saati_giris = row["giris_saat"]
                ders_saati_cikis = row["cikis_saat"]
                break

    if current_ders_saati:
        derste_personel_ids = set(
            DersProgrami.objects.filter(
                gun=current_day_db, ders_saati__derssaati_no=current_ders_saati,
                **dp_tarih_filter,
            ).values_list("ogretmen_id", flat=True)
        )
    else:
        derste_personel_ids = set()

    bugun_dersi_olan_ids = set(
        DersProgrami.objects.filter(gun=current_day_db, **dp_tarih_filter).values_list("ogretmen_id", flat=True)
    )

    devamsiz_personel_ids = set(
        Devamsizlik.objects.filter(baslangic_tarihi__lte=today)
        .filter(Q(bitis_tarihi__gte=today) | Q(bitis_tarihi__isnull=True))
        .values_list("ogretmen__personel_id", flat=True)
    )

    nobetci_atama_map = {}
    if current_ders_saati:
        gun_baslangic = timezone.make_aware(datetime.combine(today, time.min))
        gun_bitis = timezone.make_aware(datetime.combine(today, time.max))
        atamalar_qs = NobetGecmisi.objects.filter(
            tarih__range=[gun_baslangic, gun_bitis], saat=current_ders_saati, atandi=1
        ).select_related("ogretmen__personel")
        devamsiz_id_set = {a.devamsiz for a in atamalar_qs if a.devamsiz}
        devamsiz_personel_map = {
            p.pk: p for p in NobetPersonel.objects.filter(id__in=devamsiz_id_set)
        }
        for atama in atamalar_qs:
            pid = atama.ogretmen.personel.pk
            devamsiz_obj = devamsiz_personel_map.get(atama.devamsiz)
            nobetci_atama_map.setdefault(pid, []).append(
                {
                    "sinif": atama.sinif or "",
                    "devamsiz_adi": devamsiz_obj.adi_soyadi if devamsiz_obj else "",
                }
            )

    tum_nobetci = NobetOgretmen.objects.select_related("personel").order_by("personel__adi_soyadi")

    derste = []
    ogretmenler_odasinda = []
    derssiz = []

    for nobetci in tum_nobetci:
        p = nobetci.personel
        devamsiz = p.id in devamsiz_personel_ids
        atamalar = nobetci_atama_map.get(p.id, [])

        if devamsiz:
            derssiz.append({"personel": p, "devamsiz": True})
        elif p.id in derste_personel_ids or atamalar:
            ders_bilgisi = ""
            if p.id in derste_personel_ids:
                kayit = DersProgrami.objects.filter(
                    gun=current_day_db, ders_saati__derssaati_no=current_ders_saati, ogretmen=p
                ).select_related("ders_saati", "ders").first()
                if kayit:
                    sinif = str(kayit.sinif_sube) if kayit.sinif_sube else ""
                    ders_bilgisi = f"{sinif} – {kayit.ders_adi}".strip(" –")
            derste.append(
                {
                    "personel": p,
                    "ders_bilgisi": ders_bilgisi,
                    "nobetci_atamalar": atamalar,
                }
            )
        elif p.pk in bugun_dersi_olan_ids:
            ogretmenler_odasinda.append({"personel": p})
        else:
            derssiz.append({"personel": p, "devamsiz": False})

    context = {
        "title": "Öğretmen Durum Bilgisi",
        "derste": derste,
        "ogretmenler_odasinda": ogretmenler_odasinda,
        "derssiz": derssiz,
        "simdi": now,
        "gosterilen_tarih": today,
        "current_ders_saati": current_ders_saati,
        "auto_ders_saati": auto_ders_saati,
        "ders_saati_giris": ders_saati_giris,
        "ders_saati_cikis": ders_saati_cikis,
        "gun_saatleri": gun_saatleri,
        "tarih_degistirebilir": tarih_degistirebilir,
        "secilen_tarih_str": today.strftime("%Y-%m-%d"),
        "secilen_ders_saati": current_ders_saati,
    }
    return render(request, "dersprogrami/ogretmen_program.html", context)


# ─────────────────────────────────────────────
# Sınıf Haftalık Programı
# ─────────────────────────────────────────────


@mudur_required
def sinif_program(request):
    from collections import defaultdict

    from django.db.models import Q

    now = timezone.localtime()
    current_clock = now.time()

    secilen_tarih = None
    secilen_ders_saati = None
    secilen_sinif_id = None
    tarih_str = request.GET.get("tarih", "").strip()
    ds_str = request.GET.get("ders_saati", "").strip()
    ss_str = request.GET.get("sinif_sube", "").strip()
    if tarih_str:
        try:
            secilen_tarih = datetime.strptime(tarih_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    if ds_str:
        try:
            val = int(ds_str)
            if 1 <= val <= 8:
                secilen_ders_saati = val
        except (ValueError, TypeError):
            pass
    if ss_str:
        try:
            secilen_sinif_id = int(ss_str)
        except (ValueError, TypeError):
            pass

    today = secilen_tarih if secilen_tarih else now.date()
    current_day_db = _WEEKDAY_TO_DB.get(today.weekday(), "Monday")

    tum_program = list(
        DersProgrami.objects.select_related("sinif_sube", "ogretmen", "ders_saati", "ders")
        .filter(sinif_sube__isnull=False)
        .order_by("sinif_sube__sinif", "sinif_sube__sube", "ders_saati__derssaati_no")
    )

    gun_saatleri_qs = (
        DersProgrami.objects.filter(gun=current_day_db)
        .select_related("ders_saati")
        .order_by("ders_saati__derssaati_no")
    )
    seen_ds = set()
    gun_saatleri = []
    for dp in gun_saatleri_qs:
        if dp.ders_saati and dp.ders_saati_id not in seen_ds:
            seen_ds.add(dp.ders_saati_id)
            gun_saatleri.append({
                "ders_saati": dp.ders_saati.derssaati_no,
                "ders_saati_adi": dp.ders_saati.ders_adi,
                "giris_saat": dp.ders_saati.derssaati_baslangic,
                "cikis_saat": dp.ders_saati.derssaati_bitis,
            })

    auto_ders_saati = None
    for row in gun_saatleri:
        if row["giris_saat"] <= current_clock < row["cikis_saat"]:
            auto_ders_saati = row["ders_saati"]
            break

    current_ders_saati = secilen_ders_saati if secilen_ders_saati else auto_ders_saati

    ders_saati_giris = None
    ders_saati_cikis = None
    for row in gun_saatleri:
        if row["ders_saati"] == current_ders_saati:
            ders_saati_giris = row["giris_saat"]
            ders_saati_cikis = row["cikis_saat"]
            break

    GUN_DB = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    GUN_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]

    sinif_programlari = defaultdict(list)
    sinif_obj_map = {}
    for dp in tum_program:
        if dp.sinif_sube is None:
            continue
        sinif_programlari[dp.sinif_sube.pk].append(dp)
        sinif_obj_map[dp.sinif_sube.pk] = dp.sinif_sube

    tum_siniflar = sorted(sinif_obj_map.values(), key=lambda s: (s.sinif, s.sube))

    if secilen_sinif_id is not None and secilen_sinif_id in sinif_obj_map:
        sinif_ids_sirali = [secilen_sinif_id]
    else:
        sinif_ids_sirali = []

    gun_baslangic = timezone.make_aware(datetime.combine(today, time.min))
    gun_bitis = timezone.make_aware(datetime.combine(today, time.max))
    atamalar_qs = NobetGecmisi.objects.filter(
        tarih__range=[gun_baslangic, gun_bitis], atandi=1
    ).select_related("ogretmen__personel")

    atama_map = {}
    for a in atamalar_qs:
        atama_map[(a.sinif, a.saat)] = a.ogretmen.personel.adi_soyadi

    atanamayan_qs = NobetAtanamayan.objects.filter(tarih__range=[gun_baslangic, gun_bitis])
    atanamayan_set = {(a.sinif, a.saat) for a in atanamayan_qs}

    devamsizliklar = (
        Devamsizlik.objects.filter(baslangic_tarihi__lte=today)
        .filter(Q(bitis_tarihi__gte=today) | Q(bitis_tarihi__isnull=True))
        .select_related("ogretmen__personel")
    )

    devamsiz_saatler_map = {}
    for d in devamsizliklar:
        p_id = d.ogretmen.personel.id
        neden = d.get_devamsiz_tur_display()
        if d.ders_saatleri:
            try:
                saatler = [int(h) for h in d.ders_saatleri.split(",") if h.strip().isdigit()]
                for s_saat in saatler:
                    devamsiz_saatler_map[(p_id, s_saat)] = neden
            except ValueError:
                pass
        else:
            for s_saat in range(1, 20):
                devamsiz_saatler_map[(p_id, s_saat)] = neden

    tum_ders_saatleri = sorted({dp.ders_saati.derssaati_no for dp in tum_program if dp.ders_saati})

    ders_saati_adi_map = {}
    for dp in tum_program:
        if dp.ders_saati and dp.ders_saati.derssaati_no not in ders_saati_adi_map:
            ders_saati_adi_map[dp.ders_saati.derssaati_no] = dp.ders_saati.ders_adi

    sinif_data = []
    for sid in sinif_ids_sirali:
        dersler = sinif_programlari[sid]
        s = sinif_obj_map[sid]

        aktif_ders = None
        if current_ders_saati:
            aktif_matches = [
                d for d in dersler if d.gun == current_day_db and d.ders_saati and d.ders_saati.derssaati_no == current_ders_saati
            ]
            if aktif_matches:
                nobetci = atama_map.get((str(s), current_ders_saati))
                is_atanamayan = (str(s), current_ders_saati) in atanamayan_set
                aktif_ders = MultipleTeacherDersProxy(
                    aktif_matches,
                    nobetci_ogretmen=nobetci,
                    atanamayan=is_atanamayan,
                    devamsiz_map=devamsiz_saatler_map,
                    ders_saati=current_ders_saati,
                )

        program_rows = []
        for ds in tum_ders_saatleri:
            cells = []
            for gdb in GUN_DB:
                matches = [d for d in dersler if d.ders_saati and d.ders_saati.derssaati_no == ds and d.gun == gdb]
                if matches:
                    nobetci = None
                    is_atanamayan = False
                    d_map = {}
                    if gdb == current_day_db:
                        nobetci = atama_map.get((str(s), ds))
                        is_atanamayan = (str(s), ds) in atanamayan_set
                        d_map = devamsiz_saatler_map
                    cells.append(
                        MultipleTeacherDersProxy(
                            matches,
                            nobetci_ogretmen=nobetci,
                            atanamayan=is_atanamayan,
                            devamsiz_map=d_map,
                            ders_saati=ds,
                        )
                    )
                else:
                    cells.append(None)
            program_rows.append(
                {
                    "ders_saati": ds,
                    "ders_saati_adi": ders_saati_adi_map.get(ds, f"{ds}.D"),
                    "aktif": ds == current_ders_saati,
                    "cells": cells,
                }
            )

        sinif_data.append(
            {
                "sinif_sube": s,
                "aktif_ders": aktif_ders,
                "program_rows": program_rows,
            }
        )

    context = {
        "title": "Sınıf Haftalık Programı",
        "sinif_data": sinif_data,
        "gun_tr_list": GUN_TR,
        "simdi": now,
        "gosterilen_tarih": today,
        "current_ders_saati": current_ders_saati,
        "ders_saati_giris": ders_saati_giris,
        "ders_saati_cikis": ders_saati_cikis,
        "gun_saatleri": gun_saatleri,
        "secilen_tarih_str": today.strftime("%Y-%m-%d"),
        "secilen_ders_saati": current_ders_saati,
        "tum_siniflar": tum_siniflar,
        "secilen_sinif_id": secilen_sinif_id,
    }
    return render(request, "dersprogrami/sinif_program.html", context)


# ─────────────────────────────────────────────
# Sınıf → Öğretmen Listesi
# ─────────────────────────────────────────────


@yonetici_required
def sinif_ogretmenleri(request):
    from collections import defaultdict

    form = SinifSubeSecimForm(request.GET or None)

    secilen_sinif = None
    ogretmen_listesi = []
    ogretmen_no = 0

    if form.is_valid():
        secilen_sinif = form.cleaned_data.get("sinif_sube")

    if secilen_sinif:
        dersler = (
            DersProgrami.objects.filter(sinif_sube=secilen_sinif)
            .select_related("ogretmen", "ders_saati", "ders")
            .order_by("ogretmen__adi_soyadi", "gun", "ders_saati__derssaati_no")
        )

        # (personel_pk, ders_adi) → {personel, ders_adi, sayi}
        satir_map: dict = {}
        for ders in dersler:
            p = ders.ogretmen
            key = (p.pk, ders.ders_adi)
            if key not in satir_map:
                satir_map[key] = {"personel": p, "ders_adi": ders.ders_adi, "sayi": 0}
            satir_map[key]["sayi"] += 1

        ogretmen_listesi = sorted(
            satir_map.values(), key=lambda r: (r["personel"].adi_soyadi, r["ders_adi"])
        )

    context = {
        "title": "Sınıf Öğretmen Listesi",
        "form": form,
        "secilen_sinif": secilen_sinif,
        "ogretmen_listesi": ogretmen_listesi,
    }
    return render(request, "dersprogrami/sinif_ogretmenleri.html", context)


# ─────────────────────────────────────────────
# Ders Programı Listeleme
# ─────────────────────────────────────────────


@login_required
def dersprogrami_listesi(request):
    from okul.models import SinifSube

    # Filtre parametreleri
    ogretmen_id = request.GET.get("ogretmen", "").strip()
    sinif_id = request.GET.get("sinif_sube", "").strip()
    gun = request.GET.get("gun", "").strip()

    qs = DersProgrami.objects.select_related("ogretmen", "sinif_sube", "ders_saati", "ders").order_by(
        "ogretmen__adi_soyadi", "gun", "ders_saati__derssaati_no"
    )

    if ogretmen_id:
        try:
            qs = qs.filter(ogretmen_id=int(ogretmen_id))
        except (ValueError, TypeError):
            pass
    if sinif_id:
        try:
            qs = qs.filter(sinif_sube_id=int(sinif_id))
        except (ValueError, TypeError):
            pass
    if gun:
        qs = qs.filter(gun=gun)

    tum_ogretmenler = NobetPersonel.objects.order_by("adi_soyadi")
    tum_siniflar = SinifSube.objects.order_by("sinif", "sube")

    GUNLER = [
        ("Monday", "Pazartesi"),
        ("Tuesday", "Salı"),
        ("Wednesday", "Çarşamba"),
        ("Thursday", "Perşembe"),
        ("Friday", "Cuma"),
    ]

    context = {
        "title": "Ders Programı Listesi",
        "kayitlar": qs,
        "tum_ogretmenler": tum_ogretmenler,
        "tum_siniflar": tum_siniflar,
        "gunler": GUNLER,
        "secilen_ogretmen": ogretmen_id,
        "secilen_sinif": sinif_id,
        "secilen_gun": gun,
    }
    return render(request, "dersprogrami/dersprogrami_listesi.html", context)


# ─────────────────────────────────────────────
# Öğretmen Haftalık Ders Programı Tablosu
# ─────────────────────────────────────────────


@login_required
def haftalik_ders_programi(request):
    GUN_DB = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    GUN_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]

    is_yonetici = _is_yonetici(request.user)

    secilen_personel = None
    tum_ogretmenler = None

    if is_yonetici:
        tum_ogretmenler = NobetPersonel.objects.order_by("adi_soyadi")
        ogretmen_id = request.GET.get("ogretmen", "").strip()
        if ogretmen_id:
            try:
                secilen_personel = NobetPersonel.objects.get(pk=int(ogretmen_id))
            except (NobetPersonel.DoesNotExist, ValueError, TypeError):
                pass
    else:
        try:
            secilen_personel = request.user.personel
        except NobetPersonel.DoesNotExist:
            secilen_personel = None

    program_tablo = []
    nobet_gorevleri = []
    rehberlik_siniflari = []

    if secilen_personel:
        dersler = list(
            DersProgrami.objects.filter(ogretmen=secilen_personel)
            .select_related("sinif_sube", "ders_saati", "ders")
            .order_by("ders_saati__derssaati_no")
        )
        ders_saatleri_bilgi = {}
        for d in dersler:
            if d.ders_saati and d.ders_saati.derssaati_no not in ders_saatleri_bilgi:
                ders_saatleri_bilgi[d.ders_saati.derssaati_no] = {
                    "ders_saati_adi": d.ders_saati.ders_adi,
                    "giris_saat": d.ders_saati.derssaati_baslangic,
                    "cikis_saat": d.ders_saati.derssaati_bitis,
                }
        for ds in sorted(ders_saatleri_bilgi.keys()):
            bilgi = ders_saatleri_bilgi[ds]
            cells = []
            for gun_db in GUN_DB:
                match = next(
                    (d for d in dersler if d.ders_saati and d.ders_saati.derssaati_no == ds and d.gun == gun_db), None
                )
                cells.append(match)
            program_tablo.append({
                "ders_saati": ds,
                "ders_saati_adi": bilgi["ders_saati_adi"],
                "giris_saat": bilgi["giris_saat"],
                "cikis_saat": bilgi["cikis_saat"],
                "cells": cells,
            })

        # Nöbet görevleri
        try:
            nobet_ogretmen = secilen_personel.ogretmen
            nobet_gorevleri = list(
                nobet_ogretmen.nobetler.order_by("nobet_gun")
            )
        except Exception:
            nobet_gorevleri = []

        # Rehberlik ve Yönlendirme dersi verdiği sınıflar
        rehberlik_siniflari = list(
            DersProgrami.objects.filter(
                ogretmen=secilen_personel,
                ders__ders_adi__icontains="rehberlik",
                sinif_sube__isnull=False,
            )
            .values_list("sinif_sube__sinif", "sinif_sube__sube")
            .distinct()
            .order_by("sinif_sube__sinif", "sinif_sube__sube")
        )

    context = {
        "title": "Haftalık Ders Programı",
        "is_yonetici": is_yonetici,
        "tum_ogretmenler": tum_ogretmenler,
        "secilen_personel": secilen_personel,
        "secilen_ogretmen_id": str(secilen_personel.pk) if secilen_personel else "",
        "gun_tr_list": GUN_TR,
        "program_tablo": program_tablo,
        "nobet_gorevleri": nobet_gorevleri,
        "rehberlik_siniflari": rehberlik_siniflari,
    }
    return render(request, "dersprogrami/haftalik_program.html", context)


# ─────────────────────────────────────────────
# Veri Yükleme — Haftalık Ders Programı
# ─────────────────────────────────────────────


@mudur_yardimcisi_required
def dersprogrami_yukle(request):
    form = DersProgramiImportForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        from veriaktar.services.default_path_service import DefaultPath
        from veriaktar.services.ders_programi_import_service import DersProgramiIsleyici

        dp = DefaultPath()
        try:
            f = request.FILES["dosya"]
            tarih = form.cleaned_data["uygulama_tarihi"]
            file_path = dp.VERI_DIR / f.name
            with open(file_path, "wb+") as dest:
                for chunk in f.chunks():
                    dest.write(chunk)
            DersProgramiIsleyici(file_path=str(file_path), uygulama_tarihi=tarih).calistir()
            messages.success(request, "Ders programı başarıyla aktarıldı.")
        except Exception as e:
            messages.error(request, f"Hata oluştu: {str(e)}")
        return redirect("dersprogrami_yukle")

    context = {
        "title": "Ders Programı Yükle",
        "form": form,
        "toplam": DersProgrami.objects.count(),
    }
    return render(request, "dersprogrami/dersprogrami_yukle.html", context)
