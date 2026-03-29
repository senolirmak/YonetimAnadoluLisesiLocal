from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import SinifTahtaForm
from .models import BildirimLog, SinifTahta


def _yonetici_mi(user):
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(
        name__in=["mudur_yardimcisi", "okul_muduru", "rehber_ogretmen", "disiplin_kurulu"]
    ).exists()


def _mudur_yardimcisi_mi(user):
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name__in=["mudur_yardimcisi", "okul_muduru"]).exists()


# ── Tahta Listesi ──────────────────────────────────────────────
@login_required
def tahta_listesi(request):
    if not _mudur_yardimcisi_mi(request.user):
        raise PermissionDenied

    tahtalar = SinifTahta.objects.select_related("sinif_sube").order_by(
        "sinif_sube__sinif", "sinif_sube__sube"
    )
    return render(request, "bildirim_gonderici/tahta_listesi.html", {"tahtalar": tahtalar})


# ── Tahta Ekle ─────────────────────────────────────────────────
@login_required
def tahta_ekle(request):
    if not _mudur_yardimcisi_mi(request.user):
        raise PermissionDenied

    if request.method == "POST":
        form = SinifTahtaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Tahta kaydedildi.")
            return redirect("bildirim:tahta_listesi")
    else:
        form = SinifTahtaForm()
    return render(request, "bildirim_gonderici/tahta_form.html", {"form": form, "baslik": "Tahta Ekle"})


# ── Tahta Düzenle ──────────────────────────────────────────────
@login_required
def tahta_duzenle(request, pk):
    if not _mudur_yardimcisi_mi(request.user):
        raise PermissionDenied

    tahta = get_object_or_404(SinifTahta, pk=pk)
    if request.method == "POST":
        form = SinifTahtaForm(request.POST, instance=tahta)
        if form.is_valid():
            form.save()
            messages.success(request, "Tahta güncellendi.")
            return redirect("bildirim:tahta_listesi")
    else:
        form = SinifTahtaForm(instance=tahta)
    return render(request, "bildirim_gonderici/tahta_form.html", {"form": form, "baslik": "Tahta Düzenle"})


# ── Tahta Sil ──────────────────────────────────────────────────
@login_required
def tahta_sil(request, pk):
    if not _mudur_yardimcisi_mi(request.user):
        raise PermissionDenied

    tahta = get_object_or_404(SinifTahta, pk=pk)
    if request.method == "POST":
        tahta.delete()
        messages.success(request, "Tahta silindi.")
        return redirect("bildirim:tahta_listesi")
    return render(request, "bildirim_gonderici/tahta_sil.html", {"tahta": tahta})


# ── Test Bildirimi ─────────────────────────────────────────────
@login_required
def tahta_test(request, pk):
    if not _mudur_yardimcisi_mi(request.user):
        raise PermissionDenied

    tahta = get_object_or_404(SinifTahta, pk=pk)
    from .services import tahta_bildirimi_gonder
    tahta_bildirimi_gonder(
        tahta,
        baslik="✅ TEST BİLDİRİMİ",
        mesaj=f"{tahta.sinif_sube} tahtasına bağlantı testi başarılı.",
        tur=BildirimLog.TUR_TEST,
        gonderen=request.user,
    )
    messages.info(request, f"{tahta.sinif_sube} tahtasına test bildirimi gönderildi.")
    return redirect("bildirim:tahta_listesi")


# ── Bildirim Geçmişi ───────────────────────────────────────────
@login_required
def bildirim_gecmisi(request):
    if not _yonetici_mi(request.user):
        raise PermissionDenied

    qs = BildirimLog.objects.select_related("tahta__sinif_sube", "gonderen").order_by(
        "-gonderim_zamani"
    )[:200]
    return render(request, "bildirim_gonderici/bildirim_gecmisi.html", {"kayitlar": qs})


# ── Durum Sorgulama (AJAX) ─────────────────────────────────────
@login_required
def tahta_durum(request, pk):
    if not _mudur_yardimcisi_mi(request.user):
        return JsonResponse({"error": "Yetkisiz"}, status=403)

    tahta = get_object_or_404(SinifTahta, pk=pk)
    import urllib.error
    import urllib.request

    from django.conf import settings
    timeout = getattr(settings, "BILDIRIM_TIMEOUT", 4)
    try:
        req = urllib.request.Request(
            f"http://{tahta.ip_adresi}:{tahta.port}/saglik",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout):
            return JsonResponse({"durum": "cevap_veriyor"})
    except Exception:
        return JsonResponse({"durum": "cevap_vermiyor"})
