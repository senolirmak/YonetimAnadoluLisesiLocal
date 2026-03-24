from datetime import date as dt_date
from datetime import datetime, timedelta
from datetime import time as dt_time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cagri.models import OgrenciCagri
from dersprogrami.models import NobetDersProgrami
from devamsizlik.models import OgrenciDevamsizlik
from faaliyet.models import Faaliyet
from nobet.models import (
    EgitimOgretimYili,
    GunlukNobetCizelgesi,
    NobetAtanamayan,
    NobetGecmisi,
    NobetGorevi,
    NobetPersonel,
    OkulBilgi,
    OkulDonem,
)

from .forms import EgitimOgretimYiliForm, OkulBilgiAyarForm, OkulDonemForm
from ogrencinobet.models import OgrenciNobetGorevi
from personeldevamsizlik.models import Devamsizlik
from utility.constants import WEEKDAY_TO_DB as _WEEKDAY_TO_DB


def _only_ogretmen(user):
    """Sadece ogretmen grubunda olup yönetici gruplarında olmayan kullanıcı."""
    if user.is_superuser:
        return False
    gruplar = set(user.groups.values_list("name", flat=True))
    yonetici = {"mudur_yardimcisi", "okul_muduru", "rehber_ogretmen", "disiplin_kurulu"}
    return "ogretmen" in gruplar and not (gruplar & yonetici)


def _ogretmen_menu_gorumu(user):
    """ogretmen + rehber_ogretmen + disiplin_kurulu → nöbet okuma sayfalarına erişim."""
    if user.is_superuser:
        return False
    gruplar = set(user.groups.values_list("name", flat=True))
    ust_yonetici = {"mudur_yardimcisi", "okul_muduru"}
    return bool(gruplar & {"ogretmen", "rehber_ogretmen", "disiplin_kurulu"}) and not (
        gruplar & ust_yonetici
    )


_DAYS_MAP = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}
_GUN_TR = {
    "Monday": "Pazartesi",
    "Tuesday": "Salı",
    "Wednesday": "Çarşamba",
    "Thursday": "Perşembe",
    "Friday": "Cuma",
}
_TR_GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]


