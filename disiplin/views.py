from datetime import date as date_type

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cagri.models import OgrenciCagri
from dersprogrami.models import DersProgrami
from okul.models import SinifSube
from okul.utils import get_aktif_dp_tarihi
from ogrenci.models import Ogrenci

from .models import DisiplinGorusme

DisiplinCagri = OgrenciCagri

# ─────────────────────────────────────────────
# Yardımcılar
# ─────────────────────────────────────────────


def _disiplin_mi(user):
    return (
        user.is_superuser
        or user.groups.filter(name__in=["disiplin_kurulu", "mudur_yardimcisi"]).exists()
    )


from okul.auth import is_mudur_yardimcisi as _mudur_yardimcisi_mi


def _personel(request):
    try:
        return request.user.personel
    except Exception:
        return None


def _sinifsube_secenekleri():
    rows = Ogrenci.objects.values_list("sinif", "sube").distinct().order_by("sinif", "sube")
    return [f"{s}/{sb}" for s, sb in rows]


# ─────────────────────────────────────────────
# Görüşme Listesi
# ─────────────────────────────────────────────


@login_required
def gorusme_liste(request):
    kullanici_disiplin = _disiplin_mi(request.user)
    kullanici_mudur = _mudur_yardimcisi_mi(request.user)

    if not kullanici_disiplin and not kullanici_mudur:
        messages.error(request, "Bu sayfaya erişim yetkiniz yok.")
        return redirect("index")

    personel = _personel(request)

    from django.db.models import Q

    # disiplin_kurulu üyeleri kendi kayıtlarını görür (gizliler dahil)
    # mudur_yardimcisi gizli olmayanları + kendi personel kaydıyla oluşturduklarını görür
    disiplin_sadece = kullanici_disiplin and not kullanici_mudur

    if disiplin_sadece and personel:
        qs = DisiplinGorusme.objects.filter(kayit_eden=personel).select_related(
            "ogrenci", "kayit_eden"
        ).prefetch_related("grup_ogrencileri")
    elif kullanici_mudur:
        if personel:
            qs = DisiplinGorusme.objects.filter(
                Q(gizli=False) | Q(kayit_eden=personel)
            ).select_related("ogrenci", "kayit_eden").prefetch_related("grup_ogrencileri")
        else:
            qs = DisiplinGorusme.objects.filter(gizli=False).select_related("ogrenci", "kayit_eden").prefetch_related("grup_ogrencileri")
    elif kullanici_disiplin and personel:
        qs = DisiplinGorusme.objects.filter(kayit_eden=personel).select_related(
            "ogrenci", "kayit_eden"
        ).prefetch_related("grup_ogrencileri")
    else:
        qs = DisiplinGorusme.objects.none()

    # GET filtreleri
    tarih_bas = request.GET.get("tarih_bas", "").strip()
    tarih_bit = request.GET.get("tarih_bit", "").strip()
    sinifsube = request.GET.get("sinifsube", "").strip()
    tur = request.GET.get("tur", "").strip()
    ogrenci_q = request.GET.get("ogrenci_q", "").strip()
    gizli_filtr = request.GET.get("gizli", "").strip()

    if tarih_bas:
        qs = qs.filter(tarih__gte=tarih_bas)
    if tarih_bit:
        qs = qs.filter(tarih__lte=tarih_bit)
    if sinifsube:
        parts = sinifsube.split("/")
        if len(parts) == 2:
            qs = qs.filter(ogrenci__sinif=parts[0], ogrenci__sube__iexact=parts[1])
    if tur:
        qs = qs.filter(tur=tur)
    if ogrenci_q:
        qs = qs.filter(
            Q(ogrenci__adi__icontains=ogrenci_q)
            | Q(ogrenci__soyadi__icontains=ogrenci_q)
            | Q(ogrenci__okulno__icontains=ogrenci_q)
        )
    if kullanici_disiplin and gizli_filtr in ("0", "1"):
        qs = qs.filter(gizli=(gizli_filtr == "1"))

    qs = qs.order_by("-tarih", "-olusturma_zamani")

    context = {
        "gorusmeler": qs,
        "toplam": qs.count(),
        "sinifsube_secenekleri": _sinifsube_secenekleri(),
        "tur_secenekleri": DisiplinGorusme.TUR_CHOICES,
        "filters": {
            "tarih_bas": tarih_bas,
            "tarih_bit": tarih_bit,
            "sinifsube": sinifsube,
            "tur": tur,
            "ogrenci_q": ogrenci_q,
            "gizli": gizli_filtr,
        },
        "kullanici_disiplin": kullanici_disiplin,
        "kullanici_mudur": kullanici_mudur,
        "personel": personel,
        "bugun": timezone.localdate(),
    }
    return render(request, "disiplin/gorusme_liste.html", context)


