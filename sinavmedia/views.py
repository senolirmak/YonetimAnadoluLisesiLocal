from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from sinav.models import Takvim

from .models import SinavMedia

TOLERANS_DAKIKA = 5


def _mudur_yardimcisi_mi(user):
    return user.is_superuser or user.groups.filter(name="mudur_yardimcisi").exists()


# ---------------------------------------------------------------
# Yönetim sayfası
# ---------------------------------------------------------------
@login_required
def yonetim(request):
    if not _mudur_yardimcisi_mi(request.user):
        raise Http404

    # Sadece (Uygulama) içeren takvim slotlarını getir
    takvimler = (
        Takvim.objects.filter(ders_adi__icontains="(Uygulama)")
        .prefetch_related("medyalar")
        .order_by("tarih", "saat", "ders_adi")
    )

    SEVIYELER = [(9, "9. Sınıf"), (10, "10. Sınıf"), (11, "11. Sınıf"), (12, "12. Sınıf")]

    # Her slot için seviye satırlarını hazırla
    slot_listesi = []
    for t in takvimler:
        medya_map = {m.seviye: m for m in t.medyalar.all()}
        satirlar = [
            {"seviye": sev, "label": lbl, "medya": medya_map.get(sev)}
            for sev, lbl in SEVIYELER
        ]
        slot_listesi.append({"takvim": t, "satirlar": satirlar})

    return render(request, "sinavmedia/yonetim.html", {"slot_listesi": slot_listesi})


# ---------------------------------------------------------------
# Dosya yükle / güncelle
# ---------------------------------------------------------------
@login_required
@require_POST
def yukle(request, takvim_pk, seviye):
    if not _mudur_yardimcisi_mi(request.user):
        raise Http404

    takvim = get_object_or_404(Takvim, pk=takvim_pk, ders_adi__icontains="(Uygulama)")
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

    if not yonetici and not medya.serbest:
        # Zaman kısıtı: sınav saati ± TOLERANS_DAKIKA
        sinav_saat = datetime.strptime(medya.takvim.saat, "%H:%M").time()
        sinav_dt = timezone.make_aware(
            datetime.combine(medya.takvim.tarih, sinav_saat)
        )
        simdi = timezone.now()
        acilis = sinav_dt - timedelta(minutes=TOLERANS_DAKIKA)
        kapanis = sinav_dt + timedelta(minutes=TOLERANS_DAKIKA)

        if not (acilis <= simdi <= kapanis):
            return render(request, "sinavmedia/kilitli.html", {
                "medya": medya,
                "sinav_dt": sinav_dt,
                "tolerans": TOLERANS_DAKIKA,
            })

    return render(request, "sinavmedia/oynatici.html", {
        "medya": medya,
        "yonetici": yonetici,
    })