@login_required
def index(request):
    okul_bilgi = OkulBilgi.objects.select_related("okul_donem", "okul_donem__egitim_yili", "okul_egtyil").first()

    today = timezone.localdate()
    day_name_en = _WEEKDAY_TO_DB.get(today.weekday(), "Monday")

    toplam_ogretmen = NobetPersonel.objects.count()
    ucretli_ogretmen = NobetPersonel.objects.filter(gorev_tipi__icontains="Ücretli").count()

    devamsiz_ogretmen = (
        Devamsizlik.objects.filter(baslangic_tarihi__lte=today)
        .filter(Q(bitis_tarihi__gte=today) | Q(bitis_tarihi__isnull=True))
        .values("ogretmen")
        .distinct()
        .count()
    )

    gorev_date = (
        NobetGorevi.objects.filter(uygulama_tarihi__lte=today)
        .order_by("-uygulama_tarihi")
        .values_list("uygulama_tarihi", flat=True)
        .first()
    )
    nobetci_ogretmen = (
        NobetGorevi.objects.filter(uygulama_tarihi=gorev_date, nobet_gun=day_name_en)
        .values("ogretmen")
        .distinct()
        .count()
        if gorev_date
        else 0
    )

    brans_dagilimi = (
        NobetPersonel.objects.values("brans").annotate(sayi=Count("id")).order_by("-sayi")
    )

    # Günün nöbetçi öğretmenleri (yer bilgisiyle)
    gunun_nobetci_ogretmenleri = (
        GunlukNobetCizelgesi.objects.filter(tarih=today)
        .select_related("ogretmen__personel")
        .order_by("nobet_yeri", "ogretmen__personel__adi_soyadi")
    )

    # Günün öğrenci istatistikleri
    devamsiz_kiz = (
        OgrenciDevamsizlik.objects.filter(tarih=today, ogrenci__cinsiyet="K")
        .values("ogrenci")
        .distinct()
        .count()
    )
    devamsiz_erkek = (
        OgrenciDevamsizlik.objects.filter(tarih=today, ogrenci__cinsiyet="E")
        .values("ogrenci")
        .distinct()
        .count()
    )
    faaliyet_ogrenci = (
        Faaliyet.objects.filter(tarih=today, durum=Faaliyet.DURUM_ONAYLANDI).aggregate(
            sayi=Count("ogrenciler", distinct=True)
        )["sayi"]
        or 0
    )
    rehberlik_cagri = OgrenciCagri.objects.filter(
        tarih=today, servis=OgrenciCagri.SERVIS_REHBERLIK
    ).count()
    disiplin_cagri = OgrenciCagri.objects.filter(
        tarih=today, servis=OgrenciCagri.SERVIS_DISIPLIN
    ).count()
    muduriyetcagri_cagri = OgrenciCagri.objects.filter(
        tarih=today, servis=OgrenciCagri.SERVIS_MUDURIYETCAGRI
    ).count()

    is_ogretmen = request.user.groups.filter(name="ogretmen").exists()
    personel_bagli = is_ogretmen and hasattr(request.user, "personel")

    # Rehberlik ve Yönlendirme dersi varsa sınıf/şube bilgisini bul
    rehberlik_sinif_sube = None
    ogretmen_nobetleri = []
    atanan_dersler = []
    if personel_bagli:
        rehberlik_ders = (
            NobetDersProgrami.objects.filter(
                ogretmen=request.user.personel,
                ders_adi__iexact="rehberlik ve yönlendirme",
            )
            .select_related("sinif_sube")
            .first()
        )
        if rehberlik_ders and rehberlik_ders.sinif_sube:
            rehberlik_sinif_sube = str(rehberlik_ders.sinif_sube)

        # Öğretmenin nöbet görevleri (son uygulama tarihine göre)
        try:
            nobet_ogretmen = request.user.personel.ogretmen
            son_uygulama = (
                NobetGorevi.objects.filter(ogretmen=nobet_ogretmen)
                .order_by("-uygulama_tarihi")
                .values_list("uygulama_tarihi", flat=True)
                .first()
            )
            if son_uygulama:
                ogretmen_nobetleri = [
                    {
                        "gun": _GUN_TR.get(n.nobet_gun, n.nobet_gun),
                        "yer": n.nobet_yeri,
                    }
                    for n in NobetGorevi.objects.filter(
                        ogretmen=nobet_ogretmen, uygulama_tarihi=son_uygulama
                    ).order_by("nobet_gun")
                ]

            # Bugün atanan ders doldurma görevleri
            atanan_dersler = list(
                NobetGecmisi.objects.filter(ogretmen=nobet_ogretmen, tarih__date=today).order_by(
                    "saat"
                )
            )
        except Exception:
            pass

    gunun_nobetci_ogrencileri = list(
        OgrenciNobetGorevi.objects.filter(tarih=today)
        .select_related("ogrenci")
        .order_by("ogrenci__sinif", "ogrenci__sube", "ogrenci__okulno")
    )

    # Öğretmenin sınav gözetim görevi var mı?
    sinav_gozetim_var = False
    if hasattr(request.user, "personel") and request.user.personel:
        try:
            from sinav.models import (
                SinavBilgisi as _SinavBilgisi,
                TakvimUretim as _TakvimUretim,
                OturmaPlani as _OturmaPlani,
                DersProgram as _DersProgram,
            )
            _ogretmen_adi = request.user.personel.adi_soyadi
            _aktif_sinav = _SinavBilgisi.objects.filter(aktif=True).first()
            if _aktif_sinav:
                _aktif_uretim = _TakvimUretim.objects.filter(
                    sinav=_aktif_sinav, aktif=True
                ).first()
                if _aktif_uretim:
                    from sinav.utils import gozetmen_bul as _gozetmen_bul
                    for slot in (
                        _OturmaPlani.objects
                        .filter(uretim=_aktif_uretim)
                        .values("tarih", "saat")
                        .distinct()
                        .order_by("tarih", "saat")
                    ):
                        _tarih  = slot["tarih"]
                        _saat   = slot["saat"]
                        _subeler = list(
                            _OturmaPlani.objects
                            .filter(uretim=_aktif_uretim, tarih=_tarih, saat=_saat)
                            .order_by("sinifsube")
                            .values_list("sinifsube", flat=True)
                            .distinct()
                        )
                        if any(
                            _gozetmen_bul(_aktif_sinav, _tarih, _saat, ss) == _ogretmen_adi
                            for ss in _subeler
                        ):
                            sinav_gozetim_var = True
                            break
        except Exception:
            pass

    return render(
        request,
        "main/index.html",
        {
            "title": "Anasayfa",
            "okul_bilgi": okul_bilgi,
            "gunun_nobetci_ogrencileri": gunun_nobetci_ogrencileri,
            "gunun_nobetci_ogretmenleri": gunun_nobetci_ogretmenleri,
            "is_ogretmen": is_ogretmen,
            "personel_bagli": personel_bagli,
            "rehberlik_sinif_sube": rehberlik_sinif_sube,
            "ogretmen_nobetleri": ogretmen_nobetleri,
            "atanan_dersler": atanan_dersler,
            "sinav_gozetim_var": sinav_gozetim_var,
            "personel_istatistik": {
                "toplam": toplam_ogretmen,
                "ucretli": ucretli_ogretmen,
                "devamsiz": devamsiz_ogretmen,
                "nobetci": nobetci_ogretmen,
                "brans_dagilimi": brans_dagilimi,
            },
            "ogrenci_istatistik": {
                "devamsiz_kiz": devamsiz_kiz,
                "devamsiz_erkek": devamsiz_erkek,
                "faaliyet": faaliyet_ogrenci,
                "rehberlik_cagri": rehberlik_cagri,
                "disiplin_cagri": disiplin_cagri,
                "muduriyetcagri_cagri": muduriyetcagri_cagri,
            },
        },
    )