# ─────────────────────────────────────────────
# Görüşme Oluştur
# ─────────────────────────────────────────────


@login_required
def gorusme_olustur(request):
    if not _disiplin_mi(request.user):
        messages.error(request, "Bu sayfaya yalnızca disiplin kurulu üyeleri erişebilir.")
        return redirect("index")

    personel = _personel(request)
    if personel is None:
        messages.error(request, "Bu kullanıcıya bağlı personel kaydı bulunamadı.")
        return redirect("index")

    # Çağrısız görüşme açılamaz — önce çağrı oluşturulmalı
    cagri_id_kontrol = (
        request.GET.get("cagri_id", "").strip() or request.POST.get("cagri_id", "").strip()
    )
    if not cagri_id_kontrol:
        messages.warning(request, "Görüşme oluşturmak için önce öğrenci çağrısı oluşturun.")
        return redirect("disiplin:cagri_olustur")

    ogrenciler = Ogrenci.objects.select_related("detay").order_by("sinif", "sube", "okulno")
    sinifsube_secenekleri = _sinifsube_secenekleri()

    if request.method == "POST":
        tarih = request.POST.get("tarih", "").strip()
        tur = request.POST.get("tur", "").strip()
        konu = request.POST.get("konu", "").strip()
        aciklama = request.POST.get("aciklama", "").strip()
        sonuc = request.POST.get("sonuc", "").strip()
        takip_tarihi = request.POST.get("takip_tarihi", "").strip() or None
        gizli = request.POST.get("gizli") == "on"
        veli_adi = request.POST.get("veli", "").strip()
        veli_telefon = request.POST.get("velitelefon", "").strip()

        hatalar = []
        if not tarih:
            hatalar.append("Tarih zorunludur.")
        if not tur:
            hatalar.append("Görüşme türü zorunludur.")
        if not konu:
            hatalar.append("Konu zorunludur.")

        ogrenci = None
        grup_ids = []

        if tur in ("bireysel", "veli"):
            ogrenci_id = request.POST.get("ogrenci_id", "").strip()
            if ogrenci_id:
                try:
                    ogrenci = Ogrenci.objects.get(pk=int(ogrenci_id))
                except (Ogrenci.DoesNotExist, ValueError):
                    hatalar.append("Geçersiz öğrenci seçimi.")
        elif tur == "grup":
            grup_ids = request.POST.getlist("grup_ogrenci_ids")

        if hatalar:
            for h in hatalar:
                messages.error(request, h)
        else:
            gorusme = DisiplinGorusme.objects.create(
                ogrenci=ogrenci,
                veli_adi=veli_adi if tur == "veli" else "",
                veli_telefon=veli_telefon if tur == "veli" else "",
                tarih=tarih,
                tur=tur,
                konu=konu,
                aciklama=aciklama,
                sonuc=sonuc,
                takip_tarihi=takip_tarihi,
                gizli=gizli,
                kayit_eden=personel,
            )
            if tur == "grup" and grup_ids:
                gorusme.grup_ogrencileri.set(grup_ids)
            # Çağrıdan gelindiyse çağrıyı görüşmeye bağla ve devamsızlık kaydı oluştur
            cagri_id_post = request.POST.get("cagri_id", "").strip()
            if cagri_id_post:
                from devamsizlik.models import OgrenciDevamsizlik

                try:
                    cagri_obj = OgrenciCagri.objects.get(
                        pk=int(cagri_id_post),
                        kayit_eden=personel,
                        servis=OgrenciCagri.SERVIS_DISIPLIN,
                    )
                    cagri_obj.gorusme_disiplin = gorusme  # type: ignore[assignment]
                    cagri_obj.save(update_fields=["gorusme_disiplin"])
                    if cagri_obj.ogrenci and cagri_obj.ders_saati:
                        from okul.models import DersSaatleri as _DersSaatleri
                        _ds_obj = _DersSaatleri.objects.filter(
                            derssaati_no=cagri_obj.ders_saati
                        ).first()
                        OgrenciDevamsizlik.objects.update_or_create(
                            ogrenci=cagri_obj.ogrenci,
                            tarih=cagri_obj.tarih,
                            ders_saati=_ds_obj,
                            defaults={
                                "ders_adi": cagri_obj.ders_adi or "Disiplin",
                                "ogretmen_adi": personel.adi_soyadi,
                                "aciklama": "Disiplin Kurulu",
                            },
                        )
                except (OgrenciCagri.DoesNotExist, ValueError):
                    pass
            messages.success(request, "Görüşme kaydı oluşturuldu.")
            return redirect("disiplin:gorusme_detay", pk=gorusme.pk)

    # Çağrı listesinden gelen ön-seçimler
    secili_tur = request.GET.get("tur", "").strip()
    secili_ogrenci_id = ""
    try:
        secili_ogrenci_id = str(int(request.GET.get("ogrenci_id", "")))
    except (ValueError, TypeError):
        pass
    cagri_id = ""
    try:
        cagri_id = str(int(request.GET.get("cagri_id", "")))
    except (ValueError, TypeError):
        pass

    context = {
        "gorusme": None,
        "ogrenciler": ogrenciler,
        "sinifsube_secenekleri": sinifsube_secenekleri,
        "tur_secenekleri": DisiplinGorusme.TUR_CHOICES,
        "bugun": timezone.localdate().isoformat(),
        "secili_tur": secili_tur,
        "secili_ogrenci_id": secili_ogrenci_id,
        "cagri_id": cagri_id,
        "secili_grup_ids": [],
    }
    return render(request, "disiplin/gorusme_form.html", context)


