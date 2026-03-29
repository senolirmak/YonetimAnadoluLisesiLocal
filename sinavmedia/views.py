from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from okul.models import DersHavuzu
from sinav.models import SubeDers, Takvim

from .models import SinavMedia

SEVIYE_LABELS = {9: "9. Sınıf", 10: "10. Sınıf", 11: "11. Sınıf", 12: "12. Sınıf"}


def _ders_seviyeleri(ders_adi):
    """SubeDers tablosundan dersin okutulduğu seviyeleri döndürür."""
    base = ders_adi.replace(" (Uygulama)", "").replace(" (Yazili)", "").strip()
    ders = DersHavuzu.objects.filter(ders_adi=base).first()
    if not ders:
        # Tam eşleşme yoksa içeren ara
        ders = DersHavuzu.objects.filter(ders_adi__icontains=base).first()
    if not ders:
        return list(SEVIYE_LABELS.items())  # Bilinmiyorsa hepsini göster
    seviyeler = (
        SubeDers.objects.filter(ders=ders)
        .values_list("seviye", flat=True)
        .distinct()
        .order_by("seviye")
    )
    return [(sev, SEVIYE_LABELS[sev]) for sev in seviyeler if sev in SEVIYE_LABELS]

TOLERANS_DAKIKA = 5


from okul.auth import is_mudur_yardimcisi as _mudur_yardimcisi_mi


# ---------------------------------------------------------------
# Yönetim sayfası
# ---------------------------------------------------------------
@login_required
def yonetim(request):
    if not _mudur_yardimcisi_mi(request.user):
        raise Http404

    # Aktif sınav + aktif üretim filtresi — duplicate üretimlerden korunmak için
    from sinav.models import SinavBilgisi, TakvimUretim as TU
    aktif_sinav = SinavBilgisi.objects.filter(aktif=True).first()
    aktif_uretim = TU.objects.filter(sinav=aktif_sinav, aktif=True).first() if aktif_sinav else None

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
        seviyeler = _ders_seviyeleri(t.ders.ders_adi if t.ders else "")
        satirlar = [
            {"seviye": sev, "label": lbl, "medya": medya_map.get(sev)}
            for sev, lbl in seviyeler
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