# ─────────────────────────────────────────────
# Öğretmen — Haftalık Nöbet Listesi (salt okunur)
# ─────────────────────────────────────────────


@login_required
def ogretmen_haftalik_nobet(request):
    if not _ogretmen_menu_gorumu(request.user):
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
            "main/ogretmen_haftalik_nobet.html",
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

    nobet_yerleri = sorted(set(nobetler.values_list("nobet_yeri", flat=True)))
    veri_matrisi = {yer: {g: [] for g in _TR_GUNLER} for yer in nobet_yerleri}

    for nobet in nobetler:
        gun_tr = _GUN_TR.get(nobet.nobet_gun)
        if gun_tr and nobet.nobet_yeri in veri_matrisi:
            veri_matrisi[nobet.nobet_yeri][gun_tr].append(nobet.ogretmen.personel.adi_soyadi)

    tablo_satirlari = [
        {"yer": yer, "hucreler": [veri_matrisi[yer][gun] for gun in _TR_GUNLER]}
        for yer in nobet_yerleri
    ]

    return render(
        request,
        "main/ogretmen_haftalik_nobet.html",
        {
            "title": "Haftalık Nöbet Listesi",
            "gunler": _TR_GUNLER,
            "tablo_satirlari": tablo_satirlari,
            "baslangic": pazartesi,
            "bitis": cuma,
            "uygulama_tarihi": secili,
            "onceki": onceki.isoformat() if onceki else None,
            "sonraki": sonraki.isoformat() if sonraki else None,
        },
    )


# ─────────────────────────────────────────────
# Öğretmen — Günün Nöbetçileri (salt okunur)
# ─────────────────────────────────────────────


@login_required
def ogretmen_gunun_nobetcileri(request):
    if not _ogretmen_menu_gorumu(request.user):
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
        "main/ogretmen_gunun_nobetcileri.html",
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
    if not _ogretmen_menu_gorumu(request.user):
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
        "main/ogretmen_ders_doldurma.html",
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
# Öğretmen — Sınav Gözetim Listesi
# ─────────────────────────────────────────────


