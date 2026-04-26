from collections import OrderedDict
from datetime import date as date_type

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from dersprogrami.models import DersProgrami
from okul.models import SinifSube
from okul.utils import get_aktif_dp_tarihi
from ogrenci.models import Ogrenci

from .models import OgrenciCagri

# ─────────────────────────────────────────────
# Servis konfigürasyonları
# ─────────────────────────────────────────────

SERVIS_CONFIGS = {
    OgrenciCagri.SERVIS_REHBERLIK: {
        "display_name": "Rehberlik Çağrı Listesi",
        "form_baslik": "Rehberlik Çağrısı Oluştur",
        "yazdir_baslik": "REHBERLİK SERVİSİ",
        "kenarlık": "#20c997",
        "liste_url": "rehberlik:cagri_liste",
        "olustur_url": "rehberlik:cagri_olustur",
        "gorusme_liste_url": "rehberlik:gorusme_liste",
        "gorusme_olustur_url": "rehberlik:gorusme_olustur",
        "gorusme_detay_url": "rehberlik:gorusme_detay",
    },
    OgrenciCagri.SERVIS_DISIPLIN: {
        "display_name": "Disiplin Çağrı Listesi",
        "form_baslik": "Disiplin Çağrısı Oluştur",
        "yazdir_baslik": "DİSİPLİN KURULU",
        "kenarlık": "#dc3545",
        "liste_url": "disiplin:cagri_liste",
        "olustur_url": "disiplin:cagri_olustur",
        "gorusme_liste_url": "disiplin:gorusme_liste",
        "gorusme_olustur_url": "disiplin:gorusme_olustur",
        "gorusme_detay_url": "disiplin:gorusme_detay",
    },
    OgrenciCagri.SERVIS_MUDURIYETCAGRI: {
        "display_name": "Müdüriyet Çağrı Listesi",
        "form_baslik": "Müdüriyet Çağrısı Oluştur",
        "yazdir_baslik": "MÜDÜRİYET",
        "kenarlık": "#343a40",
        "liste_url": "muduriyetcagri:cagri_liste",
        "olustur_url": "muduriyetcagri:cagri_olustur",
        "gorusme_liste_url": "muduriyetcagri:gorusme_liste",
        "gorusme_olustur_url": "muduriyetcagri:gorusme_olustur",
        "gorusme_detay_url": "muduriyetcagri:gorusme_detay",
    },
}

# ─────────────────────────────────────────────
# Auth yardımcıları  (servis app'lerine import bağımlılığı yok)
# ─────────────────────────────────────────────


def _rehber_mi(user):
    return user.is_superuser or user.groups.filter(name="rehber_ogretmen").exists()


def _disiplin_mi(user):
    return (
        user.is_superuser
        or user.groups.filter(name__in=["disiplin_kurulu", "mudur_yardimcisi"]).exists()
    )


from okul.auth import is_mudur_yardimcisi as _mudur_yardimcisi_mi


def _mudur_mi(user):
    return (
        user.is_superuser
        or user.groups.filter(name__in=["mudur_yardimcisi", "okul_muduru"]).exists()
    )


def _personel(request):
    try:
        return request.user.personel
    except Exception:
        return None


def _check_liste_auth(user, servis):
    if servis == OgrenciCagri.SERVIS_REHBERLIK:
        return _rehber_mi(user) or _mudur_yardimcisi_mi(user)
    if servis == OgrenciCagri.SERVIS_DISIPLIN:
        return _disiplin_mi(user) or _mudur_yardimcisi_mi(user)
    if servis == OgrenciCagri.SERVIS_MUDURIYETCAGRI:
        return _mudur_mi(user)
    return False


def _check_olustur_auth(user, servis):
    if servis == OgrenciCagri.SERVIS_REHBERLIK:
        return _rehber_mi(user)
    if servis == OgrenciCagri.SERVIS_DISIPLIN:
        return _disiplin_mi(user)
    if servis == OgrenciCagri.SERVIS_MUDURIYETCAGRI:
        return _mudur_mi(user)
    return False


def _filter_qs_by_servis(user, servis, personel, qs):
    """Kullanıcının rolüne göre queryset'i daraltır."""
    if servis == OgrenciCagri.SERVIS_REHBERLIK:
        if _rehber_mi(user) and not _mudur_yardimcisi_mi(user) and personel:
            return qs.filter(kayit_eden=personel)
        return qs
    if servis == OgrenciCagri.SERVIS_DISIPLIN:
        disiplin_sadece = (
            user.is_superuser or user.groups.filter(name="disiplin_kurulu").exists()
        ) and not _mudur_yardimcisi_mi(user)
        if disiplin_sadece and personel:
            return qs.filter(kayit_eden=personel)
        return qs
    return qs  # muduriyetcagri: herkes tümünü görür


