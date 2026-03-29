from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ogrenci.models import Ogrenci

from .models import MuduriyetGorusme

# ─────────────────────────────────────────────
# Yardımcılar
# ─────────────────────────────────────────────


def _mudur_mi(user):
    return (
        user.is_superuser
        or user.groups.filter(name__in=["mudur_yardimcisi", "okul_muduru"]).exists()
    )


def _sinifsube_secenekleri():
    return [
        f"{s}/{sb}"
        for s, sb in Ogrenci.objects.values_list("sinif", "sube")
        .distinct()
        .order_by("sinif", "sube")
    ]


# ─────────────────────────────────────────────
# Görüşme Listesi
# ─────────────────────────────────────────────


@login_required
def gorusme_liste(request):
    if not _mudur_mi(request.user):
        messages.error(request, "Bu sayfaya erişim yetkiniz yok.")
        return redirect("index")

    from django.db.models import Q

    qs = MuduriyetGorusme.objects.select_related("ogrenci", "kayit_eden_kullanici")

    tarih_bas = request.GET.get("tarih_bas", "").strip()
    tarih_bit = request.GET.get("tarih_bit", "").strip()
    sinifsube = request.GET.get("sinifsube", "").strip()
    tur = request.GET.get("tur", "").strip()
    ogrenci_q = request.GET.get("ogrenci_q", "").strip()

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

    return render(
        request,
        "muduriyetcagri/gorusme_liste.html",
        {
            "gorusmeler": qs,
            "toplam": qs.count(),
            "sinifsube_secenekleri": _sinifsube_secenekleri(),
            "tur_secenekleri": MuduriyetGorusme.TUR_CHOICES,
            "filters": {
                "tarih_bas": tarih_bas,
                "tarih_bit": tarih_bit,
                "sinifsube": sinifsube,
                "tur": tur,
                "ogrenci_q": ogrenci_q,
            },
            "bugun": timezone.localdate(),
        },
    )


# ─────────────────────────────────────────────
# Görüşme Oluştur
# ─────────────────────────────────────────────


@login_required
def gorusme_olustur(request):
    if not _mudur_mi(request.user):
        messages.error(request, "Bu işlem için yetkiniz yok.")
        return redirect("index")

    # Çağrısız görüşme açılamaz — önce çağrı oluşturulmalı
    cagri_id_kontrol = (
        request.GET.get("cagri_id", "").strip() or request.POST.get("cagri_id", "").strip()
    )
    if not cagri_id_kontrol:
        messages.warning(request, "Görüşme oluşturmak için önce öğrenci çağrısı oluşturun.")
        return redirect("muduriyetcagri:cagri_olustur")

    ogrenciler = Ogrenci.objects.select_related("detay").order_by("sinif", "sube", "okulno")
    sinifsube_secenekleri = _sinifsube_secenekleri()

    if request.method == "POST":
        tarih = request.POST.get("tarih", "").strip()
        tur = request.POST.get("tur", "").strip()
        konu = request.POST.get("konu", "").strip()
        aciklama = request.POST.get("aciklama", "").strip()
        sonuc = request.POST.get("sonuc", "").strip()
        takip_tarihi = request.POST.get("takip_tarihi", "").strip() or None
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
            gorusme = MuduriyetGorusme.objects.create(
                ogrenci=ogrenci,
                veli_adi=veli_adi if tur == "veli" else "",
                veli_telefon=veli_telefon if tur == "veli" else "",
                tarih=tarih,
                tur=tur,
                konu=konu,
                aciklama=aciklama,
                sonuc=sonuc,
                takip_tarihi=takip_tarihi,
                kayit_eden_kullanici=request.user,
            )
            if tur == "grup" and grup_ids:
                gorusme.grup_ogrencileri.set(grup_ids)

            # Çağrıdan gelindiyse çağrıyı görüşmeye bağla ve devamsızlık kaydı oluştur
            cagri_id_post = request.POST.get("cagri_id", "").strip()
            if cagri_id_post:
                from cagri.models import OgrenciCagri
                from devamsizlik.models import OgrenciDevamsizlik

                try:
                    cagri_obj = OgrenciCagri.objects.get(
                        pk=int(cagri_id_post),
                        kayit_eden_kullanici=request.user,
                        servis=OgrenciCagri.SERVIS_MUDURIYETCAGRI,
                    )
                    cagri_obj.gorusme_muduriyetcagri = gorusme  # type: ignore[assignment]
                    cagri_obj.save(update_fields=["gorusme_muduriyetcagri"])
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
                                "ders_adi": cagri_obj.ders_adi or "Müdüriyet",
                                "ogretmen_adi": request.user.get_full_name()
                                or request.user.username,
                                "aciklama": "Müdüriyet",
                            },
                        )
                except (OgrenciCagri.DoesNotExist, ValueError):
                    pass

            messages.success(request, "Görüşme kaydı oluşturuldu.")
            return redirect("muduriyetcagri:gorusme_detay", pk=gorusme.pk)

    # GET — ön-seçimler
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

    return render(
        request,
        "muduriyetcagri/gorusme_form.html",
        {
            "gorusme": None,
            "ogrenciler": ogrenciler,
            "sinifsube_secenekleri": sinifsube_secenekleri,
            "tur_secenekleri": MuduriyetGorusme.TUR_CHOICES,
            "bugun": timezone.localdate().isoformat(),
            "secili_tur": secili_tur,
            "secili_ogrenci_id": secili_ogrenci_id,
            "cagri_id": cagri_id,
            "secili_grup_ids": [],
        },
    )