@login_required
def ogretmen_sinav_gozetim(request):
    if not _ogretmen_menu_gorumu(request.user):
        raise PermissionDenied

    from sinav.models import SinavBilgisi, TakvimUretim, OturmaPlani, DersProgram
    from sinav.utils import gozetmen_bul, onceki_ders_saati

    try:
        ogretmen_adi = request.user.personel.adi_soyadi
    except Exception:
        ogretmen_adi = None

    if not ogretmen_adi:
        return render(request, "main/ogretmen_sinav_gozetim.html", {
            "title": "Sınav Gözetim Listem",
            "hata": "Kullanıcınıza bağlı öğretmen kaydı bulunamadı.",
        })

    aktif_sinav = SinavBilgisi.objects.filter(aktif=True).first()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    now_local   = timezone.localtime()
    bugun       = now_local.date()
    simdi_str   = now_local.strftime("%H:%M")

    gozetim_slotlari = []
    if aktif_uretim:
        for slot in (
            OturmaPlani.objects
            .filter(uretim=aktif_uretim)
            .values("tarih", "saat")
            .distinct()
            .order_by("tarih", "saat")
        ):
            tarih = slot["tarih"]
            saat  = slot["saat"]
            sinifsubeler = list(
                OturmaPlani.objects
                .filter(uretim=aktif_uretim, tarih=tarih, saat=saat)
                .order_by("sinifsube")
                .values_list("sinifsube", flat=True)
                .distinct()
            )
            eslesen = [
                ss for ss in sinifsubeler
                if gozetmen_bul(aktif_sinav, tarih, saat, ss) == ogretmen_adi
            ]
            if not eslesen:
                continue
            _onceki_saat = onceki_ders_saati(saat)
            _aktif = (
                tarih == bugun
                and _onceki_saat is not None
                and simdi_str >= _onceki_saat
            )
            # Medya butonu için: (Uygulama) slotları + öğretmenin seviyelerine ait medyalar
            seviyeler = set()
            for ss in eslesen:
                try:
                    seviyeler.add(int(ss.split("-")[0].strip()))
                except (ValueError, IndexError):
                    pass

            from sinavmedia.models import SinavMedia
            from sinav.models import Takvim as TakvimModel
            uygulama_takvimler = TakvimModel.objects.filter(
                sinav=aktif_sinav, uretim=aktif_uretim,
                tarih=tarih, saat=saat, ders_adi__icontains="(Uygulama)",
            )
            medyalar = []
            for t in uygulama_takvimler:
                for sev in sorted(seviyeler):
                    try:
                        m = SinavMedia.objects.get(takvim=t, seviye=sev)
                        medyalar.append({"pk": m.pk, "label": m.get_seviye_display()})
                    except SinavMedia.DoesNotExist:
                        pass

            gozetim_slotlari.append({
                "tarih":       tarih,
                "saat":        saat,
                "onceki_saat": _onceki_saat,
                "siniflar":    eslesen,
                "aktif":       _aktif,
                "medyalar":    medyalar,
            })

    return render(request, "main/ogretmen_sinav_gozetim.html", {
        "title":            "Sınav Gözetim Listem",
        "ogretmen_adi":     ogretmen_adi,
        "aktif_sinav":      aktif_sinav,
        "aktif_uretim":     aktif_uretim,
        "gozetim_slotlari": gozetim_slotlari,
    })


# ─────────────────────────────────────────────
# Öğretmen — Gözetim Sınıf Listesi Detayı
# ─────────────────────────────────────────────