def _sinifsube_secenekleri():
    return [
        f"{s}/{sb}"
        for s, sb in Ogrenci.objects.values_list("sinif", "sube")
        .distinct()
        .order_by("sinif", "sube")
    ]


# ─────────────────────────────────────────────
# Çağrı Listesi
# ─────────────────────────────────────────────


@login_required
def cagri_liste(request, servis):
    cfg = SERVIS_CONFIGS[servis]

    if not _check_liste_auth(request.user, servis):
        messages.error(request, "Bu sayfaya erişim yetkiniz yok.")
        return redirect("index")

    from django.db.models import Q

    personel = _personel(request)

    qs = OgrenciCagri.objects.filter(servis=servis).select_related(
        "ogrenci",
        "kayit_eden",
        "kayit_eden_kullanici",
        "gorusme_rehberlik",
        "gorusme_disiplin",
        "gorusme_muduriyetcagri",
    )
    qs = _filter_qs_by_servis(request.user, servis, personel, qs)

    tarih_bas = request.GET.get("tarih_bas", "").strip()
    tarih_bit = request.GET.get("tarih_bit", "").strip()
    ogrenci_q = request.GET.get("ogrenci_q", "").strip()
    sinifsube = request.GET.get("sinifsube", "").strip()

    if tarih_bas:
        qs = qs.filter(tarih__gte=tarih_bas)
    if tarih_bit:
        qs = qs.filter(tarih__lte=tarih_bit)
    if sinifsube:
        parts = sinifsube.split("/")
        if len(parts) == 2:
            qs = qs.filter(ogrenci__sinif=parts[0], ogrenci__sube__iexact=parts[1])
    if ogrenci_q:
        qs = qs.filter(
            Q(ogrenci__adi__icontains=ogrenci_q)
            | Q(ogrenci__soyadi__icontains=ogrenci_q)
            | Q(ogrenci__okulno__icontains=ogrenci_q)
        )

    # Listenin her satırında "Sil" butonu gösterilecek mi?
    kullanici_olusturabilir = _check_olustur_auth(request.user, servis)

    return render(
        request,
        "cagri/cagri_liste.html",
        {
            "cagrilar": qs,
            "toplam": qs.count(),
            "servis": servis,
            "servis_config": cfg,
            "sinifsube_secenekleri": _sinifsube_secenekleri(),
            "kullanici_olusturabilir": kullanici_olusturabilir,
            "filters": {
                "tarih_bas": tarih_bas,
                "tarih_bit": tarih_bit,
                "ogrenci_q": ogrenci_q,
                "sinifsube": sinifsube,
            },
            "bugun": timezone.localdate(),
        },
    )


# ─────────────────────────────────────────────
# Çağrı Oluştur
# ─────────────────────────────────────────────