# ─────────────────────────────────────────────
# Görüşme Detay
# ─────────────────────────────────────────────


@login_required
def gorusme_detay(request, pk):
    gorusme = get_object_or_404(DisiplinGorusme, pk=pk)
    personel = _personel(request)
    disiplin = _disiplin_mi(request.user)
    mudur = _mudur_yardimcisi_mi(request.user)

    # Erişim kontrolü
    sahip = personel is not None and gorusme.kayit_eden == personel

    if not sahip and not mudur and not disiplin:
        messages.error(request, "Bu görüşmeyi görme yetkiniz yok.")
        return redirect("disiplin:gorusme_liste")

    # Gizli kayıtlara yalnızca sahibi erişebilir
    if gorusme.gizli and not sahip:
        messages.error(request, "Bu gizli görüşme kaydına erişim yetkiniz yok.")
        return redirect("disiplin:gorusme_liste")

    return render(
        request,
        "disiplin/gorusme_detay.html",
        {
            "gorusme": gorusme,
            "sahip": sahip,
        },
    )


# ─────────────────────────────────────────────
# Görüşme Düzenle
# ─────────────────────────────────────────────


@login_required
def gorusme_duzenle(request, pk):
    gorusme = get_object_or_404(DisiplinGorusme, pk=pk)
    personel = _personel(request)

    if not _disiplin_mi(request.user):
        messages.error(request, "Bu işlem için yetkiniz yok.")
        return redirect("disiplin:gorusme_liste")

    if personel is None or gorusme.kayit_eden != personel:
        messages.error(request, "Yalnızca kendi görüşmelerinizi düzenleyebilirsiniz.")
        return redirect("disiplin:gorusme_detay", pk=pk)

    ogrenciler = Ogrenci.objects.select_related("detay").order_by("sinif", "sube", "okulno")
    sinifsube_secenekleri = _sinifsube_secenekleri()

    if request.method == "POST":
        tarih = request.POST.get("tarih", "").strip()
        tur = request.POST.get("tur", "").strip()
        konu = request.POST.get("konu", "").strip()
        aciklama = request.POST.get("aciklama", "").strip()
        sonuc = request.POST.get("sonuc", "").strip()
        takip_tarihi = request.POST.get("takip_tarihi", "").strip() or None
        gizli = request.POST.get("gizli") == "on"
        veli_adi = request.POST.get("veli", "").strip()
        veli_telefon = request.POST.get("velitelefon", "").strip()

        hatalar = []
        if not tarih:
            hatalar.append("Tarih zorunludur.")
        if not tur:
            hatalar.append("Görüşme türü zorunludur.")
        if not konu:
            hatalar.append("Konu zorunludur.")

        ogrenci = None
        grup_ids = []

        if tur in ("bireysel", "veli"):
            ogrenci_id = request.POST.get("ogrenci_id", "").strip()
            if ogrenci_id:
                try:
                    ogrenci = Ogrenci.objects.get(pk=int(ogrenci_id))
                except (Ogrenci.DoesNotExist, ValueError):
                    hatalar.append("Geçersiz öğrenci seçimi.")
        elif tur == "grup":
            grup_ids = request.POST.getlist("grup_ogrenci_ids")

        if hatalar:
            for h in hatalar:
                messages.error(request, h)
        else:
            gorusme.ogrenci = ogrenci  # type: ignore[assignment]
            gorusme.veli_adi = veli_adi if tur == "veli" else ""
            gorusme.veli_telefon = veli_telefon if tur == "veli" else ""
            gorusme.tarih = tarih
            gorusme.tur = tur
            gorusme.konu = konu
            gorusme.aciklama = aciklama
            gorusme.sonuc = sonuc
            gorusme.takip_tarihi = takip_tarihi
            gorusme.gizli = gizli
            gorusme.save()
            if tur == "grup":
                gorusme.grup_ogrencileri.set(grup_ids)
            else:
                gorusme.grup_ogrencileri.clear()
            messages.success(request, "Görüşme kaydı güncellendi.")
            return redirect("disiplin:gorusme_detay", pk=gorusme.pk)

    secili_grup_ids = list(gorusme.grup_ogrencileri.values_list("pk", flat=True))
    context = {
        "gorusme": gorusme,
        "ogrenciler": ogrenciler,
        "sinifsube_secenekleri": sinifsube_secenekleri,
        "tur_secenekleri": DisiplinGorusme.TUR_CHOICES,
        "bugun": timezone.localdate().isoformat(),
        "secili_ogrenci_id": gorusme.ogrenci.pk if gorusme.ogrenci else None,
        "secili_grup_ids": secili_grup_ids,
    }
    return render(request, "disiplin/gorusme_form.html", context)