@login_required
def ogretmen_gozetim_sinif_listesi(request):
    if not _ogretmen_menu_gorumu(request.user):
        raise PermissionDenied

    from nobet.models import SinifSube
    from sinav.models import SinavBilgisi, TakvimUretim, OturmaPlani
    from sinav.utils import gozetmen_bul, onceki_ders_saati

    tarih_str = request.GET.get("tarih", "")
    saat      = request.GET.get("saat", "")
    sinifsube = request.GET.get("sinifsube", "")

    try:
        tarih = dt_date.fromisoformat(tarih_str)
    except (ValueError, TypeError):
        tarih = None

    aktif_sinav  = SinavBilgisi.objects.filter(aktif=True).first()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    ogrenciler = []
    ogretmen_adi = None
    ders_adi = ""
    salon_raw = None
    if tarih and saat and sinifsube and aktif_uretim:
        salon_map = {
            f"Salon-{ss.sinif}_{ss.sube}": ss.salon
            for ss in SinifSube.objects.all()
        }
        ogretmen_adi = gozetmen_bul(aktif_sinav, tarih, saat, sinifsube)
        qs = (
            OturmaPlani.objects
            .filter(uretim=aktif_uretim, tarih=tarih, saat=saat, sinifsube=sinifsube)
            .order_by("salon", "sira_no")
        )
        ders_adi = qs.values_list("ders_adi", flat=True).first() or ""
        salon_raw = qs.values_list("salon", flat=True).first()
        ogrenciler = [
            {
                "sira_no":    o.sira_no,
                "okulno":     o.okulno,
                "adi_soyadi": o.adi_soyadi,
                "salon":      salon_map.get(o.salon, o.salon),
            }
            for o in qs
        ]

    return render(request, "main/ogretmen_gozetim_sinif_listesi.html", {
        "title":        f"Sınıf Listesi – {sinifsube}",
        "tarih":        tarih,
        "saat":         saat,
        "sinifsube":    sinifsube,
        "ders_adi":     ders_adi,
        "onceki_saat":  onceki_ders_saati(saat) if saat else None,
        "ogretmen_adi": ogretmen_adi,
        "ogrenciler":   ogrenciler,
        "aktif_sinav":  aktif_sinav,
        "salon":        salon_raw,
    })


# ─────────────────────────────────────────────────────────
# Sınav Salon Yoklaması
# ─────────────────────────────────────────────────────────

def sinav_salon_yoklama(request):
    if not _ogretmen_menu_gorumu(request.user):
        raise PermissionDenied

    from sinav.models import SinavBilgisi, TakvimUretim, OturmaPlani, SinavSalonYoklama

    tarih_str = request.GET.get("tarih", "")
    saat      = request.GET.get("saat", "")
    salon     = request.GET.get("salon", "")

    try:
        tarih = dt_date.fromisoformat(tarih_str)
    except (ValueError, TypeError):
        tarih = None

    aktif_sinav  = SinavBilgisi.objects.filter(aktif=True).first()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    # POST → kaydet
    if request.method == "POST" and tarih and saat and salon and aktif_uretim:
        ogrenciler_qs = OturmaPlani.objects.filter(
            uretim=aktif_uretim, tarih=tarih, saat=saat, salon=salon
        )
        for o in ogrenciler_qs:
            durum = request.POST.get(f"durum_{o.okulno}", "mevcut")
            SinavSalonYoklama.objects.update_or_create(
                uretim=aktif_uretim,
                tarih=tarih,
                saat=saat,
                salon=salon,
                okulno=o.okulno,
                defaults={
                    "adi_soyadi": o.adi_soyadi,
                    "sinifsube":  o.sinifsube,
                    "sira_no":    o.sira_no,
                    "durum":      durum,
                    "kaydeden":   request.user,
                },
            )
        from django.contrib import messages
        messages.success(request, f"{salon} – {saat} yoklaması kaydedildi.")
        return redirect(
            f"{request.path}?tarih={tarih_str}&saat={saat}&salon={salon}"
        )

    # GET → yoklama formunu hazırla
    ogrenciler = []
    mevcut_yoklama = {}
    if tarih and saat and salon and aktif_uretim:
        qs = OturmaPlani.objects.filter(
            uretim=aktif_uretim, tarih=tarih, saat=saat, salon=salon
        ).order_by("sira_no")

        mevcut_yoklama = {
            y.okulno: y.durum
            for y in SinavSalonYoklama.objects.filter(
                uretim=aktif_uretim, tarih=tarih, saat=saat, salon=salon
            )
        }

        ogrenciler = [
            {
                "sira_no":    o.sira_no,
                "okulno":     o.okulno,
                "adi_soyadi": o.adi_soyadi,
                "sinifsube":  o.sinifsube,
                "ders_adi":   o.ders_adi,
                "durum":      mevcut_yoklama.get(o.okulno, "mevcut"),
            }
            for o in qs
        ]

    yoklama_alindi = bool(mevcut_yoklama)

    return render(request, "main/sinav_salon_yoklama.html", {
        "title":            f"Salon Yoklaması – {salon}",
        "tarih":            tarih,
        "saat":             saat,
        "salon":            salon,
        "ogrenciler":       ogrenciler,
        "yoklama_alindi":   yoklama_alindi,
        "aktif_sinav":      aktif_sinav,
        "durum_secenekleri": [
            ("mevcut", "Mevcut", "green"),
            ("yok",    "Yok",    "red"),
            ("gec",    "Geç",    "orange"),
        ],
    })


