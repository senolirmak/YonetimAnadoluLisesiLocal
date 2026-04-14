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
from dersprogrami.models import DersProgrami
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

    _gruplar = set(request.user.groups.values_list("name", flat=True))
    _yonetici_gruplar = {"mudur_yardimcisi", "okul_muduru", "rehber_ogretmen", "disiplin_kurulu"}
    _salt_ogretmen = not request.user.is_superuser and "ogretmen" in _gruplar and not bool(_gruplar & _yonetici_gruplar)
    personel_bagli = _salt_ogretmen and hasattr(request.user, "personel")

    # Rehberlik ve Yönlendirme dersi varsa sınıf/şube bilgisini bul
    rehberlik_sinif_sube = None
    ogretmen_nobetleri = []
    atanan_dersler = []
    if personel_bagli:
        rehberlik_ders = (
            DersProgrami.objects.filter(
                ogretmen=request.user.personel,
                ders__ders_adi__iexact="rehberlik ve yönlendirme",
            )
            .select_related("sinif_sube", "ders")
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

    # Sınav: aktif üretim var mı? + öğretmenin gözetim görevi var mı?
    sinav_gozetim_var = False
    sinav_aktif_var   = False
    if hasattr(request.user, "personel") and request.user.personel:
        try:
            from sinav.models import (
                SinavBilgisi as _SinavBilgisi,
                TakvimUretim as _TakvimUretim,
                OturmaPlani as _OturmaPlani,
            )
            _personel = request.user.personel
            _aktif_sinav = _SinavBilgisi.objects.filter(aktif=True).first()
            if _aktif_sinav:
                _aktif_uretim = _TakvimUretim.objects.filter(
                    sinav=_aktif_sinav, aktif=True
                ).first()
                if _aktif_uretim:
                    sinav_aktif_var = True
                    sinav_gozetim_var = _OturmaPlani.objects.filter(
                        uretim=_aktif_uretim,
                        gozetmen_fk=_personel,
                    ).exists()
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
            "personel_bagli": personel_bagli,
            "rehberlik_sinif_sube": rehberlik_sinif_sube,
            "ogretmen_nobetleri": ogretmen_nobetleri,
            "atanan_dersler": atanan_dersler,
            "sinav_gozetim_var": sinav_gozetim_var,
            "sinav_aktif_var":   sinav_aktif_var,
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
# Nöbet devir: nöbetçi öğretmenin sınav slotları
# ─────────────────────────────────────────────

def _nobetci_gozetim_slotlari(personel, aktif_uretim):
    """
    Devamsız öğretmen yerine sınıfa giren nöbetçi öğretmenin
    üstlendiği sınav gözetim slotlarını döndürür.

    Eşleşme mantığı:
      NobetGecmisi.tarih.date()  ==  OturmaPlani.tarih
      NobetGecmisi.saat          ==  Takvim.ders_saati.derssaati_no
                                     → Takvim.saat → OturmaPlani.saat
      NobetGecmisi.sinif ("9/A") ==  OturmaPlani.salon_sinif_sube (sinif=9, sube="A")
    """
    from nobet.models import NobetGecmisi
    from sinav.models import OturmaPlani, Takvim
    from sinav.utils import salon_goster

    if not (personel and aktif_uretim):
        return []

    # Bu öğretmenin NobetOgretmen kaydı (OneToOne via related_name="ogretmen")
    try:
        nobet_ogr = personel.ogretmen
    except Exception:
        return []

    gecmisler = list(
        NobetGecmisi.objects
        .filter(ogretmen=nobet_ogr, atandi=1, sinif__isnull=False)
        .values("tarih", "saat", "sinif")
    )
    if not gecmisler:
        return []

    # OturmaPlani'nin kapsadığı tarih aralığını al (gereksiz sorguları önler)
    sinav_tarihler = set(
        OturmaPlani.objects
        .filter(uretim=aktif_uretim)
        .values_list("tarih", flat=True)
        .distinct()
    )

    slotlar = []
    seen = set()

    for g in gecmisler:
        tarih = g["tarih"].date() if hasattr(g["tarih"], "date") else g["tarih"]
        if tarih not in sinav_tarihler:
            continue

        sinif_str = (g["sinif"] or "").strip()
        parts = sinif_str.split("/")
        if len(parts) != 2:
            continue
        try:
            sinif_no = int(parts[0])
        except ValueError:
            continue
        sube_str = parts[1].strip()

        # NobetGecmisi.saat → Takvim.saat (ders_saati FK üzerinden)
        # Takvim.ders_saati.derssaati_no == NobetGecmisi.saat
        ders_no = g["saat"]
        if ders_no:
            sinav_saatleri = set(
                Takvim.objects
                .filter(uretim=aktif_uretim, tarih=tarih,
                        ders_saati__derssaati_no=ders_no)
                .values_list("saat", flat=True)
                .distinct()
            )
        else:
            sinav_saatleri = None  # saat bilgisi yoksa tüm slotlara bak

        op_filtre = dict(
            uretim=aktif_uretim,
            tarih=tarih,
            salon_sinif_sube__sinif=sinif_no,
            salon_sinif_sube__sube=sube_str,
        )
        if sinav_saatleri is not None:
            op_filtre["saat__in"] = sinav_saatleri

        op_qs = (
            OturmaPlani.objects
            .filter(**op_filtre)
            .values(
                "tarih", "saat", "oturum", "salon",
                "salon_sinif_sube__sinif",
                "salon_sinif_sube__sube",
            )
            .distinct()
            .order_by("tarih", "saat", "oturum")
        )

        for row in op_qs:
            key = (row["tarih"], row["saat"], row["oturum"])
            if key in seen:
                continue
            seen.add(key)
            sinif = row["salon_sinif_sube__sinif"]
            sube  = row["salon_sinif_sube__sube"]
            salon = row["salon"] or ""
            slotlar.append({
                "tarih":      row["tarih"],
                "saat":       row["saat"],
                "oturum":     row["oturum"],
                "salonlar":   [{"ham": salon, "ad": salon_goster(salon)}] if salon else [],
                "sinifsube":  f"{sinif}/{sube}" if sinif and sube else sinif_str,
                "nobet_devir": True,
            })

    return sorted(slotlar, key=lambda x: (x["tarih"], x["saat"], x["oturum"]))


# ─────────────────────────────────────────────
# Öğretmen — Sınav Gözetim Listesi
# ─────────────────────────────────────────────


@login_required
def ogretmen_sinav_gozetim(request):
    is_admin = request.user.is_staff or request.user.is_superuser
    preview_id = request.GET.get("preview_ogretmen_id", "").strip()
    if not is_admin and not _ogretmen_menu_gorumu(request.user):
        raise PermissionDenied

    is_preview = bool(preview_id and is_admin)

    from sinav.utils import AdminOverride, slot_listesi_aktif_isle
    # force_aktif yalnızca superuser'ın aktif önizleme modunda geçerli;
    # normal öğretmen sayfasını hiçbir şekilde etkilemez.
    force_aktif = is_preview and AdminOverride.is_active(request)

    from sinav.models import SinavBilgisi, TakvimUretim, OturmaPlani
    from sinav.utils import onceki_ders_saati, salon_goster, slot_aktif_mi

    # Admin önizleme: ?preview_ogretmen_id=PK parametresi yalnızca yöneticiler için geçerlidir
    if preview_id and is_admin:
        from okul.models import Personel as _Personel
        personel = _Personel.objects.filter(pk=preview_id).first()
        ogretmen_adi = personel.adi_soyadi if personel else None
    else:
        personel = getattr(request.user, "personel", None)
        try:
            ogretmen_adi = personel.adi_soyadi if personel else None
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

    now_local = timezone.localtime()
    bugun     = now_local.date()
    simdi_str = now_local.strftime("%H:%M")

    # ── Superuser tarih/saat simülasyonu: ?sim_tarih=2026-04-06&sim_saat=08:30 ─
    sim_aktif = False
    if is_admin:
        _sim_tarih = request.GET.get("sim_tarih", "").strip()
        _sim_saat  = request.GET.get("sim_saat",  "").strip()
        if _sim_tarih:
            try:
                bugun     = dt_date.fromisoformat(_sim_tarih)
                sim_aktif = True
            except ValueError:
                pass
        if _sim_saat and len(_sim_saat) == 5 and ":" in _sim_saat:
            simdi_str = _sim_saat
            sim_aktif = True

    gozetim_slotlari = []
    if aktif_uretim:
        # 1. Öğretmenin gözetmen olduğu (tarih, saat, oturum) slotları
        slots = (
            OturmaPlani.objects
            .filter(uretim=aktif_uretim, gozetmen_fk=personel)
            .values("tarih", "saat", "oturum")
            .distinct()
            .order_by("tarih", "saat", "oturum")
        )
        for slot in slots:
            tarih  = slot["tarih"]
            saat   = slot["saat"]
            oturum = slot["oturum"]

            # 2. Bu slot için sinifsube ve salon listesi
            op_qs = (
                OturmaPlani.objects
                .filter(uretim=aktif_uretim, tarih=tarih, saat=saat, oturum=oturum,
                        gozetmen_fk=personel)
                .values("salon")
                .distinct()
                .order_by("salon")
            )
            salonlar_raw = []
            for row in op_qs:
                if row["salon"] and row["salon"] not in salonlar_raw:
                    salonlar_raw.append(row["salon"])

            salonlar = [{"ham": s, "ad": salon_goster(s)} for s in salonlar_raw]

            gozetim_slotlari.append({
                "tarih":    tarih,
                "saat":     saat,
                "oturum":   oturum,
                "salonlar": salonlar,
            })

    # ── Uygulama sınavı medyaları: gozetim slotlarına ekle ───────────────────
    if aktif_uretim and gozetim_slotlari:
        from sinav.models import Takvim as _Takvim
        from sinavmedia.models import SinavMedia as _SM

        # (tarih, saat) → {seviye: {"pk": ..., "serbest": ...}}
        uygulama_map = {}
        for m in (
            _SM.objects
            .filter(takvim__uretim=aktif_uretim)
            .select_related("takvim")
        ):
            key = (m.takvim.tarih, m.takvim.saat)
            uygulama_map.setdefault(key, {})[m.seviye] = {"pk": m.pk, "serbest": m.serbest}

        for slot in gozetim_slotlari:
            key = (slot["tarih"], slot["saat"])
            media_map = uygulama_map.get(key, {})
            if not media_map:
                slot["medyalar"] = []
                slot["medya_serbest"] = False
                continue

            # Seviye eşleşmesinden bağımsız: bu slotta herhangi bir serbest medya var mı?
            slot_medya_serbest = any(v["serbest"] for v in media_map.values())

            # Salondaki seviye(ler)i bul
            sinifsubeler = (
                OturmaPlani.objects
                .filter(uretim=aktif_uretim, tarih=slot["tarih"],
                        saat=slot["saat"], oturum=slot["oturum"],
                        gozetmen_fk=personel)
                .values_list("sinifsube", flat=True)
                .distinct()
            )
            seviyeler = set()
            for ss in sinifsubeler:
                try:
                    seviyeler.add(int(str(ss).split("/")[0]))
                except (ValueError, AttributeError):
                    pass
            medyalar = [
                {"pk": media_map[sev]["pk"], "seviye_adi": f"{sev}. Sınıf",
                 "serbest": media_map[sev]["serbest"]}
                for sev in sorted(seviyeler)
                if sev in media_map
            ]
            # Seviye eşleşmesi olmasa bile serbest medya varsa link gösterilebilsin
            if not medyalar and slot_medya_serbest:
                medyalar = [
                    {"pk": v["pk"], "seviye_adi": "", "serbest": True}
                    for v in media_map.values()
                    if v["serbest"]
                ]
            slot["medyalar"] = medyalar
            slot["medya_serbest"] = slot_medya_serbest

    # ── Nöbet devir: nöbetçi öğretmenin üstlendiği sınav slotları ──────────────
    if aktif_uretim and personel:
        nobet_slotlari = _nobetci_gozetim_slotlari(personel, aktif_uretim)
        mevcut_gozetim_keyler = {(s["tarih"], s["saat"], s["oturum"]) for s in gozetim_slotlari}
        for s in nobet_slotlari:
            if (s["tarih"], s["saat"], s["oturum"]) not in mevcut_gozetim_keyler:
                s.setdefault("medyalar", [])
                s.setdefault("medya_serbest", False)
                gozetim_slotlari.append(s)
        gozetim_slotlari.sort(key=lambda x: (x["tarih"], x["saat"], x["oturum"]))

    # ── Ders-Sınav eşleştirme (servis üzerinden) ─────────────────────────────
    from sinav.services.ders_sinav_eslestir import tum_siniflistesi_eslestir
    from collections import defaultdict

    # Sınıf Listesi PDF: sınav öncesi son dersin öğretmeni bulunur (bitis bazlı eşleşme)
    _siniflistesi_map = tum_siniflistesi_eslestir(aktif_uretim)
    siniflistesi_slotlari = _siniflistesi_map.get(ogretmen_adi, [])

    # Saat kısıtlarını uygula
    slot_listesi_aktif_isle(gozetim_slotlari,     "gozetim",      bugun, simdi_str)
    slot_listesi_aktif_isle(siniflistesi_slotlari, "siniflistesi", bugun, simdi_str)

    # Önizleme modunda superuser tüm linkleri zorla aktif edebilir
    if force_aktif:
        for s in gozetim_slotlari + siniflistesi_slotlari:
            s["aktif"] = True

    # Tüm slot tiplerini tarih bazında birleştir
    _grp: dict = defaultdict(lambda: {"gozetim": [], "siniflistesi": []})
    for s in gozetim_slotlari:
        _grp[s["tarih"]]["gozetim"].append(s)
    for s in siniflistesi_slotlari:
        _grp[s["tarih"]]["siniflistesi"].append(s)
    tarih_gruplari = [
        {"tarih": t, "gozetim": g["gozetim"], "siniflistesi": g["siniflistesi"]}
        for t, g in sorted(_grp.items())
    ]

    title = f"Sınav Gözetim Listem — {ogretmen_adi}" if (preview_id and is_admin) else "Sınav Gözetim Listem"
    return render(request, "main/ogretmen_sinav_gozetim.html", {
        "title":          title,
        "ogretmen_adi":   ogretmen_adi,
        "aktif_sinav":    aktif_sinav,
        "aktif_uretim":   aktif_uretim,
        "tarih_gruplari": tarih_gruplari,
        "is_preview":     is_preview,
        "force_aktif":    force_aktif,
        "sim_aktif":      sim_aktif,
        "sim_bugun":      bugun   if sim_aktif else None,
        "sim_saat":       simdi_str if sim_aktif else None,
    })


# ─────────────────────────────────────────────
# Öğretmen — Sınav Medyası
# ─────────────────────────────────────────────

@login_required
def ogretmen_sinav_medya(request):
    is_admin = request.user.is_staff or request.user.is_superuser
    if not (is_admin or _ogretmen_menu_gorumu(request.user)):
        raise PermissionDenied

    from datetime import datetime as _dt, timedelta as _td
    from sinav.models import SinavBilgisi, TakvimUretim, OturmaPlani
    from sinavmedia.models import SinavMedia
    from sinavmedia.views import TOLERANS_DAKIKA

    preview_id = request.GET.get("preview_ogretmen_id", "").strip()
    if preview_id and is_admin:
        from okul.models import Personel as _Personel
        personel = _Personel.objects.filter(pk=preview_id).first()
    else:
        personel = getattr(request.user, "personel", None)
    ogretmen_adi = personel.adi_soyadi if personel else None

    aktif_sinav  = SinavBilgisi.objects.filter(aktif=True).first()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    # Opsiyonel filtre: belirli bir slot için ?tarih=&saat=&oturum=
    filtre_tarih  = request.GET.get("tarih", "").strip()
    filtre_saat   = request.GET.get("saat", "").strip()
    filtre_oturum = request.GET.get("oturum", "").strip()

    # ── Superuser simülasyonu ────────────────────────────────────────────────
    # Öncelik: açık sim_tarih/sim_saat → yoksa preview modunda filtre tarih/saat
    sim_aktif = False
    simdi_override = None
    if is_admin:
        from datetime import datetime as _dt2
        _sim_tarih = request.GET.get("sim_tarih", "").strip() or (filtre_tarih if preview_id else "")
        _sim_saat  = request.GET.get("sim_saat",  "").strip() or (filtre_saat  if preview_id else "")
        if _sim_tarih and _sim_saat:
            try:
                simdi_override = timezone.make_aware(
                    _dt2.strptime(f"{_sim_tarih} {_sim_saat}", "%Y-%m-%d %H:%M")
                )
                sim_aktif = True
            except ValueError:
                pass

    medya_gruplari = []
    if personel and aktif_uretim:
        # Öğretmenin gözetmen olduğu (tarih, saat, oturum) slotları
        slots_qs = (
            OturmaPlani.objects
            .filter(uretim=aktif_uretim, gozetmen_fk=personel)
            .values("tarih", "saat", "oturum")
            .distinct()
            .order_by("tarih", "saat", "oturum")
        )
        if filtre_tarih:
            slots_qs = slots_qs.filter(tarih=filtre_tarih)
        if filtre_saat:
            slots_qs = slots_qs.filter(saat=filtre_saat)
        if filtre_oturum:
            slots_qs = slots_qs.filter(oturum=filtre_oturum)
        slots = slots_qs

        # (tarih, saat) → {seviye: SinavMedia}
        media_map = {}
        for m in SinavMedia.objects.filter(
            takvim__uretim=aktif_uretim
        ).select_related("takvim"):
            key = (m.takvim.tarih, m.takvim.saat)
            media_map.setdefault(key, {})[m.seviye] = m

        for slot in slots:
            tarih, saat, oturum = slot["tarih"], slot["saat"], slot["oturum"]
            key = (tarih, saat)
            if key not in media_map:
                continue
            # Salondaki seviyeler
            sinifsubeler = (
                OturmaPlani.objects
                .filter(uretim=aktif_uretim, tarih=tarih, saat=saat,
                        oturum=oturum, gozetmen_fk=personel)
                .values_list("sinifsube", flat=True)
                .distinct()
            )
            seviyeler = set()
            for ss in sinifsubeler:
                try:
                    seviyeler.add(int(str(ss).split("/")[0]))
                except (ValueError, AttributeError):
                    pass

            simdi = simdi_override if simdi_override else timezone.now()
            medyalar = []
            for sev in sorted(seviyeler):
                if sev not in media_map[key]:
                    continue
                m = media_map[key][sev]
                if m.serbest:
                    erisim_acik = True
                else:
                    sinav_saat = _dt.strptime(m.takvim.saat, "%H:%M").time()
                    sinav_dt   = timezone.make_aware(
                        _dt.combine(m.takvim.tarih, sinav_saat)
                    )
                    erisim_acik = (
                        sinav_dt
                        <= simdi <=
                        sinav_dt + _td(minutes=TOLERANS_DAKIKA)
                    )
                medyalar.append({
                    "obj":          m,
                    "seviye_adi":   m.get_seviye_display(),
                    "ders_adi":     m.takvim.ders_tam_adi,
                    "aciklama":     m.aciklama,
                    "dosya_url":    m.dosya.url if erisim_acik else None,
                    "dosya_adi":    m.dosya.name,
                    "erisim_acik":  erisim_acik,
                    "sinav_saat":   m.takvim.saat,
                })
            if medyalar:
                medya_gruplari.append({
                    "tarih":    tarih,
                    "saat":     saat,
                    "oturum":   oturum,
                    "medyalar": medyalar,
                })

    return render(request, "main/sinav_medya.html", {
        "title":          "Sınav Medyası",
        "ogretmen_adi":   ogretmen_adi,
        "aktif_sinav":    aktif_sinav,
        "medya_gruplari": medya_gruplari,
        "sim_aktif":      sim_aktif,
        "sim_dt":         simdi_override,
    })


# ─────────────────────────────────────────────
# Öğretmen — Gözetim Sınıf Listesi Detayı
# ─────────────────────────────────────────────


@login_required
def ogretmen_gozetim_sinif_listesi(request):
    if not (request.user.is_superuser or _ogretmen_menu_gorumu(request.user)):
        raise PermissionDenied

    from okul.models import SinifSube
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
    gruplar = set(request.user.groups.values_list("name", flat=True))
    if not (
        request.user.is_superuser
        or "mudur_yardimcisi" in gruplar
        or "okul_muduru" in gruplar
        or _ogretmen_menu_gorumu(request.user)
    ):
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

    salon_ad = salon.replace("-", " ", 1).replace("_", "/") if salon else salon

    # ── Salon oturma düzeni grid: inverse snake formula ──
    # Her öğrencinin sira_no'su (group, row, col) koordinatına çevrilir.
    # Yılan düzeni: Grup 1→1-12, Grup 2→13-24, Grup 3→25-36
    # Çift satır sol→sağ, tek satır sağ→sol
    N_GROUPS, N_COLS = 3, 2

    if ogrenciler:
        max_sira = max(o["sira_no"] for o in ogrenciler)
        # Her gruptaki koltuk sayısını veriden türet (daima N_COLS'un katı)
        seats_per_group = -(-max_sira // N_GROUPS)          # ceiling div
        seats_per_group = -(-seats_per_group // N_COLS) * N_COLS  # N_COLS'a yuvarla
        n_rows = seats_per_group // N_COLS
    else:
        n_rows, seats_per_group = 6, 12

    # Boş grid: grid[row][group][col]
    grid = [[[None] * N_COLS for _ in range(N_GROUPS)] for _ in range(n_rows)]

    # DB sira_no → pozisyon: sıralı (sequential) inverse — snake YOK
    # PDF görüntü etiketi ayrıca hesaplanır (snake formülü)
    for o in ogrenciler:
        s     = o["sira_no"]
        grp   = (s - 1) // seats_per_group
        local = (s - 1) % seats_per_group
        row   = local // N_COLS
        col   = local % N_COLS              # sıralı; snake değil
        if grp < N_GROUPS and row < n_rows:
            # PDF snake etiketi: bu (row, col) pozisyonunun PDF numarası
            lcol      = col if row % 2 == 0 else (N_COLS - 1 - col)
            pdf_label = grp * seats_per_group + row * N_COLS + lcol + 1
            grid[row][grp][col] = {**o, "pdf_sira": pdf_label}

    # Boş hücrelere PDF snake etiketi yaz
    for row_idx in range(n_rows):
        for grp_idx in range(N_GROUPS):
            for col_idx in range(N_COLS):
                if grid[row_idx][grp_idx][col_idx] is None:
                    lcol      = col_idx if row_idx % 2 == 0 else (N_COLS - 1 - col_idx)
                    pdf_label = grp_idx * seats_per_group + row_idx * N_COLS + lcol + 1
                    grid[row_idx][grp_idx][col_idx] = {"pdf_sira": pdf_label, "bos": True}

    return render(request, "main/sinav_salon_yoklama.html", {
        "title":            f"Salon Yoklaması – {salon_ad}",
        "tarih":            tarih,
        "saat":             saat,
        "salon":            salon,
        "salon_ad":         salon_ad,
        "ogrenciler":       ogrenciler,
        "grid":             grid,
        "yoklama_alindi":   yoklama_alindi,
        "aktif_sinav":      aktif_sinav,
        "durum_secenekleri": [
            ("mevcut", "Mevcut", "green"),
            ("yok",    "Yok",    "red"),
            ("gec",    "Geç",    "orange"),
        ],
    })


# ─────────────────────────────────────────────────────────
# Sınav Oturum İstatistikleri
# ─────────────────────────────────────────────────────────

@login_required
def sinav_oturum_istatistik(request):
    from sinav.models import SinavBilgisi, TakvimUretim, OturmaPlani
    from django.db.models import Count

    aktif_sinav  = SinavBilgisi.objects.filter(aktif=True).first()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    oturumlar = []
    if aktif_uretim:
        qs = (
            OturmaPlani.objects
            .filter(uretim=aktif_uretim)
            .values("tarih", "saat", "oturum", "salon", "sinifsube", "ders_adi")
            .annotate(n=Count("okulno", distinct=True))
            .order_by("tarih", "saat", "oturum", "salon", "sinifsube")
        )

        # group by (tarih, saat, oturum, salon) → sonra (seviye, ders_adi) topla
        sessions = {}
        for row in qs:
            key = (row["tarih"], row["saat"], row["oturum"], row["salon"])
            sessions.setdefault(key, []).append(row)

        for (tarih, saat, oturum, salon), satirlar in sessions.items():
            # (seviye, ders_adi) bazında topla
            seviye_ders = {}
            for s in satirlar:
                seviye = s["sinifsube"].split("/")[0] if "/" in s["sinifsube"] else s["sinifsube"]
                sk = (seviye, s["ders_adi"])
                seviye_ders[sk] = seviye_ders.get(sk, 0) + s["n"]

            sinif_satirlari = [
                {"seviye": seviye, "ders_adi": ders_adi, "n": n}
                for (seviye, ders_adi), n in sorted(seviye_ders.items())
            ]
            toplam = sum(s["n"] for s in sinif_satirlari)
            salon_ad = salon.replace("-", " ", 1).replace("_", "/") if salon else salon
            oturumlar.append({
                "tarih":   tarih,
                "saat":    saat,
                "oturum":  oturum,
                "salon":   salon,
                "salon_ad": salon_ad,
                "satirlar": sinif_satirlari,
                "toplam":  toplam,
            })

    genel_toplam = sum(o["toplam"] for o in oturumlar)

    # tarih → oturum → salonlar hiyerarşisi
    tarih_gruplari = []
    for oturum_item in oturumlar:
        tarih   = oturum_item["tarih"]
        oturum  = oturum_item["oturum"]
        saat    = oturum_item["saat"]

        tarih_grup = next((g for g in tarih_gruplari if g["tarih"] == tarih), None)
        if tarih_grup is None:
            tarih_grup = {"tarih": tarih, "oturum_gruplari": []}
            tarih_gruplari.append(tarih_grup)

        ot_grup = next((g for g in tarih_grup["oturum_gruplari"]
                        if g["oturum"] == oturum), None)
        if ot_grup is None:
            ot_grup = {"oturum": oturum, "saat": saat, "salonlar": []}
            tarih_grup["oturum_gruplari"].append(ot_grup)

        ot_grup["salonlar"].append(oturum_item)

    return render(request, "main/sinav_oturum_istatistik.html", {
        "title":           "Sınav Oturum İstatistikleri",
        "aktif_sinav":     aktif_sinav,
        "tarih_gruplari":  tarih_gruplari,
        "genel_toplam":    genel_toplam,
    })


# ─────────────────────────────────────────────────────────
# Öğretmen — Yoklama Raporum
# ─────────────────────────────────────────────────────────


@login_required
def ogretmen_yoklama_raporum(request):
    if not (request.user.is_superuser or _ogretmen_menu_gorumu(request.user)):
        raise PermissionDenied

    from collections import defaultdict
    from sinav.models import SinavBilgisi, TakvimUretim, Takvim, SinavSalonYoklama
    from dersprogrami.models import DersProgrami
    from ortaksinav_engine.utils import normalize_sube_cell

    personel = getattr(request.user, "personel", None)
    if not personel:
        return render(request, "main/ogretmen_yoklama_raporum.html", {
            "title": "Yoklama Raporlarım",
            "hata": "Kullanıcınıza bağlı öğretmen kaydı bulunamadı.",
        })

    aktif_sinav  = SinavBilgisi.objects.filter(aktif=True).first()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    # Öğretmenin ders programından (ders_adi, sinifsube_str) çiftleri
    dp_qs = (
        DersProgrami.objects
        .filter(ogretmen=personel)
        .select_related("ders", "sinif_sube")
    )
    teacher_pairs = set()
    for dp in dp_qs:
        if dp.ders and dp.sinif_sube:
            teacher_pairs.add((dp.ders.ders_adi, str(dp.sinif_sube)))

    teacher_dersler = {p[0] for p in teacher_pairs}

    girdi_listesi = []

    if aktif_uretim and teacher_pairs:
        takvimler = (
            Takvim.objects
            .filter(uretim=aktif_uretim, ders__ders_adi__in=teacher_dersler)
            .select_related("ders")
            .order_by("tarih", "saat", "ders__ders_adi")
        )

        for t in takvimler:
            ders_adi  = t.ders.ders_adi
            t_subeler = normalize_sube_cell(t.subeler)
            matching  = [s for s in t_subeler if (ders_adi, s) in teacher_pairs]

            for sinifsube in matching:
                yoklamalar = list(
                    SinavSalonYoklama.objects
                    .filter(uretim=aktif_uretim, tarih=t.tarih, saat=t.saat, sinifsube=sinifsube)
                    .order_by("salon", "sira_no")
                )
                mevcut = sum(1 for y in yoklamalar if y.durum == "mevcut")
                yok    = sum(1 for y in yoklamalar if y.durum == "yok")
                gec    = sum(1 for y in yoklamalar if y.durum == "gec")
                girdi_listesi.append({
                    "tarih":          t.tarih,
                    "saat":           t.saat,
                    "oturum":         t.oturum,
                    "ders":           ders_adi,
                    "sinav_turu":     t.sinav_turu,
                    "sinifsube":      sinifsube,
                    "yoklamalar":     yoklamalar,
                    "mevcut":         mevcut,
                    "yok":            yok,
                    "gec":            gec,
                    "toplam":         len(yoklamalar),
                    "yoklama_alindi": bool(yoklamalar),
                })

    tarih_dict = defaultdict(list)
    for g in girdi_listesi:
        tarih_dict[g["tarih"]].append(g)
    tarih_gruplari = [
        {"tarih": tarih, "girdiler": girdiler}
        for tarih, girdiler in sorted(tarih_dict.items())
    ]

    return render(request, "main/ogretmen_yoklama_raporum.html", {
        "title":          "Yoklama Raporlarım",
        "aktif_sinav":    aktif_sinav,
        "aktif_uretim":   aktif_uretim,
        "tarih_gruplari": tarih_gruplari,
        "ogretmen_adi":   personel.adi_soyadi,
        "ders_sayisi":    len(teacher_dersler),
        "hata":           None if teacher_pairs else "Ders programında size atanmış ders bulunamadı.",
    })


# ─────────────────────────────────────────────────────────
# Sınıf Oturma Planı
# ─────────────────────────────────────────────────────────

@login_required
def sinif_oturma_plani(request):
    """Rehber öğretmenin sınıfının kalıcı oturma düzenini görüntüler ve kaydeder."""
    from ogrenci.models import Ogrenci, SinifOturmaDuzeni
    from okul.models import SinifSube

    user = request.user

    # Yetkili mi? Süper kullanıcı veya ders programında rehberlik dersi olan öğretmen
    if not user.is_superuser:
        if not hasattr(user, "personel"):
            raise PermissionDenied
        rehberlik_qs = DersProgrami.objects.filter(
            ogretmen=user.personel,
            ders__ders_adi__iexact="rehberlik ve yönlendirme",
        ).select_related("sinif_sube")
        if not rehberlik_qs.exists():
            raise PermissionDenied

    # Süper kullanıcı için sinif_sube parametresi ile çalışma
    sinif_sube_id = request.GET.get("sinif_sube") or request.POST.get("sinif_sube")

    if user.is_superuser and sinif_sube_id:
        sinif_sube = get_object_or_404(SinifSube, pk=sinif_sube_id)
    elif user.is_superuser:
        # Süper kullanıcıya tüm şubeleri göster
        tum_sinif_subeler = SinifSube.objects.all().order_by("sinif", "sube")
        return render(request, "main/sinif_oturma_plani.html", {
            "title": "Sınıf Oturma Planı",
            "sinif_sec": True,
            "tum_sinif_subeler": tum_sinif_subeler,
        })
    else:
        rehberlik_ders = rehberlik_qs.first()
        sinif_sube = rehberlik_ders.sinif_sube
        if not sinif_sube:
            raise PermissionDenied

    # Sınıftaki tüm öğrenciler
    ogrenciler = list(
        Ogrenci.objects.filter(sinif=sinif_sube.sinif, sube=sinif_sube.sube)
        .order_by("soyadi", "adi")
    )

    # Oturma düzeni yapılandırması — 3 grup × 2 sütun × 6 sıra
    N_GRUP  = 3
    N_KOLON_PER_GRUP = 2
    N_KOLON = N_GRUP * N_KOLON_PER_GRUP   # toplam 6 sütun
    N_SIRA  = 6

    if request.method == "POST":
        # Her hücre için: koltuk_<sira>_<kolon> = ogrenci_pk
        # Önce bu sınıfın tüm kaydını sil, sonra yenisini yaz
        SinifOturmaDuzeni.objects.filter(sinif_sube=sinif_sube).delete()
        yeni_kayitlar = []
        for sira in range(1, N_SIRA + 1):
            for kolon in range(1, N_KOLON + 1):
                deger = request.POST.get(f"koltuk_{sira}_{kolon}", "").strip()
                if deger:
                    try:
                        ogr_pk = int(deger)
                        yeni_kayitlar.append(
                            SinifOturmaDuzeni(
                                sinif_sube=sinif_sube,
                                ogrenci_id=ogr_pk,
                                sira_no=sira,
                                kolon_no=kolon,
                                guncelleyen=user,
                            )
                        )
                    except (ValueError, TypeError):
                        pass
        SinifOturmaDuzeni.objects.bulk_create(yeni_kayitlar)
        messages.success(request, f"{sinif_sube} sınıfının oturma düzeni kaydedildi.")
        qs = f"?sinif_sube={sinif_sube.pk}" if user.is_superuser else ""
        return redirect(f"{request.path}{qs}")

    # Mevcut oturma düzenini grid'e yerleştir
    mevcut = {
        (d.sira_no, d.kolon_no): d.ogrenci
        for d in SinifOturmaDuzeni.objects.filter(sinif_sube=sinif_sube)
        .select_related("ogrenci")
    }

    # Grid: grid[sira][grup][kolon] = {"ogr": ogrenci|None, "sira": int, "kolon": int}
    # kolon_no (DB) = (grup-1)*N_KOLON_PER_GRUP + kolon  (1-tabanlı)
    grid = []
    for sira in range(1, N_SIRA + 1):
        satir_gruplar = []
        for grup in range(1, N_GRUP + 1):
            hucreler = []
            for k in range(1, N_KOLON_PER_GRUP + 1):
                kolon_no = (grup - 1) * N_KOLON_PER_GRUP + k
                hucreler.append({
                    "ogr":    mevcut.get((sira, kolon_no)),
                    "sira":   sira,
                    "kolon":  kolon_no,
                })
            satir_gruplar.append(hucreler)
        grid.append(satir_gruplar)

    # Yerleştirilmemiş öğrenciler
    yerlesmis_pkler = {ogr.pk for ogr in mevcut.values()}
    yerlestirilmemis = [o for o in ogrenciler if o.pk not in yerlesmis_pkler]

    return render(request, "main/sinif_oturma_plani.html", {
        "title":              f"Sınıf Oturma Planı – {sinif_sube}",
        "sinif_sube":         sinif_sube,
        "grid":               grid,           # grid[sira_idx][kolon_idx 0..5]
        "n_grup":             N_GRUP,
        "n_kolon_per_grup":   N_KOLON_PER_GRUP,
        "n_kolon":            N_KOLON,
        "n_sira":             N_SIRA,
        "sira_range":         range(1, N_SIRA + 1),
        "grup_range":         range(1, N_GRUP + 1),
        "kolon_per_grup_range": range(1, N_KOLON_PER_GRUP + 1),
        "ogrenciler":         ogrenciler,
        "yerlestirilmemis":   yerlestirilmemis,
        "sinif_sec":          False,
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