# ─────────────────────────────────────────────
# Görüşme Sil
# ─────────────────────────────────────────────


@login_required
def gorusme_sil(request, pk):
    gorusme = get_object_or_404(DisiplinGorusme, pk=pk)
    personel = _personel(request)

    if not _disiplin_mi(request.user):
        messages.error(request, "Bu işlem için yetkiniz yok.")
        return redirect("disiplin:gorusme_liste")

    if personel is None or gorusme.kayit_eden != personel:
        messages.error(request, "Yalnızca kendi görüşmelerinizi silebilirsiniz.")
        return redirect("disiplin:gorusme_detay", pk=pk)

    if request.method == "POST":
        gorusme.delete()
        messages.success(request, "Görüşme kaydı silindi.")
        return redirect("disiplin:gorusme_liste")

    return render(request, "disiplin/gorusme_sil.html", {"gorusme": gorusme})


# ─────────────────────────────────────────────
# Ders Programı API (AJAX)
# ─────────────────────────────────────────────

WEEKDAY_TR = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@login_required
def ders_programi_api(request):
    """AJAX: sınıf/şube + tarih → o gündeki ders saatlerini JSON döner."""
    if not (_disiplin_mi(request.user) or _mudur_yardimcisi_mi(request.user)):
        from django.http import JsonResponse

        return JsonResponse({"error": "Yetkisiz"}, status=403)

    from django.http import JsonResponse

    sinif = request.GET.get("sinif", "").strip()
    sube = request.GET.get("sube", "").strip()
    tarih = request.GET.get("tarih", "").strip()

    if not sinif or not sube or not tarih:
        return JsonResponse([], safe=False)

    try:
        tarih_obj = date_type.fromisoformat(tarih)
    except ValueError:
        return JsonResponse([], safe=False)

    gun = WEEKDAY_TR[tarih_obj.weekday()]

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
        .select_related("ogretmen", "ders_saati")
        .order_by("ders_saati__derssaati_no")
    )

    data = [
        {
            "ders_saati": d.ders_saati.derssaati_no if d.ders_saati else None,
            "ders_saati_adi": d.ders_saati_adi,
            "ders_adi": d.ders_adi,
            "ogretmen_adi": d.ogretmen.adi_soyadi,
        }
        for d in dersler
    ]
    return JsonResponse(data, safe=False)


# ─────────────────────────────────────────────
# Disiplin Çağrısı — Liste
# ─────────────────────────────────────────────


@login_required
def cagri_liste(request):
    kullanici_disiplin = _disiplin_mi(request.user)
    kullanici_mudur = _mudur_yardimcisi_mi(request.user)

    if not kullanici_disiplin and not kullanici_mudur:
        messages.error(request, "Bu sayfaya erişim yetkiniz yok.")
        return redirect("index")

    personel = _personel(request)

    disiplin_sadece = kullanici_disiplin and not kullanici_mudur

    if disiplin_sadece and personel:
        qs = DisiplinCagri.objects.filter(kayit_eden=personel).select_related(
            "ogrenci", "kayit_eden", "gorusme"
        )
    elif kullanici_mudur:
        qs = DisiplinCagri.objects.all().select_related("ogrenci", "kayit_eden", "gorusme")
    elif kullanici_disiplin and personel:
        qs = DisiplinCagri.objects.filter(kayit_eden=personel).select_related(
            "ogrenci", "kayit_eden", "gorusme"
        )
    else:
        qs = DisiplinCagri.objects.none()

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

    qs = qs.order_by("-tarih", "ders_saati")

    context = {
        "cagrilar": qs,
        "toplam": qs.count(),
        "sinifsube_secenekleri": _sinifsube_secenekleri(),
        "kullanici_disiplin": kullanici_disiplin,
        "personel": personel,
        "filters": {
            "tarih_bas": tarih_bas,
            "tarih_bit": tarih_bit,
            "ogrenci_q": ogrenci_q,
            "sinifsube": sinifsube,
        },
        "bugun": timezone.localdate(),
    }
    return render(request, "disiplin/cagri_liste.html", context)


