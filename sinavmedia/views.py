import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from okul.auth import is_mudur_yardimcisi as _mudur_yardimcisi_mi
from sinav.models import Takvim

from .models import SinavMedia
from .services.erisim import (
    TOLERANS_DAKIKA,
    dosya_erisimi_var_mi,
    oynatma_acik_mi,
    sinav_baslangici,
)

SEVIYE_LABELS = {9: "9. Sınıf", 10: "10. Sınıf", 11: "11. Sınıf", 12: "12. Sınıf"}


def _seviye_from_subeler(subeler_str):
    """Takvim.subeler alanından o slota ait seviye listesini çıkarır.
    Örn. '12/A, 12/B' → [(12, '12. Sınıf')]
    """
    seviyeler = set()
    for sube in (s.strip() for s in subeler_str.upper().split(",") if s.strip()):
        m = re.match(r'^(\d+)', sube)
        if m:
            sev = int(m.group(1))
            if sev in SEVIYE_LABELS:
                seviyeler.add(sev)
    if not seviyeler:
        return list(SEVIYE_LABELS.items())
    return [(sev, SEVIYE_LABELS[sev]) for sev in sorted(seviyeler)]


# ---------------------------------------------------------------
# Yönetim sayfası
# ---------------------------------------------------------------
@login_required
def yonetim(request):
    if not _mudur_yardimcisi_mi(request.user):
        raise Http404

    from sinav.models import SinavBilgisi, TakvimUretim as TU
    aktif_sinav = SinavBilgisi.objects.filter(aktif=True).first()

    if not aktif_sinav:
        return render(request, "sinavmedia/yonetim.html", {
            "aktif_sinav": None, "aktif_uretim": None,
            "slot_listesi": [], "hata": "Henüz aktif bir sınav tanımlanmamış.",
        })

    # aktif=True olan üretimi önce ara; yoksa en son üretimi kullan
    aktif_uretim = (
        TU.objects.filter(sinav=aktif_sinav, aktif=True).first()
        or TU.objects.filter(sinav=aktif_sinav).order_by("-uretim_tarihi").first()
    )

    ctx_base = {"aktif_sinav": aktif_sinav, "aktif_uretim": aktif_uretim}

    if not aktif_uretim:
        return render(request, "sinavmedia/yonetim.html",
                      {**ctx_base, "slot_listesi": [],
                       "hata": "Bu sınav için henüz takvim üretimi yapılmamış."})

    # Sadece (Uygulama) içeren takvim slotlarını getir
    takvimler = (
        Takvim.objects.filter(
            sinav_turu="Uygulama",
            uretim=aktif_uretim,
        )
        .select_related("ders")
        .prefetch_related("medyalar")
        .order_by("tarih", "saat", "ders__ders_adi")
        .distinct()
    )

    # Her slot için seviye satırlarını SubeDers'ten akıllıca hazırla
    slot_listesi = []
    for t in takvimler:
        medya_map = {m.seviye: m for m in t.medyalar.all()}
        seviyeler = _seviye_from_subeler(t.subeler)
        satirlar = [
            {"seviye": sev, "label": lbl, "medya": medya_map.get(sev)}
            for sev, lbl in seviyeler
        ]
        slot_listesi.append({"takvim": t, "satirlar": satirlar})

    return render(request, "sinavmedia/yonetim.html",
                  {**ctx_base, "slot_listesi": slot_listesi})


# ---------------------------------------------------------------
# Dosya yükle / güncelle
# ---------------------------------------------------------------
@login_required
@require_POST
def yukle(request, takvim_pk, seviye):
    if not _mudur_yardimcisi_mi(request.user):
        raise Http404

    takvim = get_object_or_404(Takvim, pk=takvim_pk, sinav_turu="Uygulama")
    dosya = request.FILES.get("dosya")
    if not dosya:
        messages.error(request, "Dosya seçilmedi.")
        return redirect("sinavmedia:yonetim")

    obj, _ = SinavMedia.objects.get_or_create(takvim=takvim, seviye=seviye)
    # Eski dosyayı sil
    if obj.dosya:
        obj.dosya.delete(save=False)
    obj.dosya = dosya
    obj.aciklama = request.POST.get("aciklama", "")
    obj.save()
    messages.success(request, f"{takvim} – {obj.get_seviye_display()} yüklendi.")
    return redirect("sinavmedia:yonetim")


# ---------------------------------------------------------------
# Serbest bırak / kilitle toggle
# ---------------------------------------------------------------
@login_required
@require_POST
def serbest_toggle(request, pk):
    if not _mudur_yardimcisi_mi(request.user):
        raise Http404

    medya = get_object_or_404(SinavMedia, pk=pk)
    medya.serbest = not medya.serbest
    medya.save(update_fields=["serbest"])
    durum = "serbest bırakıldı" if medya.serbest else "kilitlendi"
    messages.success(request, f"{medya} {durum}.")
    return redirect("sinavmedia:yonetim")


# ---------------------------------------------------------------
# Sil
# ---------------------------------------------------------------
@login_required
@require_POST
def sil(request, pk):
    if not _mudur_yardimcisi_mi(request.user):
        raise Http404

    medya = get_object_or_404(SinavMedia, pk=pk)
    medya.dosya.delete(save=False)
    medya.delete()
    messages.success(request, "Medya silindi.")
    return redirect("sinavmedia:yonetim")


# ---------------------------------------------------------------
# Oynatıcı (öğretmen + yönetici)
# ---------------------------------------------------------------
@login_required
def oynat(request, pk):
    medya = get_object_or_404(SinavMedia, pk=pk)
    yonetici = _mudur_yardimcisi_mi(request.user)

    if not yonetici and not oynatma_acik_mi(medya):
        return render(request, "sinavmedia/kilitli.html", {
            "medya": medya,
            "sinav_dt": sinav_baslangici(medya),
            "tolerans": TOLERANS_DAKIKA,
        })

    return render(request, "sinavmedia/oynatici.html", {
        "medya": medya,
        "yonetici": yonetici,
    })


# ---------------------------------------------------------------
# Dosya (korumalı)
# ---------------------------------------------------------------
@login_required
def dosya(request, pk):
    """Medya dosyasını erişim kuralına göre verir (bkz. services/erisim.py).

    settings.SINAVMEDIA_X_ACCEL açıksa (prod, Nginx'te `internal` /korumali-medya/ yolu
    tanımlıyken) dosyayı Nginx teslim eder — Range/seek desteği ve worker'ı meşgul
    etmemek için. Kapalıysa (geliştirme ya da Nginx henüz güncellenmemişken) Django verir."""
    import mimetypes
    from urllib.parse import quote

    from django.conf import settings
    from django.core.exceptions import PermissionDenied
    from django.http import FileResponse, HttpResponse

    medya = get_object_or_404(SinavMedia.objects.select_related("takvim"), pk=pk)
    if not medya.dosya or not dosya_erisimi_var_mi(request.user, medya):
        raise PermissionDenied

    icerik_turu = mimetypes.guess_type(medya.dosya.name)[0] or "application/octet-stream"
    if getattr(settings, "SINAVMEDIA_X_ACCEL", False):
        yanit = HttpResponse(content_type=icerik_turu)
        yanit["X-Accel-Redirect"] = "/korumali-medya/" + quote(medya.dosya.name)
    else:
        try:
            yanit = FileResponse(medya.dosya.open("rb"), content_type=icerik_turu)
        except FileNotFoundError:
            raise Http404
    yanit["Cache-Control"] = "private, no-store"
    return yanit