# ─────────────────────────────────────────────
# Görüşme Detay
# ─────────────────────────────────────────────


@login_required
def gorusme_detay(request, pk):
    gorusme = get_object_or_404(MuduriyetGorusme, pk=pk)

    if not _mudur_mi(request.user):
        messages.error(request, "Bu sayfaya erişim yetkiniz yok.")
        return redirect("muduriyetcagri:gorusme_liste")

    sahip = (gorusme.kayit_eden_kullanici == request.user) or request.user.is_superuser

    return render(
        request,
        "muduriyetcagri/gorusme_detay.html",
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
    gorusme = get_object_or_404(MuduriyetGorusme, pk=pk)

    if not _mudur_mi(request.user):
        messages.error(request, "Bu işlem için yetkiniz yok.")
        return redirect("muduriyetcagri:gorusme_liste")

    if gorusme.kayit_eden_kullanici != request.user and not request.user.is_superuser:
        messages.error(request, "Yalnızca kendi görüşmelerinizi düzenleyebilirsiniz.")
        return redirect("muduriyetcagri:gorusme_detay", pk=pk)

    ogrenciler = Ogrenci.objects.select_related("detay").order_by("sinif", "sube", "okulno")
    sinifsube_secenekleri = _sinifsube_secenekleri()

    if request.method == "POST":
        tarih = request.POST.get("tarih", "").strip()
        tur = request.POST.get("tur", "").strip()
        konu = request.POST.get("konu", "").strip()
        aciklama = request.POST.get("aciklama", "").strip()
        sonuc = request.POST.get("sonuc", "").strip()
        takip_tarihi = request.POST.get("takip_tarihi", "").strip() or None
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
            gorusme.save()
            if tur == "grup":
                gorusme.grup_ogrencileri.set(grup_ids)
            else:
                gorusme.grup_ogrencileri.clear()
            messages.success(request, "Görüşme kaydı güncellendi.")
            return redirect("muduriyetcagri:gorusme_detay", pk=gorusme.pk)

    secili_grup_ids = list(gorusme.grup_ogrencileri.values_list("pk", flat=True))
    return render(
        request,
        "muduriyetcagri/gorusme_form.html",
        {
            "gorusme": gorusme,
            "ogrenciler": ogrenciler,
            "sinifsube_secenekleri": sinifsube_secenekleri,
            "tur_secenekleri": MuduriyetGorusme.TUR_CHOICES,
            "bugun": timezone.localdate().isoformat(),
            "secili_ogrenci_id": gorusme.ogrenci.pk if gorusme.ogrenci else None,
            "secili_grup_ids": secili_grup_ids,
        },
    )


# ─────────────────────────────────────────────
# Görüşme Sil
# ─────────────────────────────────────────────


@login_required
def gorusme_sil(request, pk):
    gorusme = get_object_or_404(MuduriyetGorusme, pk=pk)

    if not _mudur_mi(request.user):
        messages.error(request, "Bu işlem için yetkiniz yok.")
        return redirect("muduriyetcagri:gorusme_liste")

    if gorusme.kayit_eden_kullanici != request.user and not request.user.is_superuser:
        messages.error(request, "Yalnızca kendi görüşmelerinizi silebilirsiniz.")
        return redirect("muduriyetcagri:gorusme_detay", pk=pk)

    if request.method == "POST":
        gorusme.delete()
        messages.success(request, "Görüşme kaydı silindi.")
        return redirect("muduriyetcagri:gorusme_liste")

    return render(request, "muduriyetcagri/gorusme_sil.html", {"gorusme": gorusme})