# ─────────────────────────────────────────────
# Disiplin Çağrısı — Oluştur
# ─────────────────────────────────────────────


@login_required
def cagri_olustur(request):
    if not _disiplin_mi(request.user):
        messages.error(request, "Bu sayfaya yalnızca disiplin kurulu üyeleri erişebilir.")
        return redirect("index")

    personel = _personel(request)
    if personel is None:
        messages.error(request, "Bu kullanıcıya bağlı personel kaydı bulunamadı.")
        return redirect("index")

    # ── Grup görüşmesinden mi gelinildi? ──
    grup_modu = False
    grup_ogrenciler = None
    secili_ogrenci_id = ""

    gorusme_id_str = request.GET.get("gorusme_id", "") or request.POST.get("gorusme_id", "")
    try:
        gorusme_id = int(gorusme_id_str)
        gorusme_obj = DisiplinGorusme.objects.get(pk=gorusme_id)
        if gorusme_obj.tur == "grup":
            grup_modu = True
            grup_ogrenciler = gorusme_obj.grup_ogrencileri.select_related("detay").order_by(
                "sinif", "sube", "okulno"
            )
    except (ValueError, TypeError, DisiplinGorusme.DoesNotExist):
        gorusme_id = None

    # Tekli mod için ön-seçim
    if not grup_modu:
        try:
            secili_ogrenci_id = str(int(request.GET.get("ogrenci_id", "")))
        except (ValueError, TypeError):
            pass

    ogrenciler = Ogrenci.objects.select_related("detay").order_by("sinif", "sube", "okulno")
    sinifsube_secenekleri = _sinifsube_secenekleri()

    # ── Sınıf gruplarını hesapla (grup modunda) ──
    from collections import OrderedDict

    sinif_gruplari = []
    tek_sinif = True
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

    if request.method == "POST":
        tarih = request.POST.get("tarih", "").strip()
        cagri_metni = request.POST.get("cagri_metni", "").strip()

        hatalar = []
        if not tarih:
            hatalar.append("Tarih zorunludur.")

        if grup_modu:
            # Çoklu seçim: her seçili öğrenci için sınıfına ait ders_saati kullan
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
                        DisiplinCagri.objects.create(
                            kayit_eden=personel,
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
                return redirect("disiplin:cagri_liste")
        else:
            # Tekli seçim
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
                DisiplinCagri.objects.create(
                    kayit_eden=personel,
                    ogrenci=ogrenci,
                    tarih=tarih,
                    ders_saati=int(ders_saati) if ders_saati else None,
                    ders_adi=ders_adi,
                    ogretmen_adi=ogretmen_adi,
                    cagri_metni=cagri_metni,
                )
                messages.success(request, "Öğrenci çağrısı oluşturuldu.")
                return redirect("disiplin:cagri_liste")

        for h in hatalar:
            messages.error(request, h)

    context = {
        "ogrenciler": ogrenciler,
        "sinifsube_secenekleri": sinifsube_secenekleri,
        "bugun": timezone.localdate().isoformat(),
        "secili_ogrenci_id": secili_ogrenci_id,
        "grup_modu": grup_modu,
        "grup_ogrenciler": grup_ogrenciler,
        "sinif_gruplari": sinif_gruplari,
        "tek_sinif": tek_sinif,
        "gorusme_id": gorusme_id_str,
    }
    return render(request, "disiplin/cagri_form.html", context)


# ─────────────────────────────────────────────
# Disiplin Çağrısı — Yazdır
# ─────────────────────────────────────────────


@login_required
def cagri_yazdir(request, pk):
    cagri = get_object_or_404(DisiplinCagri, pk=pk)
    disiplin = _disiplin_mi(request.user)
    mudur = _mudur_yardimcisi_mi(request.user)
    if not disiplin and not mudur:
        messages.error(request, "Bu sayfaya erişim yetkiniz yok.")
        return redirect("index")
    return render(request, "disiplin/cagri_yazdir.html", {"cagri": cagri})