@login_required
def cagri_olustur(request, servis):
    cfg = SERVIS_CONFIGS[servis]

    if not _check_olustur_auth(request.user, servis):
        messages.error(request, "Bu sayfaya erişim yetkiniz yok.")
        return redirect("index")

    personel = _personel(request)
    if servis in (OgrenciCagri.SERVIS_REHBERLIK, OgrenciCagri.SERVIS_DISIPLIN) and personel is None:
        messages.error(request, "Bu kullanıcıya bağlı personel kaydı bulunamadı.")
        return redirect("index")

    # ── Grup modu (rehberlik ve disiplin için) ──
    grup_modu = False
    grup_ogrenciler = None
    sinif_gruplari = []
    tek_sinif = True
    gorusme_id = None
    gorusme_id_str = request.GET.get("gorusme_id", "") or request.POST.get("gorusme_id", "")

    if servis != OgrenciCagri.SERVIS_MUDURIYETCAGRI and gorusme_id_str:
        try:
            gorusme_id = int(gorusme_id_str)
            if servis == OgrenciCagri.SERVIS_REHBERLIK:
                from rehberlik.models import Gorusme as RGorusme

                gorusme_obj = RGorusme.objects.get(pk=gorusme_id)
            else:
                from disiplin.models import DisiplinGorusme

                gorusme_obj = DisiplinGorusme.objects.get(pk=gorusme_id)
            if gorusme_obj.tur == "grup":
                grup_modu = True
                grup_ogrenciler = gorusme_obj.grup_ogrencileri.select_related("detay").order_by(
                    "sinif", "sube", "okulno"
                )
        except Exception:
            gorusme_id = None

    # Sınıf gruplarını hesapla
    if grup_modu and grup_ogrenciler is not None:
        grp_dict = OrderedDict()
        for ogr in grup_ogrenciler:
            key = f"{ogr.sinif}_{ogr.sube}"
            if key not in grp_dict:
                grp_dict[key] = {
                    "sinif": str(ogr.sinif),
                    "sube": ogr.sube,
                    "key": key,
                    "label": f"{ogr.sinif}/{ogr.sube}",
                    "ogrenciler": [],
                }
            grp_dict[key]["ogrenciler"].append(ogr)
        sinif_gruplari = list(grp_dict.values())
        tek_sinif = len(sinif_gruplari) == 1

    ogrenciler = Ogrenci.objects.select_related("detay").order_by("sinif", "sube", "okulno")
    sinifsube_secenekleri = _sinifsube_secenekleri()

    secili_ogrenci_id = ""
    if not grup_modu:
        try:
            secili_ogrenci_id = str(int(request.GET.get("ogrenci_id", "")))
        except (ValueError, TypeError):
            pass

    if request.method == "POST":
        tarih = request.POST.get("tarih", "").strip()
        cagri_metni = request.POST.get("cagri_metni", "").strip()
        hatalar = []
        if not tarih:
            hatalar.append("Tarih zorunludur.")

        if grup_modu:
            secili_ids = request.POST.getlist("ogrenci_ids")
            if not secili_ids:
                hatalar.append("En az bir öğrenci seçmelisiniz.")
            if not hatalar:
                olusturulan = 0
                for ogr_id in secili_ids:
                    try:
                        ogr = Ogrenci.objects.get(pk=int(ogr_id))
                        sinif_key = f"{ogr.sinif}_{ogr.sube}"
                        ds_str = request.POST.get(f"ders_saati_{sinif_key}", "").strip()
                        da = request.POST.get(f"ders_adi_{sinif_key}", "").strip()
                        oa = request.POST.get(f"ogretmen_adi_{sinif_key}", "").strip()
                        OgrenciCagri.objects.create(
                            servis=servis,
                            kayit_eden=personel,
                            kayit_eden_kullanici=request.user,
                            ogrenci=ogr,
                            tarih=tarih,
                            ders_saati=int(ds_str) if ds_str else None,
                            ders_adi=da,
                            ogretmen_adi=oa,
                            cagri_metni=cagri_metni,
                        )
                        olusturulan += 1
                    except (Ogrenci.DoesNotExist, ValueError):
                        pass
                messages.success(request, f"{olusturulan} öğrenci için çağrı oluşturuldu.")
                return redirect(cfg["liste_url"])
        else:
            ogrenci_id = request.POST.get("ogrenci_id", "").strip()
            ders_saati = request.POST.get("ders_saati", "").strip()
            ders_adi = request.POST.get("ders_adi", "").strip()
            ogretmen_adi = request.POST.get("ogretmen_adi", "").strip()
            if not ogrenci_id:
                hatalar.append("Öğrenci seçimi zorunludur.")
            ogrenci = None
            if ogrenci_id:
                try:
                    ogrenci = Ogrenci.objects.get(pk=int(ogrenci_id))
                except (Ogrenci.DoesNotExist, ValueError):
                    hatalar.append("Geçersiz öğrenci seçimi.")
            if not hatalar:
                OgrenciCagri.objects.create(
                    servis=servis,
                    kayit_eden=personel,
                    kayit_eden_kullanici=request.user,
                    ogrenci=ogrenci,
                    tarih=tarih,
                    ders_saati=int(ders_saati) if ders_saati else None,
                    ders_adi=ders_adi,
                    ogretmen_adi=ogretmen_adi,
                    cagri_metni=cagri_metni,
                )
                messages.success(request, "Öğrenci çağrısı oluşturuldu.")
                return redirect(cfg["liste_url"])

        for h in hatalar:
            messages.error(request, h)

    cagri_yapan_adi = ""
    cagri_yapan_unvan = ""
    if servis == OgrenciCagri.SERVIS_MUDURIYETCAGRI:
        try:
            yonetici = request.user.okul_yonetici
            cagri_yapan_adi = yonetici.adi_soyadi
            cagri_yapan_unvan = yonetici.get_unvan_display()
        except Exception:
            cagri_yapan_adi = request.user.get_full_name() or request.user.username
            cagri_yapan_unvan = "Müdür Yardımcısı"

    return render(
        request,
        "cagri/cagri_form.html",
        {
            "servis": servis,
            "servis_config": cfg,
            "ogrenciler": ogrenciler,
            "sinifsube_secenekleri": sinifsube_secenekleri,
            "bugun": timezone.localdate().isoformat(),
            "secili_ogrenci_id": secili_ogrenci_id,
            "grup_modu": grup_modu,
            "grup_ogrenciler": grup_ogrenciler,
            "sinif_gruplari": sinif_gruplari,
            "tek_sinif": tek_sinif,
            "gorusme_id": gorusme_id_str,
            "cagri_yapan_adi": cagri_yapan_adi,
            "cagri_yapan_unvan": cagri_yapan_unvan,
        },
    )