# ─────────────────────────────────────────────────────────
# Okul Yapılandırması
# ─────────────────────────────────────────────────────────

@login_required
def okul_ayarlari(request):
    user = request.user
    if not (user.is_superuser or user.groups.filter(name="mudur_yardimcisi").exists()):
        raise PermissionDenied

    okul = OkulBilgi.objects.select_related("okul_donem", "okul_egtyil").first()
    egitim_yillari = EgitimOgretimYili.objects.prefetch_related("donemleri").order_by("-egitim_yili")

    # Hangi form POST edildi?
    action = request.POST.get("action", "") if request.method == "POST" else ""

    # ── Okul Bilgileri formu ──────────────────────────────
    okul_form = OkulBilgiAyarForm(
        request.POST if action == "okul_bilgi" else None,
        instance=okul,
    )
    if action == "okul_bilgi" and okul_form.is_valid():
        okul_form.save()
        messages.success(request, "Okul bilgileri güncellendi.")
        return redirect("okul_ayarlari")

    # ── Eğitim Yılı formu ────────────────────────────────
    eyil_pk = request.POST.get("eyil_pk", "").strip()
    eyil_instance = get_object_or_404(EgitimOgretimYili, pk=eyil_pk) if eyil_pk else None
    eyil_form = EgitimOgretimYiliForm(
        request.POST if action == "egitim_yili" else None,
        instance=eyil_instance,
    )
    if action == "egitim_yili" and eyil_form.is_valid():
        yil = eyil_form.save()
        msg = "güncellendi" if eyil_pk else "eklendi"
        if not eyil_pk:
            messages.info(request, f"'{yil.egitim_yili}' eklendi. Lütfen dönem tarihlerini giriniz.")
        else:
            messages.success(request, f"'{yil.egitim_yili}' {msg}.")
        return redirect("okul_ayarlari")

    # ── Dönem formu ───────────────────────────────────────
    donem_pk = request.POST.get("donem_pk", "").strip()
    donem_instance = get_object_or_404(OkulDonem, pk=donem_pk) if donem_pk else None
    donem_form = OkulDonemForm(
        request.POST if action == "donem" else None,
        instance=donem_instance,
    )
    if action == "donem" and donem_form.is_valid():
        donem_form.save()
        messages.success(request, "Dönem kaydedildi.")
        return redirect("okul_ayarlari")

    # Hatalı POST durumunda hangi formu açık tutacağız?
    aktif_form = action if action in ("okul_bilgi", "egitim_yili", "donem") else None

    context = {
        "title": "Okul Yapılandırması",
        "okul": okul,
        "okul_form": okul_form,
        "egitim_yillari": egitim_yillari,
        "eyil_form": eyil_form,
        "eyil_pk": eyil_pk,
        "donem_form": donem_form,
        "donem_pk": donem_pk,
        "aktif_form": aktif_form,
    }
    return render(request, "main/okul_ayarlari.html", context)