# ─────────────────────────────────────────────
# Çağrı Sil
# ─────────────────────────────────────────────


@login_required
def cagri_sil(request, pk):
    cagri = get_object_or_404(OgrenciCagri, pk=pk)
    cfg = SERVIS_CONFIGS[cagri.servis]
    personel = _personel(request)
    user = request.user

    if not _check_liste_auth(user, cagri.servis):
        messages.error(request, "Bu işlem için yetkiniz yok.")
        return redirect("index")

    sahip = user.is_superuser
    if not sahip and cagri.kayit_eden and personel and cagri.kayit_eden == personel:
        sahip = True
    if not sahip and cagri.kayit_eden_kullanici == user:
        sahip = True

    if not sahip:
        messages.error(request, "Yalnızca kendi oluşturduğunuz çağrıları silebilirsiniz.")
        return redirect(cfg["liste_url"])

    if request.method == "POST":
        cagri.delete()
        messages.success(request, "Çağrı kaydı silindi.")
        return redirect(cfg["liste_url"])

    return render(request, "cagri/cagri_sil.html", {"cagri": cagri, "servis_config": cfg})


# ─────────────────────────────────────────────
# Çağrı Yazdır
# ─────────────────────────────────────────────


@login_required
def cagri_yazdir(request, pk):
    cagri = get_object_or_404(OgrenciCagri, pk=pk)
    cfg = SERVIS_CONFIGS[cagri.servis]

    if not _check_liste_auth(request.user, cagri.servis):
        messages.error(request, "Bu sayfaya erişim yetkiniz yok.")
        return redirect("index")

    return render(request, "cagri/cagri_yazdir.html", {"cagri": cagri, "servis_config": cfg})


# ─────────────────────────────────────────────
# Ders Programı API  (tek merkezi endpoint)
# ─────────────────────────────────────────────

_WEEKDAY = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@login_required
def ders_programi_api(request):
    if not (_rehber_mi(request.user) or _disiplin_mi(request.user) or _mudur_mi(request.user)):
        return JsonResponse({"error": "Yetkisiz"}, status=403)

    sinif = request.GET.get("sinif", "").strip()
    sube = request.GET.get("sube", "").strip()
    tarih = request.GET.get("tarih", "").strip()

    if not sinif or not sube or not tarih:
        return JsonResponse([], safe=False)
    try:
        tarih_obj = date_type.fromisoformat(tarih)
    except ValueError:
        return JsonResponse([], safe=False)

    gun = _WEEKDAY[tarih_obj.weekday()]
    try:
        ss = SinifSube.objects.get(sinif=int(sinif), sube__iexact=sube)
    except (SinifSube.DoesNotExist, ValueError):
        return JsonResponse([], safe=False)

    aktif_tarih = get_aktif_dp_tarihi()
    dp_filter = {"sinif_sube": ss, "gun": gun}
    if aktif_tarih:
        dp_filter["uygulama_tarihi"] = aktif_tarih
    dersler = (
        DersProgrami.objects.filter(**dp_filter)
        .select_related("ogretmen", "ders", "ders_saati")
        .order_by("ders_saati__derssaati_no")
    )
    return JsonResponse(
        [
            {
                "ders_saati": d.ders_saati.derssaati_no if d.ders_saati else None,
                "ders_saati_adi": d.ders_saati_adi,
                "ders_adi": d.ders_adi,
                "ogretmen_adi": d.ogretmen.adi_soyadi,
            }
            for d in dersler
        ],
        safe=False,
    )
